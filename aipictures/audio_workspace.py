"""Standalone music workspace and queue controller, without a chat reply panel."""
import json
import secrets
import shutil
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import numpy as np
from PySide6.QtCore import Qt,QUrl,QTimer
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import (QWidget,QSplitter,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QDoubleSpinBox,
    QPushButton,QSlider,QFileDialog,QListWidget,QListWidgetItem,QComboBox)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from .playback_button import PlaybackButton
from .storage import write_json


class Waveform(QWidget):
    def __init__(self):super().__init__();self.values=None;self.setMinimumHeight(240)
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#f4f6fc'));p.setPen(QPen(QColor('#6073b9'),2))
        if self.values is None:p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'生成音频后在这里试听');return
        width=self.width();mid=self.height()/2;scale=mid*.8
        for x in range(0,width,3):
            value=self.values[min(len(self.values)-1,int(x/width*len(self.values)))]
            p.drawLine(x,round(mid-value*scale),x,round(mid+value*scale))


class AudioWorkspace:
    def __init__(self,w):
        self.window=w;self.data=w.api_controller.data;self.manifest=None
        from .audio_generation import settings
        self.config=settings(self.data)
        self.page=QSplitter(Qt.Orientation.Horizontal);self.left=QWidget();left=QVBoxLayout(self.left)
        self.title=QLabel('独立音频');left.addWidget(self.title);self.wave=Waveform();left.addWidget(self.wave,1)
        self.player=QMediaPlayer(self.page);self.output=QAudioOutput(self.page);self.player.setAudioOutput(self.output);self.output.setVolume(.65)
        row=QHBoxLayout();self.play=PlaybackButton();self.play.clicked.connect(self.toggle);row.addWidget(self.play)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.sliderMoved.connect(self.player.setPosition);row.addWidget(self.slider,1)
        self.clock=QLabel('00:00');row.addWidget(self.clock);self.export=QPushButton('导出音频…');self.export.clicked.connect(self.save);row.addWidget(self.export);left.addLayout(row)
        for control in (self.play,self.slider,self.export):control.setEnabled(False)
        self.player.durationChanged.connect(lambda duration:self.slider.setRange(0,duration))
        self.player.positionChanged.connect(self.position);self.player.playbackStateChanged.connect(lambda state:self.play.set_playing(state==QMediaPlayer.PlaybackState.PlayingState))
        self.right=QWidget();right=QVBoxLayout(self.right);right.addWidget(QLabel('用户需求'))
        self.prompt=QPlainTextEdit();self.prompt.setPlaceholderText('用一句话描述想要的音乐，例如：舒缓但带有淡淡悲伤的背景音乐。\n点击下方“生成专业提示词”细化配器、节奏与结构。');right.addWidget(self.prompt,1)
        self.parameters=QWidget();parameters=QVBoxLayout(self.parameters);parameters.setContentsMargins(0,0,0,0)
        self.kind=QComboBox()
        for title,key in [('自动识别用途','auto'),('背景配乐 BGM','music'),('游戏音效','sfx')]:self.kind.addItem(title,key)
        parameters.addWidget(self.kind)
        row=QHBoxLayout();row.addWidget(QLabel('时长 / 秒'));self.seconds=QDoubleSpinBox();self.seconds.setRange(10,180);self.seconds.setValue(30);self.seconds.setDecimals(0);row.addWidget(self.seconds,1);parameters.addLayout(row);right.addWidget(self.parameters)
        self.engine_note=QLabel();self.engine_note.setWordWrap(True);parameters.addWidget(self.engine_note)
        self.last_kind='music';self.music_seconds=30.;self.sfx_seconds=5.
        self.kind.currentIndexChanged.connect(self.update_kind);self.prompt.textChanged.connect(self.update_kind);self.update_kind()
        self.prompt.setPlaceholderText('描述想要的配乐或游戏音效，例如：层层推进的史诗战斗配乐；或金属剑碰撞后短促清脆的回响。')
        self.note=QLabel();self.note.setWordWrap(True);right.addWidget(self.note)
        from .audio_prompt_ui import AudioPromptController
        self.prompt_tools=AudioPromptController(self,right)
        self.page.addWidget(self.left);self.page.addWidget(self.right);self.page.setStretchFactor(0,3);self.page.setStretchFactor(1,1)
        from PySide6.QtWidgets import QAbstractItemView
        self.history=QListWidget();self.history.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.history.itemDoubleClicked.connect(self.open_history)
        history_page=QWidget();history_layout=QVBoxLayout(history_page);history_layout.addWidget(self.history,1)
        history_actions=QHBoxLayout()
        for title,all_cached in [('清除选中',False),('清空此类缓存',True)]:
            button=QPushButton(title);button.clicked.connect(lambda _=False,all_cached=all_cached:w.clear_result_cache('audio',all_cached));history_actions.addWidget(button);w.assets_dialog.cache_buttons.append(button)
        history_layout.addLayout(history_actions);w.assets_dialog.tabs.addTab(history_page,'音频')
        self.load_history()

    def position(self,value):
        if not self.slider.isSliderDown():self.slider.setValue(value)
        self.clock.setText(f'{value//60000:02d}:{value//1000%60:02d}')

    def toggle(self):
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        elif self.manifest:
            if self.player.source().isEmpty():self.player.setSource(QUrl.fromLocalFile(str(self.audio)))
            self.player.play()

    def stop(self):self.player.stop();self.player.setSource(QUrl())

    def effective_kind(self):
        from .audio_routing import resolve_kind
        return resolve_kind(self.prompt.toPlainText(),self.kind.currentData())

    def update_kind(self,*_):
        selected=self.effective_kind()
        if selected!=self.last_kind:
            if self.last_kind=='music':self.music_seconds=self.seconds.value()
            else:self.sfx_seconds=self.seconds.value()
            self.last_kind=selected;self.seconds.setDecimals(1 if selected=='sfx' else 0)
            self.seconds.setRange(.5,5) if selected=='sfx' else self.seconds.setRange(10,180)
            self.seconds.setValue(self.sfx_seconds if selected=='sfx' else self.music_seconds)
        self.engine_note.setText('游戏音效 · 最长5秒，保留自然衰减。' if selected=='sfx' else '背景配乐 · 独立生成，不计算视频画面。')

    def enqueue(self):
        w=self.window
        if w.preparing:return
        if not self.config:raise ValueError('独立音频模型尚未完成安装与验证。')
        kind=self.effective_kind()
        config=self.config.get('woosh',{}) if kind=='sfx' else self.config
        if not config.get('validated'):raise ValueError('游戏音效模型尚未完成安装与验证。')
        intent=getattr(w,'generation_intent',None);value=intent.current() if intent else None
        if value:
            prepared=dict(prompt=value['positive'],negative=value['negative'],source_brief=value['source']['requirement'],caption_english=value.get('english'),prompt_record=value['record'])
            from .audio_prompt import fingerprint
            prepared['caption_fingerprint']=fingerprint(prepared['prompt'],prepared['negative'])
        else:prepared=self.prompt_tools.snapshot()
        seed=int(w.seed.text());seed=secrets.randbelow(2**53) if seed==-1 else seed
        if not 0<=seed<2**64:raise ValueError('种子范围不正确。')
        folder=self.data/'audio'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]);folder.mkdir(parents=True)
        params=dict(prepared,mode='audio',backend='standalone',seconds=self.seconds.value(),seed=seed,
            audio_kind=kind,audio_settings=config.copy(),intent_settings=w.intent_controller.config,url=w.client.url if w.connected else None)
        if intent:intent.record(params)
        write_json(folder/'job.json',dict(kind='audio',status='queued',params=params))
        item=QListWidgetItem('音频 · 等待');w.queue_list.addItem(item);w.pending.append((None,params,folder,item));w.start_next()

    def start(self,params,folder,item):
        from .audio_generation import generate
        w=self.window;cancel=threading.Event();w.current=dict(folder=folder,params=params,cancel=cancel,client=None)
        self.player.pause();w.video_controller.player.stop();w.task_display.start();w.progress.setRange(0,0);item.setText('音频 · 生成中')
        write_json(folder/'job.json',dict(kind='audio',status='running',params=params))
        def event(kind,value):
            if kind in ('audio_stage','intent_stage'):w.status.setText(value['message'])
            elif kind=='audio_process':w.current.update(process_pid=value['pid'],owned_job=value['owner'])
            elif kind in ('result','error','cancelled'):
                status='completed' if kind=='result' else 'cancelled' if kind=='cancelled' else 'failed'
                w.status.setText('音频生成完成' if kind=='result' else '音频已取消' if kind=='cancelled' else '音频生成失败：'+str(value))
                w.current=None;w.task_display.finish(status);w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' else 0)
                item.setText('音频 · '+('完成' if kind=='result' else '已取消' if kind=='cancelled' else '失败'))
                write_json(folder/'job.json',dict(kind='audio',status=status,params=params,error=None if kind=='result' else str(value)))
                if kind=='result':self.load(value['manifest']);self.load_history()
                else:self.note.setText(str(value))
                w.connect_button.setEnabled(True);QTimer.singleShot(0,w.start_next)
        w.launch(lambda emit:generate(folder,params,cancel,emit),event)

    def load(self,path):
        from .video_audio import read_audio
        value=json.loads(Path(path).read_text('utf-8'))
        if value['status']!='completed':raise ValueError(value.get('error','音频尚未完成。'))
        self.player.stop();self.manifest=Path(path);self.audio=Path(value['audio']);self.player.setSource(QUrl.fromLocalFile(str(self.audio)))
        self.prompt_tools.remember_caption(value.get('params',{}),value.get('caption'))
        for control in (self.play,self.slider,self.export):control.setEnabled(True)
        samples=read_audio(self.audio,value['duration_seconds']);mono=np.abs(samples).mean(axis=0)
        self.wave.values=np.array([np.max(chunk) for chunk in np.array_split(mono,400)]);self.wave.update()
        self.title.setText(('游戏音效' if value.get('params',{}).get('audio_kind')=='sfx' else '背景配乐')+' · '+str(round(value['duration_seconds'],1))+'秒')
        self.note.setText('音频已就绪，已检查配乐时长与收尾，可试听或导出。' if value.get('duration_integrity') else '音频已就绪，可试听或导出。')

    def save(self):
        if not self.manifest:return
        path,_=QFileDialog.getSaveFileName(self.window,'导出音频','music.wav','音频 (*.wav)')
        if not path:return
        try:
            target=self.window.cache_store.validate_export(path);shutil.copyfile(self.audio,target)
            self.window.cache_store.record_save(target,'audio',self.manifest);self.note.setText('音频已导出。')
        except (ValueError,OSError) as exc:self.note.setText(str(exc))

    def load_history(self):
        self.history.clear()
        for path in sorted((self.data/'audio').glob('*/audio.json'),reverse=True):
            try:value=json.loads(path.read_text('utf-8'));status=value['status'];title=value['params'].get('source_brief',value['params']['prompt'])
            except (OSError,ValueError,KeyError,TypeError):continue
            item=QListWidgetItem(title[:35]+' · '+{'completed':'完成','failed':'失败','cancelled':'已取消','running':'生成中'}.get(status,status))
            item.setData(Qt.ItemDataRole.UserRole,str(path));item.setData(Qt.ItemDataRole.UserRole+1,str(path.parent));self.history.addItem(item)

    def open_history(self,item):
        try:
            self.window.workbench.select_category('audio');self.load(item.data(Qt.ItemDataRole.UserRole));self.window.assets_dialog.close()
        except (ValueError,OSError) as exc:self.note.setText(str(exc))
