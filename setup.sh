#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "🚀 Starting SortSense Setup for Linux/macOS..."

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 and try again."
    exit 1
fi

# 2. Virtual Environment Setup
echo "📦 Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install dependencies
echo "📥 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Check Ollama
echo "🔍 Checking for Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "⚠️ Ollama is not installed."
    read -p "Would you like to install Ollama now? (requires sudo) [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "❌ Ollama is required. Please install it manually from https://ollama.com and run this script again."
        exit 1
    fi
fi

# 4. Start Ollama and Pull Model
echo "🧠 Checking if Ollama daemon is running..."
if ! curl -s http://localhost:11434/ > /dev/null; then
    echo "⚙️ Starting Ollama daemon in the background..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3 # Give it a moment to boot
fi

MODEL_NAME="gemma4:e4b"
echo "📥 Ensuring the model '$MODEL_NAME' is pulled (this might take a while if downloading)..."
ollama pull "$MODEL_NAME" || {
    echo "⚠️ Note: Failed to pull '$MODEL_NAME'. If this is a custom local tag, make sure it exists."
}

echo ""
echo "✅ Setup Complete!"
echo "--------------------------------------------------------"
echo "To launch the SortSense UI, run:"
echo "  source .venv/bin/activate"
echo "  python -m app.gui"
echo "--------------------------------------------------------"
