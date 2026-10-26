import json
import sys
from PySide6.QtCore import QTimer
from aipictures.app import Window, create_application
from aipictures.storage import DATA

app = create_application([])
window = Window(); window.show()
image = json.loads((DATA / 'acceptance.json').read_text('utf-8'))['image']
window.show_image(image)

def capture():
    if window.workers: return
    window.grab().save(str(DATA / 'acceptance-desktop.png'))
    app.quit()

timer = QTimer(); timer.timeout.connect(capture); timer.start(1000)
sys.exit(app.exec())
