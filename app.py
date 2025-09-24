"""
Docker to Bootable Image Converter - Gradio Application

A web interface for converting Docker registry images to bootable .img files.
"""

import gradio as gr
import os
import tempfile
import traceback
from typing import Optional, Tuple
import threading
import time

from docker_registry import DockerRegistryClient
from image_converter import ImageConverter


class DockerToBootableApp:
    """Main application class for the Docker to Bootable Image converter."""
    
    def __init__(self):
        self.current_conversion = None
        self.conversion_lock = threading.Lock()
    
    def convert_docker_image(
        self, 
        image_url: str, 
        username: str = "", 
        password: str = "", 
        platform: str = "linux/amd64",
        image_size_mb: int = 2048,
        progress=gr.Progress()
    ) -> Tuple[str, Optional[str]]:
        """
        Convert a Docker image to a bootable disk image.
        
        Args:
            image_url: Docker image URL (e.g., 'alpine:latest' or 'registry.com/user/image:tag')
            username: Optional username for private registries
            password: Optional password for private registries
            platform: Platform architecture (default: linux/amd64)
            image_size_mb: Size of the output disk image in MB
            progress: Gradio progress tracker
            
        Returns:
            Tuple of (status_message, output_file_path)
        """
        with self.conversion_lock:
            try:
                progress(0, desc="Starting conversion...")
                
                # Validate inputs
                if not image_url.strip():
                    return "❌ Error: Please provide a Docker image URL", None
                
                if image_size_mb < 512:
                    return "❌ Error: Image size must be at least 512MB", None
                
                # Parse the image URL
                try:
                    registry_url, repository, tag = DockerRegistryClient.parse_image_url(image_url.strip())
                    progress(0.1, desc=f"Parsed image: {registry_url}/{repository}:{tag}")
                except Exception as e:
                    return f"❌ Error parsing image URL: {str(e)}", None
                
                # Create registry client
                try:
                    client = DockerRegistryClient(
                        registry_url=registry_url,
                        repository=repository,
                        username=username.strip() if username.strip() else None,
                        password=password.strip() if password.strip() else None
                    )
                    progress(0.2, desc="Connected to registry")
                except Exception as e:
                    return f"❌ Error connecting to registry: {str(e)}", None
                
                # Get image information
                try:
                    image_info = client.get_image_info(tag)
                    progress(0.25, desc=f"Found image with {image_info['layer_count']} layers")
                except Exception as e:
                    return f"❌ Error getting image info: {str(e)}", None
                
                # Download layers
                try:
                    temp_layers_dir = tempfile.mkdtemp(prefix='docker_layers_')
                    progress(0.3, desc="Downloading image layers...")
                    
                    layers = client.download_all_layers(tag, temp_layers_dir, platform)
                    progress(0.6, desc=f"Downloaded {len(layers)} layers")
                except Exception as e:
                    return f"❌ Error downloading layers: {str(e)}", None
                
                # Extract layers to root filesystem
                try:
                    temp_rootfs_dir = tempfile.mkdtemp(prefix='docker_rootfs_')
                    progress(0.7, desc="Extracting layers to filesystem...")
                    
                    client.extract_layers_to_rootfs(layers, temp_rootfs_dir)
                    progress(0.8, desc="Filesystem extraction complete")
                except Exception as e:
                    return f"❌ Error extracting filesystem: {str(e)}", None
                
                # Convert to bootable image
                try:
                    output_filename = f"{repository.replace('/', '_')}_{tag}_bootable.img"
                    output_path = os.path.join('/tmp', output_filename)
                    
                    progress(0.85, desc="Creating bootable disk image...")
                    
                    converter = ImageConverter(image_size_mb=image_size_mb)
                    converter.convert_to_bootable_image(temp_rootfs_dir, output_path)
                    
                    progress(1.0, desc="Conversion complete!")
                    
                    # Verify the output file exists and has reasonable size
                    if os.path.exists(output_path):
                        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                        return (
                            f"✅ Success! Created bootable image: {output_filename} ({file_size_mb:.1f}MB)",
                            output_path
                        )
                    else:
                        return "❌ Error: Output file was not created", None
                        
                except Exception as e:
                    return f"❌ Error creating bootable image: {str(e)}", None
                
            except Exception as e:
                error_msg = f"❌ Unexpected error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
                return error_msg, None
    
    def create_interface(self):
        """Create and configure the Gradio interface."""
        
        # Load custom CSS
        css_path = os.path.join(os.path.dirname(__file__), 'custom_style.css')
        custom_css = ""
        if os.path.exists(css_path):
            with open(css_path, 'r') as f:
                custom_css = f.read()
        
        with gr.Blocks(
            title="Docker to Bootable Image Converter",
            css=custom_css,
            theme=gr.themes.Soft()
        ) as interface:
            
            # Header
            gr.HTML("""
                <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; margin-bottom: 2rem; border-radius: 12px;">
                    <h1 style="margin: 0; font-size: 2.5rem; font-weight: 700;">🐳 ➡️ 💿</h1>
                    <h2 style="margin: 0.5rem 0 0 0; font-size: 2rem;">Docker to Bootable Image Converter</h2>
                    <p style="margin: 0.5rem 0 0 0; font-size: 1.1rem; opacity: 0.9;">Convert Docker registry images to bootable disk images</p>
                </div>
            """)
            
            with gr.Row():
                with gr.Column(scale=2):
                    # Input section
                    gr.Markdown("### 📥 Image Configuration")
                    
                    image_url = gr.Textbox(
                        label="Docker Image URL",
                        placeholder="e.g., alpine:latest, ubuntu:20.04, registry.com/user/image:tag",
                        info="Enter the full Docker image URL or just image:tag for Docker Hub images"
                    )
                    
                    with gr.Row():
                        username = gr.Textbox(
                            label="Username (optional)",
                            placeholder="Registry username",
                            type="text"
                        )
                        password = gr.Textbox(
                            label="Password (optional)",
                            placeholder="Registry password",
                            type="password"
                        )
                    
                    with gr.Row():
                        platform = gr.Dropdown(
                            choices=["linux/amd64", "linux/arm64", "linux/386", "linux/arm/v7"],
                            value="linux/amd64",
                            label="Platform Architecture",
                            info="Select the target platform for multi-arch images"
                        )
                        
                        image_size = gr.Slider(
                            minimum=512,
                            maximum=8192,
                            value=2048,
                            step=256,
                            label="Disk Image Size (MB)",
                            info="Size of the output bootable disk image"
                        )
                    
                    convert_btn = gr.Button(
                        "🚀 Convert to Bootable Image",
                        variant="primary",
                        size="lg"
                    )
                
                with gr.Column(scale=1):
                    # Information panel
                    gr.Markdown("### ℹ️ How it works")
                    gr.Markdown("""
                    1. **Connect** to the Docker registry
                    2. **Download** all image layers
                    3. **Extract** layers to create root filesystem
                    4. **Create** disk image and partition
                    5. **Install** kernel and bootloader
                    6. **Generate** bootable .img file
                    
                    **Supported Images:**
                    - Alpine Linux
                    - Debian/Ubuntu
                    - Most Linux distributions
                    
                    **Requirements:**
                    - Images must contain a complete Linux userland
                    - Minimum 512MB disk space
                    """)
            
            # Output section
            gr.Markdown("### 📤 Conversion Results")
            
            status_output = gr.Textbox(
                label="Status",
                placeholder="Conversion status will appear here...",
                lines=3,
                interactive=False
            )
            
            file_output = gr.File(
                label="Download Bootable Image",
                visible=False
            )
            
            # Examples
            gr.Markdown("### 💡 Example Images to Try")
            gr.Examples(
                examples=[
                    ["alpine:latest", "", "", "linux/amd64", 1024],
                    ["debian:bullseye-slim", "", "", "linux/amd64", 2048],
                    ["ubuntu:20.04", "", "", "linux/amd64", 3072],
                ],
                inputs=[image_url, username, password, platform, image_size],
                label="Click an example to load it"
            )
            
            # Event handlers
            def handle_conversion(*args):
                status, file_path = self.convert_docker_image(*args)
                if file_path and os.path.exists(file_path):
                    return status, gr.File(value=file_path, visible=True)
                else:
                    return status, gr.File(visible=False)
            
            convert_btn.click(
                fn=handle_conversion,
                inputs=[image_url, username, password, platform, image_size],
                outputs=[status_output, file_output],
                show_progress=True
            )
            
            # Footer
            gr.HTML("""
                <div style="text-align: center; padding: 1rem; margin-top: 2rem; border-top: 1px solid #e2e8f0; color: #64748b;">
                    <p>⚠️ <strong>Note:</strong> This tool requires sudo privileges for disk operations. Generated images can be used with VMs or written to physical media.</p>
                    <p>Built with ❤️ using Gradio • Docker Registry API • Linux Tools</p>
                </div>
            """)
        
        return interface


def main():
    """Main function to run the application."""
    app = DockerToBootableApp()
    interface = app.create_interface()
    
    # Launch the interface
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )


if __name__ == "__main__":
    main()