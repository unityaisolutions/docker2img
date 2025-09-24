# Docker to Bootable Image Converter

A sophisticated Gradio web application that converts Docker registry images into bootable disk images (.img files). This tool bridges the gap between containerized applications and traditional bootable systems.

## Features

- **Web Interface**: Beautiful, responsive Gradio interface with custom CSS styling
- **Registry Support**: Works with Docker Hub, private registries, and multi-platform images
- **Authentication**: Support for private registry credentials
- **Multi-Architecture**: Supports linux/amd64, linux/arm64, linux/386, and linux/arm/v7
- **Flexible Output**: Configurable disk image sizes from 512MB to 8GB
- **Progress Tracking**: Real-time conversion progress with detailed status updates
- **Error Handling**: Comprehensive error reporting and validation
- **Docker Deployment**: Containerized deployment with all dependencies included

## How It Works

1. **Registry Connection**: Connects to the specified Docker registry using the DXF library
2. **Layer Download**: Downloads all image layers for the specified platform
3. **Filesystem Assembly**: Extracts and combines layers to create a complete root filesystem
4. **Disk Creation**: Creates a disk image file with proper partitioning
5. **Bootloader Installation**: Installs Linux kernel and GRUB bootloader
6. **Image Generation**: Produces a bootable .img file ready for use

## Quick Start

### 🐳 Docker Deployment (Recommended)

The easiest way to run the application is using Docker, which automatically handles all system dependencies:

```bash
# Clone or download the application files
# Then run with Docker Compose:
docker-compose up --build

# Access the application at http://localhost:7860
```

**Alternative Docker command:**
```bash
docker build -t docker-to-bootable .
docker run -d --privileged -p 7860:7860 -v $(pwd)/output:/app/output docker-to-bootable
```

### 🖥️ Native Installation

If you prefer to run natively on your system:

#### System Dependencies
```bash
sudo apt-get update
sudo apt-get install -y parted grub-pc-bin grub-common kpartx
```

#### Python Dependencies
```bash
pip3 install -r requirements.txt
```

#### Start the Application
```bash
./start_app.sh
# Or directly: python3 app.py
```

## Usage

### Using the Web Interface

1. **Enter Docker Image URL**:
   - For Docker Hub: `alpine:latest`, `ubuntu:20.04`, `nginx:latest`
   - For private registries: `registry.company.com/user/image:tag`

2. **Provide Credentials** (if needed):
   - Username and password for private registries
   - Leave blank for public images

3. **Select Platform**:
   - Choose target architecture (default: linux/amd64)
   - Important for multi-architecture images

4. **Set Disk Size**:
   - Minimum: 512MB
   - Recommended: 2GB or larger
   - Adjust based on image size and intended use

5. **Convert**:
   - Click "Convert to Bootable Image"
   - Monitor progress in real-time
   - Download the generated .img file

### Example Images to Try

| Image | Description | Recommended Size |
|-------|-------------|------------------|
| `alpine:latest` | Minimal Linux distribution | 1GB |
| `debian:bullseye-slim` | Debian base system | 2GB |
| `ubuntu:20.04` | Ubuntu LTS | 3GB |
| `centos:7` | CentOS base | 2GB |

## Deployment Options

### Docker Compose (Production Ready)
```yaml
version: '3.8'
services:
  docker-to-bootable:
    build: .
    ports:
      - "7860:7860"
    privileged: true
    volumes:
      - ./output:/app/output
    restart: unless-stopped
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docker-to-bootable
spec:
  template:
    spec:
      containers:
      - name: docker-to-bootable
        image: docker-to-bootable:latest
        securityContext:
          privileged: true
```

See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for detailed deployment instructions.

## Supported Distributions

The converter works best with images containing complete Linux userlands:

- ✅ **Alpine Linux** - Excellent support with APK package manager
- ✅ **Debian/Ubuntu** - Full support with APT package manager  
- ✅ **CentOS/RHEL** - Good support with YUM/DNF
- ⚠️ **Other distributions** - May work with generic bootloader installation

## Output Usage

The generated `.img` files can be used in several ways:

### Virtual Machines
```bash
# QEMU
qemu-system-x86_64 -hda output.img -m 1024

# VirtualBox
# Import as a raw disk image
```

### Physical Media
```bash
# Write to USB drive (replace /dev/sdX with actual device)
sudo dd if=output.img of=/dev/sdX bs=4M status=progress
```

### Cloud Platforms
- Upload to cloud providers that support custom images
- Convert to other formats (VMDK, VHD) using `qemu-img`

## Architecture

### Core Components

1. **`docker_registry.py`**: Docker Registry API client
   - Handles authentication and image manifest parsing
   - Downloads and extracts image layers
   - Supports multi-platform images

2. **`image_converter.py`**: Bootable image creation
   - Disk partitioning and formatting
   - Filesystem copying and kernel installation
   - GRUB bootloader configuration

3. **`app.py`**: Gradio web interface
   - User input handling and validation
   - Progress tracking and error reporting
   - File download management

4. **`custom_style.css`**: Professional styling
   - Modern, responsive design
   - Custom color scheme and animations
   - Enhanced user experience

### Conversion Process

```
Docker Image → Registry API → Layer Download → Filesystem Assembly → Disk Creation → Bootloader Installation → Bootable Image
```

## Requirements

### Docker Deployment
- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM (recommended)
- 10GB free disk space

### Native Installation
- Ubuntu 20.04+ or similar Linux distribution
- Python 3.8+
- Sudo privileges
- System packages: `parted`, `grub-pc-bin`, `grub-common`, `kpartx`

## Troubleshooting

### Common Issues

**"Permission denied" errors**:
- Ensure the application runs with privileged access
- For Docker: use `--privileged` flag
- For native: run with sudo privileges

**"Image not found" errors**:
- Verify the image URL is correct
- Check registry credentials for private images
- Ensure the specified platform is available

**"Conversion failed" errors**:
- Increase disk image size
- Check available disk space
- Verify the source image contains a complete Linux system

### Docker-Specific Issues

**Container fails to start**:
```bash
# Check logs
docker-compose logs docker-to-bootable

# Ensure privileged mode is enabled
docker run --privileged ...
```

**Loop device not available**:
```bash
# Load loop module on host
sudo modprobe loop
```

## Security Considerations

- **Privileged Access**: Required for disk operations and bootloader installation
- **Registry Credentials**: Handled securely, not logged or stored
- **Temporary Files**: Automatically cleaned up after conversion
- **Input Validation**: All user inputs are validated before processing
- **Container Security**: Use resource limits and network isolation in production

## Files Included

- `app.py` - Main Gradio application
- `docker_registry.py` - Docker Registry API client
- `image_converter.py` - Bootable image creation logic
- `custom_style.css` - Web interface styling
- `Dockerfile` - Container build configuration
- `docker-compose.yml` - Multi-container deployment
- `requirements.txt` - Python dependencies
- `start_app.sh` - Native startup script
- `test_conversion.py` - Test suite
- `README.md` - This documentation
- `DOCKER_DEPLOYMENT.md` - Detailed Docker deployment guide

## Contributing

This application demonstrates advanced integration of:
- Docker Registry API interaction
- Linux system administration
- Web interface development
- File system manipulation
- Container orchestration

Feel free to extend the functionality or adapt for specific use cases.

## License

This project is provided as-is with the Apache 2.0 license for practical use. Please ensure compliance with Docker image licenses and registry terms of service.