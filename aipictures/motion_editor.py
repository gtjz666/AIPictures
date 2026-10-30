"""Optional per-character motion editing; automatic generation requires no manual edits."""
from copy import deepcopy
import math

from PySide6.QtCore import Qt,QPointF,QRectF,Signal,QTimer,QElapsedTimer
from PySide6.QtGui import QPainter,QPen,QColor,QPixmap,QImage,QIcon,QKeySequence,QShortcut
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QPushButton,QCheckBox,QDialogButtonBox,QSlider,QToolButton,QScrollArea)

from .character_profile import JOINT_NAMES,LIMBS,COLORS
from .motion_clip import ACTIONS,JOINT_LABELS,make_clip,save_clip,validate_clip,sample_clip,paint_rig,with_visual_bounds
from .animation_actions import stage_label
from .motion_preview import palette_from_reference,draw_puppet


class PoseCanvas(QWidget):
    changed=Signal(object)
    interaction_started=Signal()
    def __init__(self,parent=None):
        super().__init__(parent); self.rig=None; self.reference=QPixmap(); self.dragged=None
        self.setMinimumSize(280,280); self.setMouseTracking(True)
        self.setToolTip('拖动彩色关节。脚踝、脚跟和脚尖分别控制；每条腿只有一组脚部节点。')
        self.show_reference=True; self.show_puppet=True; self.palette={}; self.reference_path=None; self.frame_caption=''

    def set_pose(self,rig,reference=None):
        self.rig=deepcopy(rig); self.dragged=None
        if reference and str(reference)!=self.reference_path:
            self.reference=QPixmap(str(reference)); self.reference_path=str(reference)
        self.update()

    def canvas_rect(self):
        scale=min((self.width()-20)/768,(self.height()-20)/1024)
        return QRectF((self.width()-768*scale)/2,(self.height()-1024*scale)/2,768*scale,1024*scale)

    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=self.canvas_rect(); painter.fillRect(rect,QColor('#f1f2f4'))
        if self.show_reference and not self.reference.isNull():
            painter.setOpacity(.18 if self.show_puppet else .38); painter.drawPixmap(rect,self.reference,QRectF(self.reference.rect())); painter.setOpacity(1)
        painter.save(); painter.translate(rect.topLeft()); scale=rect.width()/768; painter.scale(scale,scale)
        painter.setPen(QPen(QColor('#b6bac2'),1)); painter.drawLine(20,978,748,978)
        if self.rig:
            p=self.rig['joints']
            if self.show_puppet and self.palette:
                painter.setOpacity(.82); draw_puppet(painter,self.rig,self.palette); painter.setOpacity(1)
            for i,(a,b) in enumerate(LIMBS):
                painter.setPen(QPen(QColor(COLORS[i%len(COLORS)]),5)); painter.drawLine(QPointF(*p[JOINT_NAMES[a]][:2]),QPointF(*p[JOINT_NAMES[b]][:2]))
            for side,color in (('right','#d28700'),('left','#00a7c9')):
                painter.setPen(QPen(QColor(color),5))
                for a,b in ((side+'_ankle',side+'_heel'),(side+'_heel',side+'_toe')):
                    painter.drawLine(QPointF(*p[a][:2]),QPointF(*p[b][:2]))
            for i,(name,point) in enumerate(p.items()):
                painter.setPen(QPen(QColor('white'),2)); painter.setBrush(QColor(COLORS[i%len(COLORS)]))
                painter.drawEllipse(QPointF(*point[:2]),9 if name==self.dragged else 6,9 if name==self.dragged else 6)
        painter.restore()
        painter.setPen(QColor('#253247')); painter.setBrush(QColor(255,255,255,225))
        painter.drawRoundedRect(QRectF(rect.left()+8,rect.top()+8,min(rect.width()-16,300),28),6,6)
        painter.drawText(QRectF(rect.left()+16,rect.top()+8,rect.width()-25,28),Qt.AlignmentFlag.AlignVCenter,self.frame_caption)
        painter.end()

    def rig_point(self,position):
        rect=self.canvas_rect(); return ((position.x()-rect.x())*768/rect.width(),(position.y()-rect.y())*1024/rect.height())

    def mousePressEvent(self,event):
        if not self.rig or event.button()!=Qt.MouseButton.LeftButton: return
        self.interaction_started.emit()
        x,y=self.rig_point(event.position()); radius=14*768/self.canvas_rect().width()
        closest=min(self.rig['joints'],key=lambda name:math.dist((x,y),self.rig['joints'][name][:2]))
        if math.dist((x,y),self.rig['joints'][closest][:2])<=radius:
            self.dragged=closest; self.update()

    def mouseMoveEvent(self,event):
        if not self.dragged:
            if self.rig:
                x,y=self.rig_point(event.position())
                name=min(self.rig['joints'],key=lambda key:math.dist((x,y),self.rig['joints'][key][:2]))
                self.setToolTip(JOINT_LABELS.get(name,name)+' · '+self.frame_caption)
            return
        x,y=self.rig_point(event.position()); previous=self.rig['joints'][self.dragged]
        point=[max(0,min(767,x)),max(0,min(1023,y)),1]
        if self.dragged.endswith('_ankle'):
            side=self.dragged.split('_')[0]
            for part in ('heel','toe'):
                target=self.rig['joints'][side+'_'+part]
                target[0]+=point[0]-previous[0]; target[1]+=point[1]-previous[1]
        self.rig['joints'][self.dragged]=point
        self.changed.emit(deepcopy(self.rig)); self.update()

    def mouseReleaseEvent(self,event):
        self.dragged=None; self.update()


class MotionDialog(QDialog):
    def __init__(self,analysis,clip,parent=None):
        if not clip.get('edited') and (clip.get('generator_version',2)<3 or
                analysis.get('geometry',{}).get('subject_bbox') and not clip['base_rig'].get('visual_bounds')):
            clip=make_clip(with_visual_bounds(clip['base_rig'],analysis),clip['source_sha256'],clip['action'],clip['frame_count'],clip['fps'])
        super().__init__(parent); self.analysis=analysis; self.motion=deepcopy(clip)
        self.setWindowTitle(ACTIONS[clip['action']][0]+' · 完整动作骨骼')
        available=self.screen().availableGeometry(); self.resize(min(900,available.width()-32),min(960,available.height()-48))
        self.clock=QElapsedTimer(); self.playing_update=False
        self.changed_frames=set(clip.get('edited_frames',[]))
        layout=QVBoxLayout(self)
        note=QLabel('点击下方帧卡或拖动时间条选帧，拖关节后播放完整周期。人物示意用于动作校对，不是 AI 生成结果。\n基准修改会更新全周期；逐帧修改只影响该关键帧。'+analysis.get('layout_note',''))
        if clip['action']=='jump' and clip['base_rig'].get('visual_bounds'):
            note.setText(note.text()+'\n自动跳跃按角色头顶余量限制高度，保留画面上方空间；不会为此缩小角色。')
        if analysis.get('direction')=='left': note.setText(note.text()+'\n编辑使用向右标准坐标，导出恢复参考图的向左朝向。')
        note.setWordWrap(True); layout.addWidget(note)
        row=QHBoxLayout(); self.choice=QComboBox(); self.choice.addItem('基准骨架 · 调整角色比例',-1)
        for i in range(clip['frame_count']): self.choice.addItem(f'动作帧 {i+1} / {clip["frame_count"]}',i)
        row.addWidget(self.choice,1)
        self.preview_mode=QComboBox(); self.preview_mode.addItems(['骨骼 + 人物示意','仅骨骼']); row.addWidget(self.preview_mode)
        self.overlay=QCheckBox('参考图底图'); self.overlay.setChecked(True); row.addWidget(self.overlay); layout.addLayout(row)
        self.frame_label=QLabel(); self.frame_label.setStyleSheet('font-size:16px;font-weight:600;'); layout.addWidget(self.frame_label)
        self.canvas=PoseCanvas(self); layout.addWidget(self.canvas,1)
        self.canvas.palette=palette_from_reference(analysis.get('rgba'),clip['base_rig'])
        timeline=QWidget(); tiles=QHBoxLayout(timeline); tiles.setContentsMargins(0,0,0,0); tiles.setSpacing(4)
        self.frame_buttons=[]
        for i in range(clip['frame_count']):
            button=QToolButton(); button.setCheckable(True); button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setMinimumWidth(44); button.clicked.connect(lambda _=False,index=i:self.choose_frame(index))
            button.setStyleSheet('QToolButton:checked {background:#dbe8ff;border:2px solid #4c79cc;border-radius:5px;}')
            self.frame_buttons.append(button); tiles.addWidget(button)
        tiles.addStretch()
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(timeline); scroll.setFixedHeight(91)
        self.timeline_scroll=scroll
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); layout.addWidget(scroll)
        self.slider=QSlider(Qt.Orientation.Horizontal); self.slider.setRange(0,clip['frame_count']-1); layout.addWidget(self.slider)
        controls=QHBoxLayout(); previous=QPushButton('上一帧'); following=QPushButton('下一帧')
        previous.clicked.connect(lambda:self.step(-1)); following.clicked.connect(lambda:self.step(1))
        self.play=QPushButton('▶ 播放完整动画'); stop=QPushButton('停止 / 回到首帧'); stop.clicked.connect(self.stop_play)
        self.loop=QCheckBox('循环'); self.loop.setChecked(clip.get('loop',True))
        self.speed=QComboBox()
        for label,value in (('0.5 倍',.5),('1 倍',1.),('1.5 倍',1.5)): self.speed.addItem(label,value)
        self.speed.setCurrentIndex(1)
        for widget in (previous,self.play,stop,following,self.loop,self.speed): controls.addWidget(widget)
        layout.addLayout(controls)
        self.duration_label=QLabel(); layout.addWidget(self.duration_label)
        self.message=QLabel(''); self.message.setWordWrap(True); layout.addWidget(self.message)
        actions=QHBoxLayout(); reset=QPushButton('重置当前帧'); reset.clicked.connect(self.reset_frame); actions.addWidget(reset)
        reset_all=QPushButton('恢复自动周期'); reset_all.clicked.connect(self.reset_all); actions.addWidget(reset_all); actions.addStretch(); layout.addLayout(actions)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存并用于生成')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.accepted.connect(self.save); self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
        self.choice.currentIndexChanged.connect(self.select_frame); self.canvas.changed.connect(self.edited)
        self.canvas.interaction_started.connect(self.pause_for_edit)
        self.overlay.toggled.connect(self.toggle_reference)
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick)
        self.slider.valueChanged.connect(lambda value:self.choice.setCurrentIndex(value+1))
        self.slider.sliderPressed.connect(self.pause)
        self.choice.activated.connect(lambda _:self.select_frame())
        self.preview_mode.currentIndexChanged.connect(self.set_preview_mode)
        self.play.clicked.connect(self.toggle_play)
        self.shortcuts=[]
        for key,callback in (('Left',lambda:self.step(-1)),('Right',lambda:self.step(1)),('Space',self.toggle_play)):
            shortcut=QShortcut(QKeySequence(key),self); shortcut.activated.connect(callback); self.shortcuts.append(shortcut)
        self.refresh_tiles(); self.choice.setCurrentIndex(1); self.select_frame()

    def select_frame(self):
        if not self.playing_update: self.pause()
        index=self.choice.currentData()
        self.show_frame(index)

    def show_frame(self,index,pose=None):
        n=self.motion['frame_count']; fps=self.motion['fps']; phase=max(0,index)/(n if self.motion.get('loop',True) else n-1)
        title='基准骨架 · 调整角色比例' if index==-1 else f'第 {index+1} / {n} 帧 · '+stage_label(self.motion['action'],phase)
        self.frame_label.setText(title); self.canvas.frame_caption=title
        self.canvas.set_pose(pose or (self.motion['base_rig'] if index==-1 else self.motion['frames'][index]),self.analysis['rgba'])
        self.slider.blockSignals(True); self.slider.setValue(max(0,index)); self.slider.blockSignals(False)
        for i,button in enumerate(self.frame_buttons): button.setChecked(i==index)
        if index>=0: self.timeline_scroll.ensureWidgetVisible(self.frame_buttons[index])
        self.duration_label.setText(f'当前 {max(0,index)/fps:.2f} 秒 / 动作总长 {n/fps:.2f} 秒 · {n} 帧 · {fps} FPS · 空格播放，← → 逐帧')

    def refresh_tiles(self):
        for i,button in enumerate(self.frame_buttons):
            image=paint_rig(self.motion['frames'][i],(36,48)).convert('RGB')
            qimage=QImage(image.tobytes(),36,48,36*3,QImage.Format.Format_RGB888).copy()
            button.setIcon(QIcon(QPixmap.fromImage(qimage))); button.setIconSize(qimage.size())
            button.setText(str(i+1)+(' •' if i in self.changed_frames else ''))
            n=self.motion['frame_count'];phase=i/(n if self.motion.get('loop',True) else n-1)
            button.setToolTip(f'第 {i+1} 帧 · '+stage_label(self.motion['action'],phase))

    def set_preview_mode(self,index):
        self.canvas.show_puppet=index==0; self.canvas.update()

    def step(self,delta):
        self.pause(); index=max(0,self.choice.currentData())
        self.choice.setCurrentIndex(1+(index+delta)%self.motion['frame_count'])

    def choose_frame(self,index):
        self.pause(); self.choice.setCurrentIndex(index+1); self.show_frame(index)

    def edited(self,rig):
        self.pause()
        try:
            if self.choice.currentData()==-1:
                self.motion=make_clip(with_visual_bounds(rig,self.analysis),self.motion['source_sha256'],self.motion['action'],self.motion['frame_count'],self.motion['fps'])
                self.changed_frames.clear()
            else:
                self.motion['frames'][self.choice.currentData()]=rig; self.motion['edited']=True
                validate_clip(self.motion)
                self.changed_frames.add(self.choice.currentData())
            self.refresh_tiles()
            self.message.setText('本次修改会写入相应姿态图，下一次生成使用此完整周期。')
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
        except (ValueError,KeyError) as exc:
            self.message.setText(str(exc)); self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)

    def toggle_reference(self,checked):
        self.canvas.show_reference=checked; self.canvas.update()

    def toggle_play(self):
        if self.timer.isActive(): self.pause()
        else:
            self.choice.setCurrentIndex(1); self.clock.start(); self.timer.start(33); self.play.setText('Ⅱ 暂停播放')

    def pause(self):
        self.timer.stop(); self.play.setText('▶ 播放完整动画')

    def pause_for_edit(self):
        if self.timer.isActive(): self.pause(); self.show_frame(self.choice.currentData())

    def stop_play(self):
        self.pause(); self.choice.setCurrentIndex(1); self.show_frame(0)

    def tick(self):
        duration=self.motion['frame_count']/self.motion['fps']
        phase=self.clock.elapsed()/1000*self.speed.currentData()/duration
        if phase>=1 and not self.loop.isChecked():
            self.pause();self.choice.setCurrentIndex(self.motion['frame_count']);return
        phase%=1
        intervals=self.motion['frame_count'] if self.motion.get('loop',True) else self.motion['frame_count']-1
        index=min(self.motion['frame_count']-1,int(phase*intervals))
        self.playing_update=True; self.choice.setCurrentIndex(index+1); self.playing_update=False
        self.show_frame(index,sample_clip(self.motion,phase))

    def reset_frame(self):
        from .motion_clip import pose_at
        index=self.choice.currentData()
        if index==-1: return
        n=self.motion['frame_count'];phase=index/(n if self.motion.get('loop',True) else n-1)
        self.motion['frames'][index]=pose_at(self.motion['base_rig'],phase,self.motion['action'])
        self.changed_frames.discard(index); self.refresh_tiles(); self.select_frame()
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)

    def reset_all(self):
        self.motion=make_clip(with_visual_bounds(self.motion['base_rig'],self.analysis),self.motion['source_sha256'],self.motion['action'],self.motion['frame_count'],self.motion['fps'])
        self.changed_frames.clear(); self.refresh_tiles(); self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
        self.select_frame(); self.message.setText('已恢复按当前基准生成的完整周期。')

    def save(self):
        self.motion['edited_frames']=sorted(self.changed_frames)
        try: save_clip(self.motion)
        except ValueError as exc: self.message.setText(str(exc)); return
        self.timer.stop(); self.accept()

    def done(self,result):
        self.timer.stop(); super().done(result)
