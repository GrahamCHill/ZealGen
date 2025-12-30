import subprocess
import sys
import os
import shutil

def build():
    print("Building DocuGen GUI application...")
    
    # Entry point is src/zealgen/main.py
    # We want to bundle it as a single windowed application
    
    entry_point = os.path.join("src", "zealgen", "main.py")
    
    if not os.path.exists(entry_point):
        print(f"Error: Could not find entry point at {entry_point}")
        sys.exit(1)

    # Check if pyinstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing it...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "ZealGen",
        "--add-data", f"src/zealgen{os.pathsep}zealgen",
        entry_point
    ]

    print(f"Running command: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\nBuild successful!")
        print("The executable can be found in the 'dist' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()
