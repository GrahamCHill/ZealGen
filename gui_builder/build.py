# gui_builder/build.py
import subprocess
import sys
import os

ICON_WIN = "assets/icon.ico"
ICON_MAC = "assets/icon.icns"


def build():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    entry_point = os.path.join(project_root, "src", "docugen", "main.py")
    if not os.path.isfile(entry_point):
        sys.exit(f"Entry point not found: {entry_point}")

    try:
        import PyInstaller  # noqa
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller"]
        )

    icon_path = None
    if sys.platform == "win32":
        icon_path = os.path.join(script_dir, ICON_WIN)
    elif sys.platform == "darwin":
        icon_path = os.path.join(script_dir, ICON_MAC)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "DocuGen",
        "--add-data",
        f"{os.path.join(project_root, 'src', 'docugen')}{os.pathsep}docugen",
    ]

    if icon_path and os.path.isfile(icon_path):
        cmd.extend(["--icon", icon_path])

    if sys.platform == "darwin":
        cmd.extend([
            "--osx-bundle-identifier",
            "com.yourdomain.docugen",
        ])

    cmd.append(entry_point)
    subprocess.check_call(cmd)


if __name__ == "__main__":
    build()
