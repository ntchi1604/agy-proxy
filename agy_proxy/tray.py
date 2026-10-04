import threading
import pystray
from PIL import Image, ImageDraw

def create_image(width, height, color1, color2):
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
    dc.rectangle((0, height // 2, width // 2, height), fill=color2)
    return image

def run_tray(port: int = 8000):
    def on_quit(icon, item):
        icon.stop()
        
    icon = pystray.Icon(
        'agy-proxy',
        create_image(64, 64, 'blue', 'white'),
        f'Antigravity Proxy ({port})',
        menu=pystray.Menu(
            pystray.MenuItem('Quit', on_quit)
        )
    )
    
    icon.run()

def start_tray_in_thread(port: int = 8000):
    tray_thread = threading.Thread(target=run_tray, args=(port,), daemon=True)
    tray_thread.start()
    return tray_thread
