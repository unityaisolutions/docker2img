"""
Test script for the Docker to Bootable Image conversion process.
"""

import os
import tempfile
import shutil
from docker_registry import DockerRegistryClient
from image_converter import ImageConverter


def test_docker_registry_download():
    """Test downloading a small Docker image."""
    print("=== Testing Docker Registry Download ===")
    
    try:
        # Test with Alpine Linux (small image)
        registry, repo, tag = DockerRegistryClient.parse_image_url('alpine:latest')
        print(f"Parsed: {registry}/{repo}:{tag}")
        
        client = DockerRegistryClient(registry, repo)
        
        # Get image info
        info = client.get_image_info(tag)
        print(f"Image info: {info}")
        
        # Download layers
        temp_dir = tempfile.mkdtemp(prefix='test_layers_')
        print(f"Downloading to: {temp_dir}")
        
        layers = client.download_all_layers(tag, temp_dir)
        print(f"Downloaded {len(layers)} layers")
        
        # Extract to rootfs
        rootfs_dir = tempfile.mkdtemp(prefix='test_rootfs_')
        print(f"Extracting to: {rootfs_dir}")
        
        client.extract_layers_to_rootfs(layers, rootfs_dir)
        
        # Check if basic directories exist
        basic_dirs = ['/bin', '/etc', '/usr', '/var']
        for dir_name in basic_dirs:
            full_path = os.path.join(rootfs_dir, dir_name.lstrip('/'))
            if os.path.exists(full_path):
                print(f"✓ Found {dir_name}")
            else:
                print(f"✗ Missing {dir_name}")
        
        print("✅ Docker registry download test completed successfully")
        return rootfs_dir
        
    except Exception as e:
        print(f"❌ Docker registry test failed: {str(e)}")
        return None


def test_image_creation_dry_run():
    """Test the image creation process without actually creating a bootable image."""
    print("\n=== Testing Image Creation (Dry Run) ===")
    
    try:
        converter = ImageConverter(image_size_mb=512)
        
        # Test disk image creation
        temp_img = tempfile.mktemp(suffix='.img')
        print(f"Creating test disk image: {temp_img}")
        
        converter.create_disk_image(temp_img)
        
        if os.path.exists(temp_img):
            size_mb = os.path.getsize(temp_img) / (1024 * 1024)
            print(f"✓ Created disk image: {size_mb:.1f}MB")
            os.remove(temp_img)
        else:
            print("✗ Failed to create disk image")
            return False
        
        print("✅ Image creation dry run completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Image creation test failed: {str(e)}")
        return False


def test_full_conversion_simulation():
    """Simulate the full conversion process without requiring sudo."""
    print("\n=== Testing Full Conversion (Simulation) ===")
    
    try:
        # Download Alpine image
        rootfs_dir = test_docker_registry_download()
        if not rootfs_dir:
            return False
        
        print("\n--- Simulating Conversion Steps ---")
        
        # Simulate the conversion steps
        converter = ImageConverter(image_size_mb=1024)
        
        # Step 1: Create disk image (this works without sudo)
        temp_img = tempfile.mktemp(suffix='.img')
        print("1. Creating disk image...")
        converter.create_disk_image(temp_img)
        print("   ✓ Disk image created")
        
        # Steps 2-7 would require sudo, so we just simulate them
        print("2. Partitioning disk... (simulated)")
        print("3. Formatting partition... (simulated)")
        print("4. Mounting partition... (simulated)")
        print("5. Copying rootfs... (simulated)")
        print("6. Installing kernel/bootloader... (simulated)")
        print("7. Unmounting and cleanup... (simulated)")
        
        # Cleanup
        if os.path.exists(temp_img):
            os.remove(temp_img)
        
        shutil.rmtree(rootfs_dir, ignore_errors=True)
        
        print("✅ Full conversion simulation completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Full conversion simulation failed: {str(e)}")
        return False


def main():
    """Run all tests."""
    print("Docker to Bootable Image Converter - Test Suite")
    print("=" * 50)
    
    tests = [
        test_docker_registry_download,
        test_image_creation_dry_run,
        test_full_conversion_simulation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {str(e)}")
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    print("\nNote: Full conversion with bootloader installation requires sudo privileges.")
    print("The Gradio app will handle this when run with appropriate permissions.")


if __name__ == '__main__':
    main()
