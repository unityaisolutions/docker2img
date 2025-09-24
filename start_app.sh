# Docker to Bootable Image Converter - Startup Script
# This script sets up and starts the Gradio application

set -e

echo "🐳 ➡️ 💿 Docker to Bootable Image Converter"
echo "=========================================="

# Check if running as root (required for disk operations)
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  Warning: This application requires sudo privileges for disk operations."
    echo "   Some features may not work without elevated permissions."
    echo ""
fi

# Check system dependencies
echo "📋 Checking system dependencies..."

MISSING_DEPS=()

if ! command -v parted &> /dev/null; then
    MISSING_DEPS+=("parted")
fi

if ! command -v grub-install &> /dev/null; then
    MISSING_DEPS+=("grub-pc-bin")
fi

if ! command -v kpartx &> /dev/null; then
    MISSING_DEPS+=("kpartx")
fi

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo "❌ Missing system dependencies: ${MISSING_DEPS[*]}"
    echo "   Please install them with:"
    echo "   sudo apt-get update && sudo apt-get install -y ${MISSING_DEPS[*]}"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ All system dependencies found"
fi

# Check Python dependencies
echo "🐍 Checking Python dependencies..."

PYTHON_DEPS=("gradio" "python-dxf")
MISSING_PYTHON_DEPS=()

for dep in "${PYTHON_DEPS[@]}"; do
    if ! python3 -c "import ${dep//-/_}" &> /dev/null; then
        MISSING_PYTHON_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_PYTHON_DEPS[@]} -ne 0 ]; then
    echo "❌ Missing Python dependencies: ${MISSING_PYTHON_DEPS[*]}"
    echo "   Installing them now..."
    pip3 install "${MISSING_PYTHON_DEPS[@]}"
else
    echo "✅ All Python dependencies found"
fi

# Check available disk space
echo "💾 Checking available disk space..."
AVAILABLE_SPACE=$(df /tmp | awk 'NR==2 {print $4}')
AVAILABLE_GB=$((AVAILABLE_SPACE / 1024 / 1024))

if [ $AVAILABLE_GB -lt 5 ]; then
    echo "⚠️  Warning: Low disk space in /tmp (${AVAILABLE_GB}GB available)"
    echo "   Conversions may fail for large images"
else
    echo "✅ Sufficient disk space available (${AVAILABLE_GB}GB)"
fi

echo ""
echo "🚀 Starting the application..."
echo "   Access the web interface at: http://localhost:7860"
echo "   Press Ctrl+C to stop the application"
echo ""

# Start the application
cd "$(dirname "$0")"
python3 app.py