"""Small local-video import dialog; does not require a running inference backend."""
import threading
from datetime import datetime
from uuid import uuid4

from PySide6.QtWidgets import QDialog,QFormLayout,QVBoxLayout,QComboBox,QCheckBox,QPushButton,QFileDialog,QLabel


def open_import(window):
    if window.current or window.preparing:
        window.status.setText('请等当前任务结束后再导入视频。');return
    path,_=QFileDialog.getOpenFileName(window,'选择动作视频或 GIF','','动画 (*.mp4 *.mov *.webm *.mkv *.avi *.gif)')
    if not path:return
    dialog=QDialog(window);dialog.setWindowTitle('视频 → 动画帧');dialog.resize(420,260)
    layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
    count=QComboBox();count.addItem('8 帧',8);count.addItem('16 帧',16);form.addRow('输出帧数',count)
    fps=window.spin(1,30,8);form.addRow('播放帧率',fps)
    sampling=QComboBox();sampling.addItem('关键姿态优先 + 源过渡帧','keyframes')
    sampling.addItem('均匀取帧','uniform');form.addRow('取帧方式',sampling)
    looping=QCheckBox('提取首尾相近的循环片段');looping.setChecked(True);form.addRow(looping)
    transparent=QCheckBox('生成透明背景');transparent.setChecked(True);form.addRow(transparent)
    note=QLabel('保留原始画布，不混帧、不缩放人物。视频最长 30 秒；循环接缝仍需检查。')
    note.setWordWrap(True);layout.addWidget(note)
    submit=QPushButton('提取动画帧');submit.clicked.connect(dialog.accept);layout.addWidget(submit)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return
    frames,rate,loop,matte=count.currentData(),fps.value(),looping.isChecked(),transparent.isChecked()
    if matte:
        from .background import model_file
        if not model_file().is_file():window.status.setText('透明背景模型尚未安装，请先安装或取消透明输出。');return
    from .video_frames import extract_video
    from pathlib import Path
    folder=window.api_controller.data/'animations'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
    window.preparing=True;window.importing_folder=folder
    window.prepare_cancel.clear();window.task_display.start();window.progress.setRange(0,0)
    window.api_controller.apply_mode()
    def event(kind,data):
        if kind=='reference_stage':window.status.setText(data['message'])
        elif kind=='frame_ready':window.show_image(data['image'],allow_zoom=False)
        elif kind in ('result','error','cancelled'):
            window.preparing=False;window.importing_folder=None
            status={'result':'completed','error':'failed','cancelled':'cancelled'}[kind]
            window.task_display.finish(status);window.progress.setRange(0,100)
            window.progress.setValue(100 if kind=='result' else 0);window.api_controller.apply_mode()
            if kind=='result':
                window.animation_player.load(data['manifest']);window.load_gallery()
                window.add_chat('软件','视频已转为独立动画帧。'+('；'.join(data['warnings']) if data['warnings'] else ''),job=str(folder))
            else:window.add_chat('软件','视频转帧'+('已取消：' if kind=='cancelled' else '失败：')+str(data),job=str(folder))
    method=sampling.currentData()
    window.launch(lambda emit:extract_video(Path(path),folder,frames,rate,loop,matte,window.prepare_cancel,emit,sampling=method),event)
