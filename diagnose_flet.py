import sys
import os

print(f"Python executable: {sys.executable}")
print(f"Path: {sys.path}")

try:
    import flet
    print(f"Flet location: {os.path.dirname(flet.__file__)}")
except ImportError as e:
    print(f"Error importing flet: {e}")

try:
    import flet_desktop
    print(f"flet_desktop location: {os.path.dirname(flet_desktop.__file__)}")
except ImportError as e:
    print(f"Error importing flet_desktop: {e}")

try:
    import flet.desktop
    print("flet.desktop is importable")
except ImportError:
    print("flet.desktop is NOT importable")
