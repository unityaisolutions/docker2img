# Docker to Bootable Image Converter - Agent Context

## Build & Test

```bash
# Native development
pip install -r requirements.txt
python app.py

# Docker development
docker-compose up --build

# Test conversion
python test_conversion.py

# Run with sudo for disk operations
sudo python app.py
```

Access at http://localhost:7860

## Architecture Overview

Web interface (`app.py`) orchestrates Docker registry client (`docker_registry.py`) to download/extract image layers, then disk converter (`image_converter.py`) creates partitioned bootable images with GRUB bootloader. Requires privileged access for loop devices and filesystem operations.

## Security

- **Privileged Operations**: Requires sudo for disk partitioning, mounting, loop devices
- **Registry Credentials**: Username/password handled via DXF library, not logged
- **Temp Files**: Auto-cleanup in `/tmp` after conversion
- **Container Security**: Uses `--privileged` flag for Docker deployment
- **No API Keys**: Direct registry API access, no external services

## Git Workflows

- **Branch Strategy**: Feature branches from main
- **Commit Format**: Conventional commits (`feat:`, `fix:`, `docs:`)
- **File Changes**: Test locally before committing due to sudo requirements

## Conventions & Patterns

- **Structure**: 
  - `app.py` - Gradio interface and orchestration
  - `docker_registry.py` - Registry API and layer handling  
  - `image_converter.py` - Disk operations and bootloader
- **Naming**: Snake_case for functions, PascalCase for classes
- **Error Handling**: Comprehensive try/catch with cleanup in finally blocks
- **Temp Management**: Track temp dirs/loop devices for proper cleanup
- **Progress Tracking**: Use Gradio progress parameter for user feedback
- **Platform Support**: linux/amd64, linux/arm64, linux/386, linux/arm/v7