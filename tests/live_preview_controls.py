"""Exercise real Qt output-panel and image-viewer interactions without GPU jobs."""
import hashlib
import json
import argparse
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap, QWheelEvent
from PySide6.QtTest import QTest

from aipictures.app import Window, create_application
from aipictures.storage import DATA, write_json


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--manifest')
    args=parser.parse_args()
    if args.manifest: folder=Path(args.manifest).resolve().parent
    else:
        record = json.loads((DATA / 'walk-acceptance.json').read_text('utf-8'))
        folder = Path(record['folder'])
    image = folder / 'frame_000.png'
    original_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    app = create_application([])
    # Keep the user's connection and persistent history untouched during inspection.
    with patch.object(Window, 'connect_engine', lambda self: None), patch('aipictures.app.write_json'):
        window = Window(); window.timer.stop(); window.show()
        QTest.qWait(250)
        window.generation_type.setCurrentIndex(1)
        window.animation_source.setCurrentIndex(0)
        window.positive.setPlainText('自然站立，全身，侧视')
        assert '行走' in window.intent_hint.text()
        assert not window.model.isEnabled() and not window.workflow_selector.isEnabled()
        window.animation_source.setCurrentIndex(1)
        assert window.model.isEnabled() and '不使用' in window.reference_label.text()
        window.generation_type.setCurrentIndex(0)
        assert not window.diagnostics.isVisible() and not window.chat.isVisible()
        assert window.positive.isVisible() and window.negative.isVisible()
        window.add_chat('软件', '预览操作验收：消息默认收起，按需查看。')
        assert not window.diagnostics.isVisible()
        window.show_image(str(image)); QTest.qWait(100)
        preview_height = window.preview.height()
        window.grab().save(str(DATA / 'compact-studio-preview.png'))
        QTest.mouseClick(window.output_toggle, Qt.MouseButton.LeftButton); QTest.qWait(100)
        assert window.diagnostics.isVisible() and window.chat.isVisible()
        assert '预览操作验收' in window.chat.toPlainText()
        assert window.preview.height() < preview_height
        assert window.preview.pixmap().deviceIndependentSize().height() <= window.preview.height()
        window.grab().save(str(DATA / 'output-panel-preview.png'))
        window.diagnostics.close(); QTest.qWait(100)
        assert not window.output_toggle.isChecked()
        window.activateWindow(); window.positive.setFocus(); QTest.qWait(100)
        QTest.keyClick(window.positive, Qt.Key.Key_J, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(100); assert window.diagnostics.isVisible()
        QTest.keyClick(window.positive, Qt.Key.Key_J, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(100); assert not window.diagnostics.isVisible()

        QTest.mouseClick(window.preview, Qt.MouseButton.LeftButton); QTest.qWait(150)
        viewer = window.image_viewer; assert viewer and viewer.isVisible()
        assert viewer.view.item.pixmap().size() == QPixmap(str(image)).size()
        QTest.mouseClick(viewer.original, Qt.MouseButton.LeftButton)
        assert abs(viewer.view.transform().m11() - 1) < .001
        viewport = viewer.view.viewport(); position = viewport.rect().center()
        wheel = QWheelEvent(QPointF(position), QPointF(viewport.mapToGlobal(position)),
            QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(viewport, wheel)
        assert viewer.view.transform().m11() > 1
        QTest.mouseClick(viewer.zoom_out, Qt.MouseButton.LeftButton)
        assert abs(viewer.view.transform().m11() - 1) < .001
        QTest.mouseClick(viewer.zoom_in, Qt.MouseButton.LeftButton)
        assert viewer.view.transform().m11() > 1
        QTest.mouseClick(viewer.original, Qt.MouseButton.LeftButton)
        scroll = viewer.view.verticalScrollBar(); before = scroll.value()
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=position)
        QTest.mouseMove(viewport, position + QPoint(0, 70), 50)
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=position + QPoint(0, 70))
        assert scroll.value() != before
        QTest.mouseClick(viewer.fit, Qt.MouseButton.LeftButton); QTest.qWait(100)
        assert viewer.view.fit_mode and viewer.view.transform().m11() < 1
        fitted = viewer.view.transform().mapRect(viewer.view.item.boundingRect())
        assert fitted.height() <= viewport.height() and fitted.width() <= viewport.width()
        viewer.grab().save(str(DATA / 'image-zoom-preview.png'))
        QTest.keyClick(viewer, Qt.Key.Key_Escape); assert not viewer.isVisible()

        window.animation_player.load(folder / 'sequence.json'); QTest.qWait(150)
        QTest.mouseClick(window.preview, Qt.MouseButton.LeftButton)
        assert not viewer.isVisible() and window.animation_player.timer.isActive()
        window.animation_player.toggle()
        QTest.mouseClick(window.preview, Qt.MouseButton.LeftButton)
        assert not viewer.isVisible()
        window.sequence_preview.setCurrentIndex(1)
        window.sequence_preview.select_frame(window.sequence_preview.frames.item(5))
        QTest.mouseClick(window.preview, Qt.MouseButton.LeftButton)
        assert window.animation_player.index == 5 and not viewer.isVisible()
        window.sequence_preview.setCurrentIndex(2); QTest.qWait(100)
        QTest.mouseClick(window.sequence_preview.sheet, Qt.MouseButton.LeftButton); QTest.qWait(150)
        assert viewer.isVisible() and viewer.source_path == (folder / 'sprite_sheet.png').resolve()
        assert viewer.view.item.pixmap().size() == QPixmap(str(folder / 'sprite_sheet.png')).size()
        viewer.close()
        window.show_image(str(image), allow_zoom=False)
        QTest.mouseClick(window.preview, Qt.MouseButton.LeftButton); assert not viewer.isVisible()
        window.show_image(str(image))
        QTest.mouseClick(window.preview, Qt.MouseButton.LeftButton); assert viewer.isVisible()
        viewer.close(); window.close()
    assert hashlib.sha256(image.read_bytes()).hexdigest() == original_hash
    write_json(DATA / 'preview-controls-acceptance.json', {
        'passed': True, 'output_hidden_by_default': True, 'output_button_and_ctrl_j': True,
        'full_resolution_image_viewer': True, 'wheel_zoom_drag_100_percent_fit_escape': True,
        'playing_paused_selected_animation_frames_not_enlarged': True,
        'static_sprite_sheet_enlarged': True, 'source_unchanged': True,'manifest':str(folder/'sequence.json')})
    print('Output panel and full-resolution image controls passed; animation clicks remain unchanged.')


if __name__ == '__main__': main()
