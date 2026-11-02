"""No model inference: real cached animation -> Qt manual selection -> exact assets."""
import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from aipictures.app import Window,create_application
from aipictures.storage import write_json
from aipictures.frame_selection import open_selection


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    source=a.manifest.resolve();root=a.output.resolve()
    if root.exists():raise ValueError('验收目录已存在，请使用新目录。')
    root.mkdir(parents=True);app=create_application([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    data=json.loads(source.read_text('utf-8'));indices=[3,20,43]
    if len(data['frames'])<=max(indices):raise ValueError('此验收需要至少44帧的真实已完成动画。')
    with patch('aipictures.app.DATA',root),patch.object(Window,'auto_connect_engine'),\
         patch.object(Window,'refresh_stats'),patch.object(Window,'restore_chat'):
        w=Window();w.timer.stop();w.show();w.generation_type.setCurrentIndex(1)
        w.animation_action.setCurrentIndex(w.animation_action.findData('custom'))
        w.positive.setPlainText('参考图中的角色面向镜头挥手，保持原服装与配色。')
        w.video_controller.player.load(source);w.video_controller.player.timer.stop()
        w.video_controller.player.slider.setValue(len(data['frames'])-1);w.video_controller.player.advance()
        assert w.video_controller.player.index==0
        w.grab().save(str(root/'unified-loop-seed.png'))
        open_selection(w,source);picker=w.frame_selection_dialog
        assert picker.selected()==[]
        for index in indices:picker.grid.item(index).setCheckState(Qt.CheckState.Checked)
        picker.seek(20);QTest.qWait(500);picker.grab().save(str(root/'manual-frame-selection.png'))
        sheet=root/'picked.png';started=time.monotonic()
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(sheet),'PNG')):picker.export('sheet')
        deadline=time.monotonic()+300
        while w.preparing and time.monotonic()<deadline:app.processEvents();QTest.qWait(30)
        if w.preparing or not sheet.exists():raise ValueError(picker.status.text())
        meta=json.loads(sheet.with_suffix('.json').read_text('utf-8'))
        assert meta['source_indices']==indices and meta['seed']==data['params']['seed']
        manifest=w.animation_player.manifest;assets=json.loads(manifest.read_text('utf-8'))
        with Image.open(sheet) as assembled:
            for row,index in zip(meta['frames'],indices):
                with Image.open(manifest.parent/row['image']) as asset,Image.open(source.parent/data['frames'][index]['image']) as original:
                    assert asset.convert('RGB').tobytes()==original.convert('RGB').tobytes()
                    assert asset.text['Seed']==str(meta['seed']) and asset.getchannel('A').getextrema()==(0,255)
                    r=row['rect'];assert assembled.crop((r['x'],r['y'],r['x']+r['w'],r['y']+r['h'])).tobytes()==asset.tobytes()
        picker.close();app.processEvents()
        w.animation_player.select_frames();subset=w.frame_selection_dialog
        for index in (0,2):subset.grid.item(index).setCheckState(Qt.CheckState.Checked)
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(root)):subset.export('pngs')
        deadline=time.monotonic()+60
        while w.preparing and time.monotonic()<deadline:app.processEvents();QTest.qWait(20)
        if w.preparing:raise ValueError('PNG导出尚未完成。')
        output=json.loads(w.animation_player.manifest.read_text('utf-8'))['output']
        assert len(list(Path(output).glob('*.png')))==2
        subset.close();w.grab().save(str(root/'selected-assets.png'));w.close()
        report={'passed':True,'real_cached_animation':str(source),'new_gpu_inference':False,'selected_source_indices':indices,
            'sheet':str(sheet),'png_folder':output,'seed':meta['seed'],'rgb_exact':True,'sheet_readback_exact':True,
            'alpha_preserved':True,'elapsed_seconds':round(time.monotonic()-started,2)}
        write_json(root/'acceptance.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
