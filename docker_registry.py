"""
Docker Registry Interaction Module

This module handles communication with Docker registries using the DXF library
to download image manifests and layers for conversion to bootable images.
"""

import os
import json
import tempfile
import tarfile
from typing import List, Dict, Optional, Tuple
from dxf import DXF
import requests


class DockerRegistryClient:
    """Client for interacting with Docker registries."""
    
    def __init__(self, registry_url: str, repository: str, username: Optional[str] = None, 
                 password: Optional[str] = None, insecure: bool = False):
        """
        Initialize the Docker registry client.
        
        Args:
            registry_url: The registry host (e.g., 'registry-1.docker.io')
            repository: The repository name (e.g., 'library/ubuntu')
            username: Optional username for authentication
            password: Optional password for authentication
            insecure: Whether to use HTTP instead of HTTPS
        """
        self.registry_url = registry_url
        self.repository = repository
        self.username = username
        self.password = password
        self.insecure = insecure
        
        # Set up authentication function
        def auth_func(dxf_obj, response):
            if self.username and self.password:
                dxf_obj.authenticate(self.username, self.password, response=response)
            else:
                # For public repositories, we still need to handle auth challenges
                dxf_obj.authenticate(response=response)
        
        self.dxf = DXF(self.registry_url, self.repository, auth_func)
        
        # Configure for insecure connections if needed
        if insecure:
            os.environ['DXF_INSECURE'] = '1'
    
    @staticmethod
    def parse_image_url(image_url: str) -> Tuple[str, str, str]:
        """
        Parse a Docker image URL into registry, repository, and tag components.
        
        Args:
            image_url: Full Docker image URL (e.g., 'registry.hub.docker.com/library/ubuntu:latest')
            
        Returns:
            Tuple of (registry_url, repository, tag)
        """
        # Handle different URL formats
        if '://' in image_url:
            # Remove protocol if present
            image_url = image_url.split('://', 1)[1]
        
        parts = image_url.split('/')
        
        if len(parts) == 1:
            # Just image name, assume Docker Hub
            registry_url = 'registry-1.docker.io'
            repository = f'library/{parts[0]}'
        elif len(parts) == 2:
            # user/image format, assume Docker Hub
            registry_url = 'registry-1.docker.io'
            repository = image_url
        else:
            # Full registry URL
            registry_url = parts[0]
            repository = '/'.join(parts[1:])
        
        # Extract tag if present
        if ':' in repository:
            repository, tag = repository.rsplit(':', 1)
        else:
            tag = 'latest'
            
        return registry_url, repository, tag
    
    def get_manifest(self, tag: str = 'latest') -> Dict:
        """
        Get the image manifest for the specified tag.
        
        Args:
            tag: The image tag to retrieve
            
        Returns:
            The parsed manifest as a dictionary
        """
        try:
            manifest_data = self.dxf.get_manifest(tag)
            print(f"DEBUG: Raw manifest type: {type(manifest_data)}")
            
            # Handle different return types from dxf
            if isinstance(manifest_data, dict):
                print(f"DEBUG: Manifest is dict with keys: {list(manifest_data.keys())}")
                # Check if this is a platform-specific manifest dict from DXF
                if all(key.count('/') == 1 for key in manifest_data.keys() if isinstance(key, str)):
                    # This looks like DXF's platform-specific format
                    # Try to get the linux/amd64 manifest or first available
                    platform_key = 'linux/amd64'
                    if platform_key in manifest_data:
                        print(f"DEBUG: Using platform-specific manifest for {platform_key}")
                        platform_manifest = manifest_data[platform_key]
                        if isinstance(platform_manifest, str):
                            return json.loads(platform_manifest)
                        else:
                            return platform_manifest
                    else:
                        # Use first available platform
                        first_key = next(iter(manifest_data.keys()))
                        print(f"DEBUG: Platform linux/amd64 not found, using {first_key}")
                        platform_manifest = manifest_data[first_key]
                        if isinstance(platform_manifest, str):
                            return json.loads(platform_manifest)
                        else:
                            return platform_manifest
                else:
                    # Regular manifest dict
                    return manifest_data
            elif isinstance(manifest_data, str):
                print(f"DEBUG: Manifest is string, parsing JSON")
                return json.loads(manifest_data)
            else:
                print(f"DEBUG: Unexpected manifest type: {type(manifest_data)}")
                return manifest_data
        except Exception as e:
            raise Exception(f"Failed to get manifest for {self.repository}:{tag}: {str(e)}")
    
    def download_layer(self, digest: str, output_path: str) -> None:
        """
        Download a specific layer by its digest.
        
        Args:
            digest: The layer digest (e.g., 'sha256:abc123...')
            output_path: Path where the layer should be saved
        """
        try:
            with open(output_path, 'wb') as f:
                for chunk in self.dxf.pull_blob(digest):
                    f.write(chunk)
        except Exception as e:
            raise Exception(f"Failed to download layer {digest}: {str(e)}")
    
    def download_all_layers(self, tag: str = 'latest', output_dir: str = None, platform: str = 'linux/amd64') -> List[str]:
        """
        Download all layers for the specified image tag.
        
        Args:
            tag: The image tag to download
            output_dir: Directory to save layers (uses temp dir if None)
            platform: Platform to download for multi-arch images (e.g., 'linux/amd64')
            
        Returns:
            List of paths to downloaded layer files
        """
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix='docker_layers_')
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Get the manifest
        manifest = self.get_manifest(tag)
        
        # Handle manifest list (multi-platform)
        if manifest.get('mediaType') == 'application/vnd.docker.distribution.manifest.list.v2+json':
            # This is a manifest list, find the platform-specific manifest
            platform_arch = platform.split('/')[-1] if '/' in platform else platform
            platform_os = platform.split('/')[0] if '/' in platform else 'linux'
            
            for manifest_entry in manifest.get('manifests', []):
                entry_platform = manifest_entry.get('platform', {})
                if (entry_platform.get('architecture') == platform_arch and 
                    entry_platform.get('os', 'linux') == platform_os):
                    platform_digest = manifest_entry['digest']
                    print(f"Found platform-specific manifest: {platform_digest}")
                    # Get the platform-specific manifest
                    manifest_data = self.dxf.get_manifest(platform_digest)
                    if isinstance(manifest_data, dict):
                        manifest = manifest_data
                    else:
                        manifest = json.loads(manifest_data)
                    break
            else:
                print(f"Warning: Platform {platform} not found, using first available manifest")
                if manifest.get('manifests'):
                    platform_digest = manifest['manifests'][0]['digest']
                    manifest_data = self.dxf.get_manifest(platform_digest)
                    if isinstance(manifest_data, dict):
                        manifest = manifest_data
                    else:
                        manifest = json.loads(manifest_data)
        
        # Handle different manifest formats
        layers = []
        if manifest.get('schemaVersion') == 2:
            if 'layers' in manifest:
                # Schema 2 format (most common)
                layers = manifest['layers']
            elif 'fsLayers' in manifest:
                # Schema 1 format (legacy)
                layers = [{'digest': layer['blobSum']} for layer in manifest['fsLayers']]
        elif manifest.get('schemaVersion') == 1:
            # Schema 1 format
            if 'fsLayers' in manifest:
                layers = [{'digest': layer['blobSum']} for layer in manifest['fsLayers']]
        
        if not layers:
            raise Exception(f"No layers found in manifest. Schema version: {manifest.get('schemaVersion')}, Keys: {list(manifest.keys())}")
        
        downloaded_layers = []
        
        for i, layer in enumerate(layers):
            digest = layer['digest']
            layer_filename = f"layer_{i:03d}_{digest.replace(':', '_')}.tar"
            layer_path = os.path.join(output_dir, layer_filename)
            
            print(f"Downloading layer {i+1}/{len(layers)}: {digest}")
            self.download_layer(digest, layer_path)
            downloaded_layers.append(layer_path)
        
        return downloaded_layers
    
    def extract_layers_to_rootfs(self, layer_paths: List[str], rootfs_dir: str) -> None:
        """
        Extract all downloaded layers to create a complete root filesystem.
        
        Args:
            layer_paths: List of paths to layer tar files
            rootfs_dir: Directory where the root filesystem should be created
        """
        os.makedirs(rootfs_dir, exist_ok=True)
        
        for i, layer_path in enumerate(layer_paths):
            print(f"Extracting layer {i+1}/{len(layer_paths)}: {os.path.basename(layer_path)}")
            
            try:
                with tarfile.open(layer_path, 'r') as tar:
                    # Extract all files, preserving permissions and ownership where possible
                    tar.extractall(path=rootfs_dir, numeric_owner=True)
            except Exception as e:
                print(f"Warning: Failed to extract layer {layer_path}: {str(e)}")
                continue
    
    def get_image_info(self, tag: str = 'latest', platform: str = 'linux/amd64') -> Dict:
        """
        Get basic information about the image.
        
        Args:
            tag: The image tag to inspect
            platform: Platform to get info for (in case of manifest lists)
            
        Returns:
            Dictionary with image information
        """
        manifest = self.get_manifest(tag)
        
        # Handle manifest list (multi-platform)
        if manifest.get('mediaType') == 'application/vnd.docker.distribution.manifest.list.v2+json':
            # This is a manifest list, find the platform-specific manifest
            platform_arch = platform.split('/')[-1] if '/' in platform else platform
            platform_os = platform.split('/')[0] if '/' in platform else 'linux'
            
            for manifest_entry in manifest.get('manifests', []):
                entry_platform = manifest_entry.get('platform', {})
                if (entry_platform.get('architecture') == platform_arch and 
                    entry_platform.get('os', 'linux') == platform_os):
                    platform_digest = manifest_entry['digest']
                    # Get the platform-specific manifest
                    manifest_data = self.dxf.get_manifest(platform_digest)
                    if isinstance(manifest_data, dict):
                        manifest = manifest_data
                    else:
                        manifest = json.loads(manifest_data)
                    break
            else:
                # Use first available manifest if platform not found
                if manifest.get('manifests'):
                    platform_digest = manifest['manifests'][0]['digest']
                    manifest_data = self.dxf.get_manifest(platform_digest)
                    if isinstance(manifest_data, dict):
                        manifest = manifest_data
                    else:
                        manifest = json.loads(manifest_data)
        
        info = {
            'registry': self.registry_url,
            'repository': self.repository,
            'tag': tag,
            'schema_version': manifest.get('schemaVersion'),
            'layer_count': 0,
            'total_size': 0
        }
        
        # Count layers and calculate total size
        if 'layers' in manifest:
            info['layer_count'] = len(manifest['layers'])
            info['total_size'] = sum(layer.get('size', 0) for layer in manifest['layers'])
        elif 'fsLayers' in manifest:
            info['layer_count'] = len(manifest['fsLayers'])
            # Schema 1 doesn't include size info in the manifest
        
        return info


def test_registry_client():
    """Test function for the Docker registry client."""
    # Test with a small public image
    try:
        registry, repo, tag = DockerRegistryClient.parse_image_url('alpine:latest')
        print(f"Parsed URL: registry={registry}, repo={repo}, tag={tag}")
        
        client = DockerRegistryClient(registry, repo)
        info = client.get_image_info(tag)
        print(f"Image info: {info}")
        
        # Download layers to a temporary directory
        temp_dir = tempfile.mkdtemp(prefix='test_layers_')
        print(f"Downloading layers to: {temp_dir}")
        
        layers = client.download_all_layers(tag, temp_dir)
        print(f"Downloaded {len(layers)} layers")
        
        # Extract to rootfs
        rootfs_dir = tempfile.mkdtemp(prefix='test_rootfs_')
        print(f"Extracting to rootfs: {rootfs_dir}")
        
        client.extract_layers_to_rootfs(layers, rootfs_dir)
        print("Extraction complete!")
        
        # List some files in the rootfs
        import subprocess
        result = subprocess.run(['ls', '-la', rootfs_dir], capture_output=True, text=True)
        print(f"Rootfs contents:\n{result.stdout}")
        
    except Exception as e:
        print(f"Test failed: {str(e)}")


if __name__ == '__main__':
    test_registry_client()