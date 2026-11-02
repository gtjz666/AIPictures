"""Render this application's controls offscreen, without connecting or generating."""
import argparse
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtGui import QFontDatabase

from aipictures.app import Window, create_application


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    # Qt's offscreen platform does not enumerate Windows system fonts.
    font = Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/'msyh.ttc'
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
    with tempfile.TemporaryDirectory() as temp, patch('aipictures.app.DATA', Path(temp)), \
         patch.object(Window, 'connect_engine'), patch.object(Window, 'load_gallery'), \
         patch.object(Window, 'restore_chat'), patch.object(Window, 'refresh_stats'):
        window = Window()
        window.timer.stop()
        window.show()
        QTest.qWait(80)
        window.grab().save(str(args.output/'single.png'))
        window.generation_type.setCurrentIndex(1)
        window.animation_action.setCurrentIndex(window.animation_action.findData('custom'))
        window.positive.setPlainText('角色挥手，然后转身走开。固定镜头，保持原有服装和配色。')
        QTest.qWait(50)
        window.grab().save(str(args.output/'custom-animation.png'))
        window.open_settings('image')
        QTest.qWait(50)
        window.settings_dialogs['image'].grab().save(str(args.output/'image-settings.png'))
        window.close()


if __name__ == '__main__':
    main()
