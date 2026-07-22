@echo off
REM ManaForge Deckbuilder Startup Script
REM Double-click this file to start the app

echo.
echo ========================================
echo  ManaForge - MTG Theme Deckbuilder
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/4] Checking dependencies...
pip list | find "Flask" >nul
if errorlevel 1 (
    echo [2/4] Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
) else (
    echo [2/4] Dependencies already installed ✓
)

echo [3/4] Checking card database...
if not exist "data\cards.sqlite" (
    echo [3/4] Syncing card data (this may take a minute)...
    python -m deckbuilder.carddata sync
    if errorlevel 1 (
        echo ERROR: Failed to sync card data
        pause
        exit /b 1
    )
) else (
    echo [3/4] Card database found ✓
)

echo [4/4] Starting Flask app...
echo.
echo ========================================
echo  Server is starting!
echo  Open: http://127.0.0.1:5000
echo  Press Ctrl+C to stop
echo ========================================
echo.

python app.py

pause
