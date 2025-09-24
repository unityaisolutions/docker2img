"""
Docker to Bootable Image Converter

This module handles the conversion of Docker container filesystems to bootable disk images.
It creates a disk image, partitions it, formats it, and installs a bootloader.
"""

import os
import subprocess
import tempfile
import shutil
from typing import Optional, List
import time


class ImageConverter:
    """Converts Docker container filesystems to bootable disk images."""
    
    def __init__(self, image_size_mb: int = 2048):
        """
        Initialize the image converter.
        
        Args:
            image_size_mb: Size of the disk image in megabytes
        """
        self.image_size_mb = image_size_mb
        self.temp_dirs = []
        self.loop_devices = []
        
    def cleanup(self):
        """Clean up temporary directories and loop devices."""
        # Detach loop devices
        for loop_device in self.loop_devices:
            try:
                subprocess.run(['sudo', 'losetup', '-d', loop_device], 
                             check=False, capture_output=True)
            except:
                pass
        
        # Remove temporary directories
        for temp_dir in self.temp_dirs:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
    
    def run_command(self, cmd: List[str], check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
        """
        Run a shell command with error handling.
        
        Args:
            cmd: Command to run as a list of strings
            check: Whether to raise exception on non-zero exit code
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            CompletedProcess object
        """
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        if result.stdout:
            print(f"STDOUT: {result.stdout}")
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        return result
    
    def create_disk_image(self, output_path: str) -> str:
        """
        Create an empty disk image file.
        
        Args:
            output_path: Path where the disk image should be created
            
        Returns:
            Path to the created disk image
        """
        print(f"Creating disk image: {output_path} ({self.image_size_mb}MB)")
        
        # Create sparse file
        self.run_command([
            'dd', 'if=/dev/zero', f'of={output_path}', 
            'bs=1M', f'count={self.image_size_mb}', 'status=progress'
        ])
        
        return output_path
    
    def partition_disk(self, disk_path: str) -> str:
        """
        Create a partition table and primary partition on the disk.

        Args:
            disk_path: Path to the disk image file

        Returns:
            Path to the loop device
        """
        print(f"Partitioning disk: {disk_path}")

        # Check if disk image exists
        print(f"DEBUG: Checking if disk image exists: {disk_path}")
        if not os.path.exists(disk_path):
            raise Exception(f"Disk image {disk_path} does not exist")

        # Check disk image size
        try:
            size_bytes = os.path.getsize(disk_path)
            size_mb = size_bytes / (1024 * 1024)
            print(f"DEBUG: Disk image size: {size_mb:.1f}MB")
        except Exception as e:
            print(f"ERROR: Cannot get disk image size: {e}")

        # Create loop device
        print(f"DEBUG: Creating loop device for {disk_path}")
        result = self.run_command(['sudo', 'losetup', '--find', '--show', disk_path])
        loop_device = result.stdout.strip()
        self.loop_devices.append(loop_device)

        print(f"DEBUG: Created loop device: {loop_device}")

        # Verify loop device was created successfully
        if not loop_device or not os.path.exists(loop_device):
            raise Exception(f"Failed to create loop device for {disk_path}")

        # Create partition table and partition using parted
        print(f"DEBUG: Creating partition table and partition on {loop_device}")
        self.run_command([
            'sudo', 'parted', loop_device, '--script',
            'mklabel', 'msdos',
            'mkpart', 'primary', 'ext4', '1MiB', '100%',
            'set', '1', 'boot', 'on'
        ])

        # Inform kernel about partition changes
        print(f"DEBUG: Running partprobe on {loop_device}")
        self.run_command(['sudo', 'partprobe', loop_device])

        # Additional verification after partitioning
        print(f"DEBUG: Verifying partition was created")
        try:
            # Check partition table
            partprobe_result = subprocess.run(['sudo', 'parted', loop_device, 'print'],
                                            capture_output=True, text=True)
            print(f"DEBUG: Partition table info:\n{partprobe_result.stdout}")
            if partprobe_result.stderr:
                print(f"DEBUG: parted stderr: {partprobe_result.stderr}")
        except Exception as e:
            print(f"ERROR: Cannot verify partition table: {e}")

        return loop_device
    
    def format_partition(self, loop_device: str) -> str:
        """
        Format the partition with ext4 filesystem.

        Args:
            loop_device: Path to the loop device

        Returns:
            Path to the partition device
        """
        partition_device = f"{loop_device}p1"

        print(f"Formatting partition: {partition_device}")

        # Check if loop device exists
        print(f"DEBUG: Checking if loop device exists: {loop_device}")
        if not os.path.exists(loop_device):
            print(f"ERROR: Loop device {loop_device} does not exist!")
            raise Exception(f"Loop device {loop_device} does not exist")

        # Check loop device permissions
        try:
            stat_info = os.stat(loop_device)
            print(f"DEBUG: Loop device permissions: {oct(stat_info.st_mode)}, owned by: {stat_info.st_uid}:{stat_info.st_gid}")
        except Exception as e:
            print(f"ERROR: Cannot stat loop device: {e}")

        # Check available loop devices
        try:
            result = subprocess.run(['losetup', '-l'], capture_output=True, text=True)
            print(f"DEBUG: Available loop devices:\n{result.stdout}")
        except Exception as e:
            print(f"ERROR: Cannot list loop devices: {e}")

        # Check if partition device already exists before waiting
        print(f"DEBUG: Checking if partition device already exists: {partition_device}")
        if os.path.exists(partition_device):
            print(f"DEBUG: Partition device already exists!")
            # Format with ext4
            self.run_command([
                'sudo', 'mkfs.ext4', '-F', partition_device
            ])
            return partition_device

        # Try partprobe first
        print(f"DEBUG: Running partprobe on {loop_device}")
        try:
            partprobe_result = subprocess.run(['sudo', 'partprobe', loop_device],
                                            capture_output=True, text=True)
            print(f"DEBUG: partprobe stdout: {partprobe_result.stdout}")
            print(f"DEBUG: partprobe stderr: {partprobe_result.stderr}")
            print(f"DEBUG: partprobe return code: {partprobe_result.returncode}")
        except Exception as e:
            print(f"ERROR: partprobe failed: {e}")

        # Wait for partition device to appear with more detailed logging
        print(f"DEBUG: Waiting for partition device {partition_device} to appear...")
        max_attempts = 15  # Increased from 10 to 15 seconds
        for i in range(max_attempts):
            print(f"DEBUG: Attempt {i+1}/{max_attempts}: Checking for {partition_device}")
            if os.path.exists(partition_device):
                print(f"DEBUG: SUCCESS! Partition device appeared after {i+1} seconds")
                break

            # Check if any partition devices exist for this loop device
            try:
                ls_result = subprocess.run(['ls', '-la', f"{loop_device}p*"],
                                         capture_output=True, text=True)
                if ls_result.stdout.strip():
                    print(f"DEBUG: Found partition devices:\n{ls_result.stdout}")
                else:
                    print(f"DEBUG: No partition devices found yet")
            except:
                pass

            time.sleep(1)
        else:
            # Partition device still didn't appear
            print(f"ERROR: Partition device {partition_device} did not appear after {max_attempts} seconds")

            # Additional diagnostic information
            try:
                print("DEBUG: Checking /dev/loop* devices:")
                ls_dev_result = subprocess.run(['ls', '-la', '/dev/loop*'],
                                             capture_output=True, text=True)
                print(ls_dev_result.stdout)
            except:
                pass

            try:
                print("DEBUG: Checking /proc/partitions:")
                cat_result = subprocess.run(['cat', '/proc/partitions'],
                                          capture_output=True, text=True)
                print(cat_result.stdout)
            except:
                pass

            raise Exception(f"Partition device {partition_device} did not appear after {max_attempts} seconds")

        # Format with ext4
        self.run_command([
            'sudo', 'mkfs.ext4', '-F', partition_device
        ])

        return partition_device
    
    def mount_partition(self, partition_device: str) -> str:
        """
        Mount the partition to a temporary directory.
        
        Args:
            partition_device: Path to the partition device
            
        Returns:
            Path to the mount point
        """
        mount_point = tempfile.mkdtemp(prefix='bootable_mount_')
        self.temp_dirs.append(mount_point)
        
        print(f"Mounting {partition_device} to {mount_point}")
        
        self.run_command(['sudo', 'mount', partition_device, mount_point])
        
        return mount_point
    
    def copy_rootfs(self, rootfs_dir: str, mount_point: str):
        """
        Copy the root filesystem to the mounted partition.
        
        Args:
            rootfs_dir: Source root filesystem directory
            mount_point: Mounted partition directory
        """
        print(f"Copying rootfs from {rootfs_dir} to {mount_point}")
        
        # Copy all files preserving permissions and ownership
        self.run_command([
            'sudo', 'cp', '-a', f'{rootfs_dir}/.', mount_point
        ])
        
        # Create necessary directories if they don't exist
        for directory in ['/boot', '/proc', '/sys', '/dev']:
            dir_path = os.path.join(mount_point, directory.lstrip('/'))
            self.run_command(['sudo', 'mkdir', '-p', dir_path], check=False)
    
    def install_kernel_and_bootloader(self, mount_point: str, loop_device: str):
        """
        Install kernel and GRUB bootloader in the mounted filesystem.
        
        Args:
            mount_point: Mounted partition directory
            loop_device: Loop device for bootloader installation
        """
        print("Installing kernel and bootloader")
        
        # Bind mount necessary filesystems for chroot
        for fs in ['/proc', '/sys', '/dev']:
            target = os.path.join(mount_point, fs.lstrip('/'))
            self.run_command(['sudo', 'mount', '--bind', fs, target])
        
        try:
            # Detect the distribution and install appropriate packages
            os_release_path = os.path.join(mount_point, 'etc/os-release')
            
            if os.path.exists(os_release_path):
                with open(os_release_path, 'r') as f:
                    os_release = f.read()
                
                if 'alpine' in os_release.lower():
                    self._install_alpine_kernel_bootloader(mount_point, loop_device)
                elif 'debian' in os_release.lower() or 'ubuntu' in os_release.lower():
                    self._install_debian_kernel_bootloader(mount_point, loop_device)
                else:
                    print("Warning: Unknown distribution, attempting generic installation")
                    self._install_generic_kernel_bootloader(mount_point, loop_device)
            else:
                print("Warning: No /etc/os-release found, attempting generic installation")
                self._install_generic_kernel_bootloader(mount_point, loop_device)
                
        finally:
            # Unmount bind mounts
            for fs in ['/dev', '/sys', '/proc']:
                target = os.path.join(mount_point, fs.lstrip('/'))
                self.run_command(['sudo', 'umount', target], check=False)
    
    def _install_alpine_kernel_bootloader(self, mount_point: str, loop_device: str):
        """Install kernel and bootloader for Alpine Linux."""
        print("Installing Alpine Linux kernel and bootloader")
        
        # Update package index and install kernel
        chroot_commands = [
            ['apk', 'update'],
            ['apk', 'add', 'linux-lts', 'grub', 'grub-bios'],
            ['grub-install', '--target=i386-pc', f'--boot-directory=/boot', loop_device],
            ['grub-mkconfig', '-o', '/boot/grub/grub.cfg']
        ]
        
        for cmd in chroot_commands:
            self.run_command(['sudo', 'chroot', mount_point] + cmd, check=False)
    
    def _install_debian_kernel_bootloader(self, mount_point: str, loop_device: str):
        """Install kernel and bootloader for Debian/Ubuntu."""
        print("Installing Debian/Ubuntu kernel and bootloader")
        
        # Update package index and install kernel
        chroot_commands = [
            ['apt-get', 'update'],
            ['apt-get', 'install', '-y', 'linux-image-generic', 'grub-pc'],
            ['grub-install', '--target=i386-pc', f'--boot-directory=/boot', loop_device],
            ['update-grub']
        ]
        
        for cmd in chroot_commands:
            self.run_command(['sudo', 'chroot', mount_point] + cmd, check=False)
    
    def _install_generic_kernel_bootloader(self, mount_point: str, loop_device: str):
        """Generic kernel and bootloader installation."""
        print("Attempting generic kernel and bootloader installation")
        
        # Try to install a basic kernel and bootloader
        # This is a fallback that may not work for all distributions
        kernel_path = os.path.join(mount_point, 'boot')
        
        # Create a basic GRUB configuration
        grub_dir = os.path.join(mount_point, 'boot/grub')
        self.run_command(['sudo', 'mkdir', '-p', grub_dir])
        
        grub_cfg = """
set default=0
set timeout=5

menuentry "Linux" {
    linux /boot/vmlinuz root=/dev/sda1 ro
    initrd /boot/initrd.img
}
"""
        
        grub_cfg_path = os.path.join(grub_dir, 'grub.cfg')
        with open('/tmp/grub.cfg', 'w') as f:
            f.write(grub_cfg)
        
        self.run_command(['sudo', 'cp', '/tmp/grub.cfg', grub_cfg_path])
        
        # Try to install GRUB
        self.run_command([
            'sudo', 'grub-install', '--target=i386-pc', 
            f'--boot-directory={kernel_path}', loop_device
        ], check=False)
    
    def unmount_and_cleanup(self, mount_point: str):
        """
        Unmount the partition and clean up.
        
        Args:
            mount_point: Mount point to unmount
        """
        print(f"Unmounting {mount_point}")
        
        self.run_command(['sudo', 'umount', mount_point], check=False)
    
    def convert_to_bootable_image(self, rootfs_dir: str, output_path: str) -> str:
        """
        Convert a Docker root filesystem to a bootable disk image.
        
        Args:
            rootfs_dir: Path to the extracted Docker root filesystem
            output_path: Path where the bootable image should be created
            
        Returns:
            Path to the created bootable image
        """
        try:
            print(f"Converting {rootfs_dir} to bootable image {output_path}")
            
            # Step 1: Create disk image
            self.create_disk_image(output_path)
            
            # Step 2: Partition the disk
            loop_device = self.partition_disk(output_path)
            
            # Step 3: Format the partition
            partition_device = self.format_partition(loop_device)
            
            # Step 4: Mount the partition
            mount_point = self.mount_partition(partition_device)
            
            # Step 5: Copy root filesystem
            self.copy_rootfs(rootfs_dir, mount_point)
            
            # Step 6: Install kernel and bootloader
            self.install_kernel_and_bootloader(mount_point, loop_device)
            
            # Step 7: Unmount and cleanup
            self.unmount_and_cleanup(mount_point)
            
            print(f"Successfully created bootable image: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error during conversion: {str(e)}")
            raise
        finally:
            self.cleanup()


def test_image_converter():
    """Test function for the image converter."""
    # This would require a root filesystem to test with
    print("Image converter module loaded successfully")
    print("Note: Full testing requires root filesystem and sudo privileges")


if __name__ == '__main__':
    test_image_converter()