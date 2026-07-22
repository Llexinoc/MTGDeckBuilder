#!/usr/bin/env python3
"""
ManaForge Deckbuilder - Startup Script with UV Support
Run this to start the Flask app with all setup checks
"""
import os
import sys
import subprocess
import shutil
import webbrowser
import threading
import time

def run_command(cmd, description):
    """Run a command and report status"""
    print(f"\n[*] {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"    ✓ {description} - Success")
            return True
        else:
            print(f"    ✗ {description} - Failed")
            if result.stderr and "externally-managed" not in result.stderr and "No virtual environment" not in result.stderr:
                print(f"    Error: {result.stderr[:150]}")
            return False
    except Exception as e:
        print(f"    ✗ {description} - Error: {e}")
        return False

def detect_uv():
    """Check if UV is installed"""
    return shutil.which("uv") is not None

def main():
    print("\n" + "="*50)
    print("  ManaForge - MTG Theme Deckbuilder")
    print("="*50)
    
    # Change to script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Step 1: Check Python
    print("\n[1/4] Checking Python installation...")
    try:
        version = subprocess.run([sys.executable, "--version"], capture_output=True, text=True)
        print(f"    ✓ Python found: {version.stdout.strip()}")
    except:
        print("    ✗ Python not found")
        return 1
    
    # Detect UV environment
    using_uv = detect_uv()
    if using_uv:
        print("    ℹ UV detected - setting up virtual environment")
    
    # Step 2: Setup UV venv if needed
    if using_uv:
        print("\n[2/4] Setting up UV virtual environment...")
        if not os.path.exists(".venv"):
            print("    Creating virtual environment...")
            if not run_command("uv venv .venv", "Creating .venv"):
                print("    ERROR: Could not create virtual environment")
                return 1
        else:
            print("    ✓ Virtual environment exists")
        
        # Install dependencies using uv
        if not run_command("uv pip install -r requirements.txt", "Installing dependencies with UV"):
            print("    ERROR: Could not install dependencies")
            return 1
        else:
            print("    ✓ Dependencies installed")
    else:
        # Standard pip approach
        print("\n[2/4] Installing dependencies...")
        if not run_command(f"{sys.executable} -m pip install -r requirements.txt", "Installing dependencies"):
            print("    ERROR: Could not install dependencies")
            return 1
        else:
            print("    ✓ Dependencies installed")
    
    # Step 3: Sync card data
    print("\n[3/4] Checking card database...")
    if not os.path.exists("data/cards.sqlite"):
        print("    Card database not found - syncing from Scryfall...")
        if not run_command(f"{sys.executable} -m deckbuilder.carddata sync", "Syncing card data"):
            print("    WARNING: Could not sync card data (app may work with live API)")
    else:
        try:
            db_size_mb = os.path.getsize("data/cards.sqlite") / (1024*1024)
            print(f"    ✓ Card database found ({db_size_mb:.1f} MB)")
        except:
            print("    ✓ Card database exists")
    
    # Step 4: Start Flask app
    print("\n[4/4] Starting Flask app...")
    print("\n" + "="*50)
    print("  Server is starting!")
    print("  Browser will open automatically...")
    print("  Press Ctrl+C to stop")
    print("="*50 + "\n")
    
    browser_opened = False
    
    def open_browser():
        """Open browser after short delay"""
        nonlocal browser_opened
        time.sleep(2)
        if not browser_opened:
            browser_opened = True
            webbrowser.open("http://127.0.0.1:5000")
    
    # Start browser opener thread
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    process = None
    try:
        # Start Flask app and stream output
        # Use venv Python on Windows, standard venv on Unix
        venv_python = os.path.join(".venv", "Scripts", "python.exe") if sys.platform == "win32" else os.path.join(".venv", "bin", "python")
        python_exe = venv_python if os.path.exists(venv_python) else sys.executable
        
        process = subprocess.Popen(
            [python_exe, "app.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Monitor output
        if process.stdout:
            for line in process.stdout:
                print(line.rstrip())
                # Check if server is ready
                if "Running on" in line and not browser_opened:
                    browser_opened = True
                    webbrowser.open("http://127.0.0.1:5000")
        
        process.wait()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        if process:
            try:
                process.terminate()
                process.wait(timeout=3)
            except:
                process.kill()
        print("Server stopped.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
