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
        # Detach loop devices and remove any kpartx mappings
        for loop_device in self.loop_devices:
            try:
                subprocess.run(['sudo', 'kpartx', '-d', loop_device],
                               check=False, capture_output=True, text=True)
            except:
                pass
            try:
                subprocess.run(['sudo', 'losetup', '-d', loop_device],
                               check=False, capture_output=True, text=True)
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

        # Create loop device with retry logic
        print(f"DEBUG: Creating loop device for {disk_path}")
        loop_device = None
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                result = self.run_command(['sudo', 'losetup', '--find', '--show', '--partscan', disk_path])
                loop_device = result.stdout.strip()
                
                if loop_device and os.path.exists(loop_device):
                    self.loop_devices.append(loop_device)
                    print(f"DEBUG: Created loop device: {loop_device}")
                    break
                else:
                    print(f"DEBUG: Attempt {attempt + 1}: Loop device creation returned '{loop_device}' but device doesn't exist")
                    
            except Exception as e:
                print(f"DEBUG: Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                import time
                time.sleep(1)
        
        if not loop_device or not os.path.exists(loop_device):
            raise Exception(f"Failed to create loop device for {disk_path} after {max_retries} attempts")

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

        # Force kernel to re-read the partition table and wait for udev
        print(f"DEBUG: Forcing kernel to re-read partition table on {loop_device}")
        self.run_command(['sudo', 'losetup', '-c', loop_device], check=False)
        print("DEBUG: Waiting for udev to settle")
        self.run_command(['sudo', 'udevadm', 'settle', '--timeout=10'], check=False)

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

    def _wait_for_partition_device(self, loop_device: str, partition_number: int = 1, timeout: int = 60) -> str:
        """
        Wait up to 'timeout' seconds for the partition device to appear.
        Returns the path to the partition device (e.g., /dev/loop0p1 or /dev/mapper/loop0p1).
        """
        base = os.path.basename(loop_device)
        expected = f"{loop_device}p{partition_number}"
        mapper = f"/dev/mapper/{base}p{partition_number}"

        print(f"DEBUG: Waiting up to {timeout}s for partition device to appear (expected: {expected}, fallback: {mapper})")

        if os.path.exists(expected):
            print(f"DEBUG: Found partition device immediately: {expected}")
            return expected
        if os.path.exists(mapper):
            print(f"DEBUG: Found mapper partition device immediately: {mapper}")
            return mapper

        start = time.time()
        attempted_kpartx = False
        last_trigger = 0.0

        while True:
            if os.path.exists(expected):
                print(f"DEBUG: Found partition device: {expected}")
                return expected
            if os.path.exists(mapper):
                print(f"DEBUG: Found mapper partition device: {mapper}")
                return mapper

            # Check via lsblk to catch any alternate paths
            try:
                lsblk = subprocess.run(['lsblk', '-pnro', 'NAME,TYPE', loop_device],
                                       capture_output=True, text=True)
                for line in lsblk.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) == 2:
                        name, typ = parts
                        if typ == 'part':
                            if name.endswith(f"p{partition_number}") and os.path.exists(name):
                                print(f"DEBUG: Detected partition via lsblk: {name}")
                                return name
            except Exception as e:
                print(f"DEBUG: lsblk check failed: {e}")

            elapsed = time.time() - start

            # Periodically trigger re-read and wait for udev
            if elapsed - last_trigger >= 3:
                try:
                    self.run_command(['sudo', 'partprobe', loop_device], check=False)
                except Exception:
                    pass
                try:
                    self.run_command(['sudo', 'losetup', '-c', loop_device], check=False)
                except Exception:
                    pass
                try:
                    self.run_command(['sudo', 'blockdev', '--rereadpt', loop_device], check=False)
                except Exception:
                    pass
                try:
                    self.run_command(['sudo', 'udevadm', 'settle', '--timeout=10'], check=False)
                except Exception:
                    pass
                last_trigger = elapsed

            # Fallback to kpartx after a short delay
            if not attempted_kpartx and elapsed >= 10:
                print("DEBUG: Using kpartx to create device-mapper partitions as fallback")
                try:
                    self.run_command(['sudo', 'kpartx', '-a', '-s', loop_device], check=False)
                    try:
                        self.run_command(['sudo', 'udevadm', 'settle', '--timeout=10'], check=False)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"DEBUG: kpartx failed: {e}")
                attempted_kpartx = True

            if elapsed >= timeout:
                break

            time.sleep(1)

        # Diagnostics
        print(f"ERROR: Partition devices did not appear within {timeout}s for loop device {loop_device}")
        try:
            print("DEBUG: lsblk -f output:")
            lb = subprocess.run(['lsblk', '-f'], capture_output=True, text=True)
            print(lb.stdout)
        except Exception:
            pass
        try:
            print("DEBUG: /proc/partitions:")
            with open('/proc/partitions') as f:
                print(f.read())
        except Exception:
            pass

        raise Exception(f"Partition device {expected} did not appear after {int(timeout)} seconds")

    def format_partition(self, loop_device: str) -> str:
        """
        Format the partition with ext4 filesystem.

        Args:
            loop_device: Path to the loop device

        Returns:
            Path to the partition device
        """
        print(f"Formatting partition for loop device: {loop_device}")

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

        # Robust wait for the partition device to appear
        partition_device = self._wait_for_partition_device(loop_device, partition_number=1, timeout=60)
        print(f"DEBUG: Using partition device: {partition_device}")

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