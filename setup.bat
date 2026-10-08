@echo off
echo 🚀 Starting SortSense Setup for Windows...

:: 1. Check Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ❌ Python 3 is not installed or not in your system PATH. 
    echo Please install Python from https://www.python.org/downloads/
    exit /b 1
)

:: 2. Virtual Environment Setup
echo 📦 Setting up Python virtual environment...
IF NOT EXIST ".venv\" (
    python -m venv .venv
)

:: Activate venv and install dependencies
call .venv\Scripts\activate.bat
echo 📥 Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

:: 3. Check Ollama
ollama --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ⚠️ Ollama is not installed.
    echo Please download and install Ollama from https://ollama.com/download/windows
    echo Once installed, run this setup script again.
    exit /b 1
)

:: 4. Pull Model
set MODEL_NAME=gemma4:e4b
echo 🧠 Ensure Ollama is running in your system tray!
echo 📥 Ensuring the model '%MODEL_NAME%' is pulled (this might take a while if downloading)...
ollama pull %MODEL_NAME%

echo.
echo ✅ Setup Complete!
echo --------------------------------------------------------
echo To launch the SortSense UI, run:
echo   .venv\Scripts\activate
echo   python -m app.gui
echo --------------------------------------------------------
pause
