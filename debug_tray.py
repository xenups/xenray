
import sys
# Inject system packages if needed (mimicking main.py)
import os
if sys.platform.startswith("linux"):
    system_packages = "/usr/lib/python3/dist-packages"
    if os.path.exists(system_packages) and system_packages not in sys.path:
        try:
            import gi
        except ImportError:
            sys.path.append(system_packages)

import pystray
from PIL import Image, ImageDraw

def create_image():
    # Generate an image with a specific color
    width = 64
    height = 64
    color1 = "blue"
    color2 = "white"
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
    dc.rectangle((0, height // 2, width // 2, height), fill=color2)
    return image

def setup(icon):
    icon.visible = True

def on_quit(icon, item):
    icon.stop()

def main():
    print(f"Python: {sys.version}")
    
    try:
        import gi
        print(f"PyGObject (gi) imported: {gi.__file__}")
        try:
            gi.require_version('AppIndicator3', '0.1')
            from gi.repository import AppIndicator3
            print("AppIndicator3 found via gi")
        except Exception as e:
            print(f"AppIndicator3 check failed: {e}")
            
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3
            print("AyatanaAppIndicator3 found via gi")
        except Exception as e:
            print(f"AyatanaAppIndicator3 check failed: {e}")
            
    except ImportError:
        print("PyGObject (gi) NOT found")

    image = create_image()
    
    # Try to force AppIndicator backend explicitly to see if it works validation
    # os.environ['PYSTRAY_BACKEND'] = 'appindicator' 
    
    print("Creating icon...")
    icon = pystray.Icon(
        'test_icon',
        image,
        menu=pystray.Menu(
            pystray.MenuItem('Quit', on_quit)
        )
    )
    
    print("Running icon... (Check your system tray)")
    icon.run(setup)

if __name__ == "__main__":
    main()
