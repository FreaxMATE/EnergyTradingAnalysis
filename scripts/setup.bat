@echo off
REM Energy Trading Analysis Setup Script for Windows

echo 🚀 Setting up Energy Trading Analysis Environment...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.8+ first.
    echo Visit: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python found
python --version

REM Create virtual environment
echo 📦 Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo 🔄 Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo ⬆️ Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo 📚 Installing dependencies...
pip install -r requirements.txt

echo 🎉 Setup complete!
echo.
echo To run the analysis:
echo 1. Activate the virtual environment: venv\Scripts\activate.bat
echo 2. Run the analysis: cd src ^&^& python modelling.py
echo.
echo To deactivate the virtual environment: deactivate
pause