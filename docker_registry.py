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
            # dxf.get_manifest() returns a dict, not a JSON string
            if isinstance(manifest_data, dict):
                return manifest_data
            else:
                return json.loads(manifest_data)
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
        
        # Handle multi-platform manifest lists
        if isinstance(manifest, dict) and platform in manifest:
            # This is a multi-platform manifest list, get the specific platform
            platform_manifest_str = manifest[platform]
            manifest = json.loads(platform_manifest_str)
            print(f"Using platform-specific manifest for {platform}")
        
        # Handle different manifest formats
        if manifest.get('schemaVersion') == 2:
            if 'layers' in manifest:
                # Schema 2 format
                layers = manifest['layers']
            elif 'fsLayers' in manifest:
                # Schema 1 format
                layers = [{'digest': layer['blobSum']} for layer in manifest['fsLayers']]
            else:
                raise Exception("Unsupported manifest format")
        else:
            raise Exception(f"Unsupported manifest schema version: {manifest.get('schemaVersion')}")
        
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
    
    def get_image_info(self, tag: str = 'latest') -> Dict:
        """
        Get basic information about the image.
        
        Args:
            tag: The image tag to inspect
            
        Returns:
            Dictionary with image information
        """
        manifest = self.get_manifest(tag)
        
        info = {
            'registry': self.registry_url,
            'repository': self.repository,
            'tag': tag,
            'schema_version': manifest.get('schemaVersion'),
            'layer_count': 0,
            'total_size': 0
        }
        
        if 'layers' in manifest:
            info['layer_count'] = len(manifest['layers'])
            info['total_size'] = sum(layer.get('size', 0) for layer in manifest['layers'])
        elif 'fsLayers' in manifest:
            info['layer_count'] = len(manifest['fsLayers'])
        
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