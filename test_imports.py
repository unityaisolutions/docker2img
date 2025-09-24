#!/usr/bin/env python3

"""Test script to check for import errors"""

try:
    print("Testing imports...")
    
    print("1. Testing gradio import...")
    import gradio as gr
    print("   ✓ gradio imported successfully")
    
    print("2. Testing dxf import...")
    from dxf import DXF
    print("   ✓ dxf imported successfully")
    
    print("3. Testing docker_registry module...")
    from docker_registry import DockerRegistryClient
    print("   ✓ docker_registry imported successfully")
    
    print("4. Testing image_converter module...")
    from image_converter import ImageConverter
    print("   ✓ image_converter imported successfully")
    
    print("5. Testing main app import...")
    from app import DockerToBootableApp
    print("   ✓ app imported successfully")
    
    print("\nAll imports successful!")
    
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()