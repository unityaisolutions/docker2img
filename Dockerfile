# Docker to Bootable Image Converter
# Dockerfile for containerized deployment

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Core system tools
    python3 \
    python3-pip \
    python3-dev \
    curl \
    wget \
    sudo \
    # Disk and partition management tools
    parted \
    fdisk \
    kpartx \
    util-linux \
    # Filesystem tools
    e2fsprogs \
    dosfstools \
    # Bootloader and kernel tools
    grub-pc-bin \
    grub-common \
    grub2-common \
    # Archive and compression tools
    tar \
    gzip \
    # Process and system utilities
    psmisc \
    procps \
    # Clean up package cache
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user with sudo privileges
RUN useradd -m -s /bin/bash appuser && \
    echo "appuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Copy Python requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY docker_registry.py .
COPY image_converter.py .
COPY custom_style.css .
COPY start_app.sh .
COPY test_conversion.py .
COPY README.md .

# Make scripts executable
RUN chmod +x start_app.sh

# Create necessary directories
RUN mkdir -p /tmp/docker_layers /tmp/docker_rootfs /tmp/bootable_images

# Set proper ownership
RUN chown -R appuser:appuser /app /tmp/docker_layers /tmp/docker_rootfs /tmp/bootable_images

# Switch to non-root user
USER appuser

# Expose the Gradio port
EXPOSE 7860

# Health check to ensure the application is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# Set environment variables
ENV PYTHONPATH=/app
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Default command
CMD ["python3", "app.py"]
