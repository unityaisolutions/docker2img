"""
Docker Registry Interaction Module

This module handles communication with Docker registries using the DXF library
to download image manifests and layers for conversion to bootable images.
"""

import os
import json
import tempfile
import tarfile
from typing import List, Dict, Optional, Tuple, Any
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
    
    def get_manifest(self, tag: str = 'latest', platform: Optional[str] = None) -> Dict:
        """
        Get the image manifest for the specified tag.
        
        Args:
            tag: The image tag to retrieve
            platform: Optional platform (e.g., 'linux/amd64', 'linux/arm/v7') used when DXF returns a
                      platform-keyed manifest map
        
        Returns:
            The parsed manifest as a dictionary
        """
        try:
            manifest_data = self.dxf.get_manifest(tag)
            print(f"DEBUG: Raw manifest type: {type(manifest_data)}")
            
            # Normalize string to dict
            if isinstance(manifest_data, str):
                print("DEBUG: Manifest is string, parsing JSON")
                manifest_data = json.loads(manifest_data)
            
            if isinstance(manifest_data, dict):
                keys = [k for k in manifest_data.keys() if isinstance(k, str)]
                print(f"DEBUG: Manifest is dict with keys: {keys}")
                
                # If this is a manifest list/index (has 'manifests' array), return as-is.
                if 'manifests' in manifest_data:
                    return manifest_data
                
                # If this looks like a platform-keyed map returned by DXF, resolve to the requested platform.
                # Example keys: 'linux/amd64', 'linux/arm/v7', 'linux/arm64/v8', 'unknown/unknown'
                platform_map_like = (
                    len(keys) > 0 and
                    all('/' in k for k in keys) and
                    not any(k in ('schemaVersion', 'mediaType', 'layers', 'fsLayers') for k in keys)
                )
                if platform_map_like:
                    resolved = self._resolve_platform_manifest_map(manifest_data, platform)
                    return resolved
                
                # Otherwise assume this is already a concrete manifest dict
                return manifest_data
            
            # Unexpected - return as-is (caller will handle)
            print(f"DEBUG: Unexpected manifest type after normalization: {type(manifest_data)}")
            return manifest_data
        except Exception as e:
            raise Exception(f"Failed to get manifest for {self.repository}:{tag}: {str(e)}")
    
    def _resolve_platform_manifest_map(self, manifest_map: Dict[str, Any], platform: Optional[str]) -> Dict:
        """
        Resolve a DXF platform-keyed manifest map into a concrete manifest dict.
        Preference order:
          1) Exact platform match (e.g., linux/arm/v7)
          2) OS/arch prefix match (e.g., requested linux/arm matches linux/arm/v7)
          3) Fallback to linux/amd64 if present
          4) First available key
        """
        keys = [k for k in manifest_map.keys() if isinstance(k, str)]
        requested = platform or 'linux/amd64'
        
        # Helpers
        def load_manifest(val: Any) -> Dict:
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    # If string isn't JSON, let caller see raw
                    return {'raw': val}
            elif isinstance(val, dict):
                return val
            else:
                return {'raw': val}
        
        # 1) Exact match
        if requested in manifest_map:
            print(f"DEBUG: Using platform-specific manifest for {requested}")
            return load_manifest(manifest_map[requested])
        
        # 2) Prefix match (e.g., requested 'linux/arm64' matches 'linux/arm64/v8')
        prefix_matches = [k for k in keys if k.startswith(requested + '/')]
        if prefix_matches:
            chosen = prefix_matches[0]
            print(f"DEBUG: Using closest platform match: {chosen} for requested {requested}")
            return load_manifest(manifest_map[chosen])
        
        # 3) Fallback to linux/amd64
        if 'linux/amd64' in manifest_map:
            print("DEBUG: Requested platform not found, falling back to linux/amd64")
            return load_manifest(manifest_map['linux/amd64'])
        
        # 4) Final fallback: first key
        first_key = keys[0]
        print(f"DEBUG: Requested platform not found, using first available: {first_key}")
        return load_manifest(manifest_map[first_key])

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
        
        # Get the manifest (pass platform so DXF platform maps are resolved)
        manifest = self.get_manifest(tag, platform)
        
        # Handle manifest list (Docker V2 list and OCI index) and also fallback if 'manifests' key exists
        media_type = manifest.get('mediaType')
        if media_type in (
            'application/vnd.docker.distribution.manifest.list.v2+json',
            'application/vnd.oci.image.index.v1+json'
        ) or 'manifests' in manifest:
            # Parse requested platform into os/arch[/variant]
            tokens = platform.split('/') if platform else ['linux', 'amd64']
            platform_os = tokens[0] if len(tokens) > 0 else 'linux'
            platform_arch = tokens[1] if len(tokens) > 1 else 'amd64'
            platform_variant = tokens[2] if len(tokens) > 2 else None
            
            chosen_digest = None
            for manifest_entry in manifest.get('manifests', []):
                entry_platform = manifest_entry.get('platform', {})
                if (entry_platform.get('os') == platform_os and
                    entry_platform.get('architecture') == platform_arch and
                    (platform_variant is None or entry_platform.get('variant') == platform_variant)):
                    chosen_digest = manifest_entry.get('digest')
                    break
            # Fallback: match os/arch ignoring variant
            if not chosen_digest and platform_variant:
                for manifest_entry in manifest.get('manifests', []):
                    entry_platform = manifest_entry.get('platform', {})
                    if (entry_platform.get('os') == platform_os and
                        entry_platform.get('architecture') == platform_arch):
                        chosen_digest = manifest_entry.get('digest')
                        break
            # Final fallback: first available
            if not chosen_digest and manifest.get('manifests'):
                print(f"Warning: Platform {platform} not found in manifest list; using first available")
                chosen_digest = manifest['manifests'][0].get('digest')
            
            if chosen_digest:
                print(f"Selected platform-specific manifest: {chosen_digest}")
                manifest_data = self.dxf.get_manifest(chosen_digest)
                if isinstance(manifest_data, dict):
                    manifest = manifest_data
                else:
                    manifest = json.loads(manifest_data)
        
        # Handle different manifest formats
        layers: List[Dict[str, Any]] = []
        schema_version = manifest.get('schemaVersion')
        if schema_version == 2 or media_type == 'application/vnd.oci.image.manifest.v1+json':
            if 'layers' in manifest:
                # Schema 2 (Docker) or OCI manifest
                layers = manifest['layers']
            elif 'fsLayers' in manifest:
                # Some edge cases present schema 1 keys with schemaVersion 2 incorrectly
                layers = [{'digest': layer['blobSum']} for layer in manifest.get('fsLayers', [])]
        elif schema_version == 1:
            if 'fsLayers' in manifest:
                layers = [{'digest': layer['blobSum']} for layer in manifest['fsLayers']]
        
        if not layers:
            # Improve diagnostics for troubleshooting
            keys = list(manifest.keys())
            mt = manifest.get('mediaType')
            raise Exception(
                "No layers found in manifest. "
                f"Schema version: {schema_version}, MediaType: {mt}, Keys: {keys}. "
                "Hint: If Keys look like platform strings (e.g., 'linux/arm/v7'), the registry "
                "returned a platform map; ensure platform selection resolved to a concrete manifest."
            )
        
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
        manifest = self.get_manifest(tag, platform)
        
        # Handle manifest list (multi-platform: Docker V2 list or OCI index)
        media_type = manifest.get('mediaType')
        if media_type in (
            'application/vnd.docker.distribution.manifest.list.v2+json',
            'application/vnd.oci.image.index.v1+json'
        ) or 'manifests' in manifest:
            tokens = platform.split('/') if platform else ['linux', 'amd64']
            platform_os = tokens[0] if len(tokens) > 0 else 'linux'
            platform_arch = tokens[1] if len(tokens) > 1 else 'amd64'
            platform_variant = tokens[2] if len(tokens) > 2 else None
            
            chosen_digest = None
            for manifest_entry in manifest.get('manifests', []):
                entry_platform = manifest_entry.get('platform', {})
                if (entry_platform.get('os') == platform_os and
                    entry_platform.get('architecture') == platform_arch and
                    (platform_variant is None or entry_platform.get('variant') == platform_variant)):
                    chosen_digest = manifest_entry.get('digest')
                    break
            if not chosen_digest and platform_variant:
                for manifest_entry in manifest.get('manifests', []):
                    entry_platform = manifest_entry.get('platform', {})
                    if (entry_platform.get('os') == platform_os and
                        entry_platform.get('architecture') == platform_arch):
                        chosen_digest = manifest_entry.get('digest')
                        break
            if not chosen_digest and manifest.get('manifests'):
                chosen_digest = manifest['manifests'][0].get('digest')
            
            if chosen_digest:
                manifest_data = self.dxf.get_manifest(chosen_digest)
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