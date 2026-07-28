"""
Red Light, Green Light - entry point.

Run with:  python main.py
Requires a webcam. See README.md for full setup instructions.
"""

import sys

from src.app import App


def main():
    app = App()
    if not app.camera.available:
        print(f"[warning] {app.camera.last_error}")
        print("[warning] The game will still launch, but you won't be able to "
              "register, log in, or play without a working webcam.")
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        pass


if __name__ == "__main__":
    sys.exit(main() or 0)
