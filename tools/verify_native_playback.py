"""Read real exported sequences through Qt playback without submitting GPU work."""
import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QPixmap

from aipictures.app import Window, create_application
from aipictures.storage import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sequence', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    for path in args.sequence:
        if not path.is_file():
            parser.error('序列记录不存在：' + str(path))
    if args.out.exists():
        parser.error('检查输出目录已存在，请使用新目录，保留旧记录。')
    args.out.mkdir(parents=True)
    app = create_application([])
    records = []
    with tempfile.TemporaryDirectory(dir=args.out.resolve()) as temporary:
        if Path(temporary).resolve().parent != args.out.resolve():
            raise RuntimeError('临时检查目录超出本次输出位置。')
        with patch('aipictures.app.DATA', Path(temporary)), \
             patch.object(Window, 'connect_engine'), patch.object(Window, 'load_gallery'), \
             patch.object(Window, 'restore_chat'), patch.object(Window, 'refresh_stats'):
            window = Window()
            window.timer.stop()
            try:
                for path in args.sequence:
                    path = path.resolve()
                    manifest = json.loads(path.read_text('utf-8'))
                    assert manifest['status'] == 'completed', path
                    player = window.animation_player
                    player.load(path)
                    player.timer.stop()
                    width, height = manifest['canvas']
                    for i, frame in enumerate(manifest['frames']):
                        player.slider.setValue(i)
                        assert Path(window.output) == path.parent / frame['image']
                        assert not window.pixmap.isNull()
                        assert (window.pixmap.width(), window.pixmap.height()) == (width, height)
                        assert f'{i+1}/{len(player.frames)}' in player.label.text()
                    if manifest.get('game_animation', {}).get('engine_driven_jump'):
                        player.physics.setChecked(True)
                        settings = manifest['game_animation']['preview_only']
                        for i, frame in enumerate(manifest['frames']):
                            player.seek(i)
                            source = QPixmap(str(path.parent / frame['image']))
                            y = settings['top_padding'] + settings['offset_y'][i]
                            assert window.pixmap.height() == height + settings['top_padding']
                            assert window.pixmap.copy(0, y, width, height).toImage() == source.toImage()
                        player.physics.setChecked(False)
                    player.slider.setValue(0)
                    for _ in player.frames:
                        player.advance()
                    assert player.index == (0 if player.loop else len(player.frames)-1)
                    records.append({'sequence': str(path), 'action': manifest['action'],
                        'frames': len(player.frames), 'motion_revision': manifest.get('motion_revision'),
                        'size_and_frame_labels': True, 'loop_or_endpoint': True,
                        'physics_preview_exact_png_translation': True if manifest.get('game_animation', {}).get('engine_driven_jump') else None})
            finally:
                window.pending.clear()
                window.current = None
                window.close()
    write_json(args.out / 'report.json', {'passed': True, 'records': records, 'gpu_jobs_submitted': 0})
    print(f'Qt native playback passed for {len(records)} real sequences; no GPU work submitted.')


if __name__ == '__main__':
    main()
