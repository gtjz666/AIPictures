"""Expensive real Qt -> isolated H3 -> preview -> transparent assets -> ZIP acceptance."""
import argparse
import json
import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QDialog,QFileDialog
from aipictures.app import Window,create_application
from aipictures.storage import DATA,write_json


def main():
    p=argparse.ArgumentParser(description='真实GPU验收，会生成一段自由动作并拆成透明素材，不属于普通单元测试。')
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--h3-settings',type=Path,default=DATA/'h3-settings.json')
    p.add_argument('--seconds',type=float,default=2)
    p.add_argument('--action',default='角色在原地抬起右手，向镜头方向挥手两次，再将手臂自然放下。完整人物始终在画面内。')
    a=p.parse_args();root=a.output.resolve()
    if root.exists():raise ValueError('验收目录已存在，请先检查旧任务，不会自动重跑。')
    if not a.reference.is_file() or not a.h3_settings.is_file():raise ValueError('参考图或已验证H3配置缺失。')
    root.mkdir(parents=True);shutil.copyfile(a.h3_settings,root/'h3-settings.json')
    app=create_application([])
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc'
    if font.is_file():QFontDatabase.addApplicationFont(str(font))
    report={'status':'running','real_inference':True,'comfy_connected_in_ui':False,'bone_editor_used':False,'lora_used':False}
    started=time.monotonic();state={'phase':'generate'}
    with patch('aipictures.app.DATA',root),patch.object(Window,'auto_connect_engine'),\
         patch.object(Window,'refresh_stats'),patch.object(Window,'restore_chat'):
        window=Window();window.timer.stop();window.show()
        window.set_reference(str(a.reference));window.generation_type.setCurrentIndex(1)
        window.animation_engine.setCurrentIndex(window.animation_engine.findData('h3'))
        window.animation_action.setCurrentIndex(window.animation_action.findData('custom'))
        window.custom_description.setPlainText(a.action)
        window.positive.setPlainText('参考图中的同一角色，保留原本的发型、服装、配色和画风。\n'+a.action)
        window.negative.setPlainText('多余肢体，重影，变色，模糊，裁切，镜头移动')
        window.seed.setText('20261102');window.video_controller.seconds.setValue(a.seconds)
        assert not window.connected and window.video_controller.h3
        window.enqueue()
        if not window.current:raise ValueError('界面未成功启动生成，请查看验收目录中的聊天记录。')
        report['video_folder']=str(window.current['folder'])
        timer=QTimer();timer.setInterval(250)
        def inspect():
            try:
                player=window.video_controller.player
                if window.current or window.preparing:return
                if state['phase']=='generate':
                    if not player.manifest:raise ValueError('生成未完成，请检查视频目录和日志。')
                    data=json.loads(player.manifest.read_text('utf-8'))
                    assert data['status']=='completed' and data['native_rgb_preserved']
                    assert len(player.frames)==data['frame_count'] and player.fps==24
                    assert player.isVisible() and window.preview_role=='video'
                    player.timer.stop();window.grab().save(str(root/'full-animation-preview.png'))
                    report.update(video_manifest=str(player.manifest),full_frame_count=len(player.frames),fps=player.fps)
                    state['phase']='extract'
                    player.split();picker=window.frame_selection_dialog
                    for i in range(8):picker.grid.item(round(i*(len(player.frames)-1)/7)).setCheckState(Qt.CheckState.Checked)
                    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(root/'picked_sheet.png'),'PNG')):picker.export('sheet')
                    assert window.preparing
                elif state['phase']=='extract':
                    manifest=window.animation_player.manifest
                    if not manifest:raise ValueError('透明素材拆帧未完成，请查看转帧记录。')
                    data=json.loads(Path(manifest).read_text('utf-8'));folder=Path(manifest).parent
                    assert data['status']=='completed' and len(data['frames'])==8
                    assert not data['temporal_blending'] and not data['content_scaled']
                    size=tuple(data['canvas']);columns=data['exports']['columns'];alphas=[]
                    with Image.open(folder/'sprite_sheet.png') as sheet:
                        for i,frame in enumerate(data['frames']):
                            with Image.open(folder/frame['image']) as asset,Image.open(window.video_controller.player.frames[frame['source_index']]) as raw:
                                assert asset.convert('RGB').tobytes()==raw.convert('RGB').tobytes()
                                assert sheet.crop(((i%columns)*size[0],(i//columns)*size[1],(i%columns+1)*size[0],(i//columns+1)*size[1])).tobytes()==asset.tobytes()
                                alphas.append(asset.getchannel('A').getextrema())
                    assert all(low==0 and high==255 for low,high in alphas)
                    window.animation_player.timer.stop();window.grab().save(str(root/'sprite-preview.png'))
                    export=root/'animation-assets.zip'
                    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(export),'ZIP')):window.animation_player.export()
                    assert export.is_file() and export.stat().st_size>0
                    report.update(status='completed',sprite_manifest=str(manifest),zip=str(export),
                        rgb_preserved=True,sheet_readback_exact=True,alpha_ranges=alphas,elapsed_seconds=time.monotonic()-started)
                    write_json(root/'acceptance.json',report);timer.stop();window.close();app.quit()
            except Exception as exc:
                report.update(status='failed',error=str(exc),elapsed_seconds=time.monotonic()-started)
                write_json(root/'acceptance.json',report);timer.stop();window.close();app.quit()
        timer.timeout.connect(inspect);timer.start();app.exec()
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='completed':raise SystemExit(1)


if __name__=='__main__':main()
