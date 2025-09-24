#!/usr/bin/env python3

"""Debug script to check manifest parsing"""

from docker_registry import DockerRegistryClient
import json

try:
    print("=== Debug Manifest Parsing ===")
    
    # Parse image URL
    registry, repo, tag = DockerRegistryClient.parse_image_url('alpine:latest')
    print(f"Parsed: {registry}/{repo}:{tag}")
    
    # Create client
    client = DockerRegistryClient(registry, repo)
    
    # Get raw manifest
    print("\n=== Raw Manifest ===")
    manifest = client.get_manifest(tag)
    print(f"Type: {type(manifest)}")
    print(f"Keys: {list(manifest.keys()) if isinstance(manifest, dict) else 'Not a dict'}")
    print(f"Media Type: {manifest.get('mediaType', 'None')}")
    print(f"Schema Version: {manifest.get('schemaVersion', 'None')}")
    
    if 'manifests' in manifest:
        print(f"\nManifest List with {len(manifest['manifests'])} entries:")
        for i, entry in enumerate(manifest['manifests']):
            platform = entry.get('platform', {})
            print(f"  {i}: {platform.get('os', '?')}/{platform.get('architecture', '?')} - {entry.get('digest', '?')}")
    
    # Test platform-specific parsing
    print("\n=== Testing Platform-Specific Parsing ===")
    info = client.get_image_info(tag, 'linux/amd64')
    print(f"Image info: {info}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()