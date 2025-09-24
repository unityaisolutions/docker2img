# Docker Deployment Guide

This guide explains how to deploy the Docker to Bootable Image Converter using Docker containers.

## 🐳 Quick Start with Docker

### Option 1: Using Docker Compose (Recommended)

1. **Build and start the application:**
   ```bash
   docker-compose up --build
   ```

2. **Access the application:**
   Open `http://localhost:7860` in your browser

3. **Stop the application:**
   ```bash
   docker-compose down
   ```

### Option 2: Using Docker directly

1. **Build the image:**
   ```bash
   docker build -t docker-to-bootable .
   ```

2. **Run the container:**
   ```bash
   docker run -d \
     --name docker-to-bootable-converter \
     --privileged \
     -p 7860:7860 \
     -v $(pwd)/output:/app/output \
     docker-to-bootable
   ```

3. **Stop the container:**
   ```bash
   docker stop docker-to-bootable-converter
   docker rm docker-to-bootable-converter
   ```

## 🔧 Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GRADIO_SERVER_NAME` | `0.0.0.0` | Server bind address |
| `GRADIO_SERVER_PORT` | `7860` | Server port |
| `PYTHONUNBUFFERED` | `1` | Disable Python output buffering |

### Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `./output` | `/app/output` | Generated bootable images |
| `./temp` | `/tmp/conversion_temp` | Temporary conversion files |

### Required Privileges

The container requires elevated privileges for disk operations:

- **`--privileged`**: Full access to host devices
- **`SYS_ADMIN`**: Mount/unmount operations
- **`MKNOD`**: Create device nodes
- **Loop devices**: Access to `/dev/loop*` for disk image mounting

## 🚀 Production Deployment

### Using Docker Swarm

1. **Initialize swarm (if not already done):**
   ```bash
   docker swarm init
   ```

2. **Deploy the stack:**
   ```bash
   docker stack deploy -c docker-compose.yml docker-to-bootable
   ```

### Using Kubernetes

Create a deployment manifest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docker-to-bootable
spec:
  replicas: 1
  selector:
    matchLabels:
      app: docker-to-bootable
  template:
    metadata:
      labels:
        app: docker-to-bootable
    spec:
      containers:
      - name: docker-to-bootable
        image: docker-to-bootable:latest
        ports:
        - containerPort: 7860
        securityContext:
          privileged: true
        volumeMounts:
        - name: output
          mountPath: /app/output
        - name: dev
          mountPath: /dev
      volumes:
      - name: output
        hostPath:
          path: /opt/docker-to-bootable/output
      - name: dev
        hostPath:
          path: /dev
---
apiVersion: v1
kind: Service
metadata:
  name: docker-to-bootable-service
spec:
  selector:
    app: docker-to-bootable
  ports:
  - port: 80
    targetPort: 7860
  type: LoadBalancer
```

## 🔒 Security Considerations

### Privileged Mode Requirements

This application requires privileged mode because it:
- Creates and mounts loop devices
- Performs disk partitioning operations
- Installs bootloaders on disk images
- Executes `chroot` operations

### Security Best Practices

1. **Network Isolation:**
   ```bash
   docker network create --driver bridge docker-to-bootable-net
   ```

2. **Resource Limits:**
   ```yaml
   deploy:
     resources:
       limits:
         memory: 4G
         cpus: '2.0'
   ```

3. **Read-only Root Filesystem:**
   ```yaml
   read_only: true
   tmpfs:
     - /tmp
     - /var/tmp
   ```

4. **User Namespace Remapping:**
   Configure Docker daemon with user namespace remapping for additional security.

## 🐛 Troubleshooting

### Common Issues

**Container fails to start:**
```bash
# Check logs
docker-compose logs docker-to-bootable

# Common solutions:
# 1. Ensure Docker daemon has privileged access
# 2. Check if loop devices are available on host
# 3. Verify sufficient disk space
```

**Permission denied errors:**
```bash
# Ensure container runs with proper privileges
docker run --privileged ...

# Or add specific capabilities
docker run --cap-add SYS_ADMIN --cap-add MKNOD ...
```

**Loop device not available:**
```bash
# Load loop module on host
sudo modprobe loop

# Create additional loop devices if needed
sudo mknod /dev/loop8 b 7 8
```

### Health Checks

Monitor container health:
```bash
# Check health status
docker ps

# View health check logs
docker inspect docker-to-bootable-converter | grep Health -A 10
```

## 📊 Monitoring and Logging

### Container Logs
```bash
# Follow logs in real-time
docker-compose logs -f docker-to-bootable

# View specific number of log lines
docker-compose logs --tail=100 docker-to-bootable
```

### Resource Monitoring
```bash
# Monitor resource usage
docker stats docker-to-bootable-converter

# Detailed container information
docker inspect docker-to-bootable-converter
```

## 🔄 Updates and Maintenance

### Updating the Application
```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose up --build -d
```

### Backup and Restore
```bash
# Backup output directory
tar -czf docker-to-bootable-backup.tar.gz output/

# Restore from backup
tar -xzf docker-to-bootable-backup.tar.gz
```

## 🌐 Reverse Proxy Setup

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:7860;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for Gradio
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Traefik Configuration
```yaml
version: '3.8'
services:
  docker-to-bootable:
    # ... existing configuration ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.docker-to-bootable.rule=Host(`your-domain.com`)"
      - "traefik.http.services.docker-to-bootable.loadbalancer.server.port=7860"
```

This Docker deployment provides a robust, scalable solution for running the Docker to Bootable Image Converter in containerized environments.