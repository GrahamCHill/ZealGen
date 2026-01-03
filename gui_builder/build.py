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
    # linux: no icon flag (handled by desktop env / package)

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

    if sys.platform == "darwin":
        PLAYWRIGHT_BROWSERS = os.path.expanduser(
            "~/Library/Caches/ms-playwright"
        )
    elif sys.platform.startswith("linux"):
        PLAYWRIGHT_BROWSERS = os.path.expanduser(
            "~/.cache/ms-playwright"
        )
    elif sys.platform == "win32":
        PLAYWRIGHT_BROWSERS = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "ms-playwright",
        )
    else:
        PLAYWRIGHT_BROWSERS = None

    if PLAYWRIGHT_BROWSERS and os.path.exists(PLAYWRIGHT_BROWSERS):
        cmd.extend([
            "--collect-all", "playwright",
            "--add-data",
            f"{PLAYWRIGHT_BROWSERS}{os.pathsep}ms-playwright",
        ])

    if icon_path and os.path.isfile(icon_path):
        cmd.extend(["--icon", icon_path])

    if sys.platform == "darwin":
        cmd.extend([
            "--osx-bundle-identifier",
            "com.yourdomain.docugen",
            "--codesign-identity", "-",

        ])


    cmd.append(entry_point)
    subprocess.check_call(cmd)


if __name__ == "__main__":
    build()
