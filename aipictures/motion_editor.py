"""Optional per-character motion editing; automatic generation requires no manual edits."""
from copy import deepcopy
import math

from PySide6.QtCore import Qt,QPointF,QRectF,Signal,QTimer
from PySide6.QtGui import QPainter,QPen,QColor,QPixmap
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QPushButton,QCheckBox,QDialogButtonBox)

from .character_profile import JOINT_NAMES,LIMBS,COLORS
from .motion_clip import ACTIONS,JOINT_LABELS,make_clip,save_clip,validate_clip


class PoseCanvas(QWidget):
    changed=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent); self.rig=None; self.reference=QPixmap(); self.dragged=None
        self.setMinimumSize(320,360); self.setMouseTracking(True)
        self.setToolTip('拖动彩色关节。脚踝、脚跟和脚尖分别控制；每条腿只有一组脚部节点。')
        self.show_reference=True

    def set_pose(self,rig,reference=None):
        self.rig=deepcopy(rig); self.dragged=None
        if reference: self.reference=QPixmap(str(reference))
        self.update()

    def canvas_rect(self):
        scale=min((self.width()-20)/768,(self.height()-20)/1024)
        return QRectF((self.width()-768*scale)/2,(self.height()-1024*scale)/2,768*scale,1024*scale)

    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=self.canvas_rect(); painter.fillRect(rect,QColor('#f1f2f4'))
        if self.show_reference and not self.reference.isNull():
            painter.setOpacity(.38); painter.drawPixmap(rect,self.reference,QRectF(self.reference.rect())); painter.setOpacity(1)
        painter.save(); painter.translate(rect.topLeft()); scale=rect.width()/768; painter.scale(scale,scale)
        painter.setPen(QPen(QColor('#b6bac2'),1)); painter.drawLine(20,978,748,978)
        if self.rig:
            p=self.rig['joints']
            for i,(a,b) in enumerate(LIMBS):
                painter.setPen(QPen(QColor(COLORS[i%len(COLORS)]),5)); painter.drawLine(QPointF(*p[JOINT_NAMES[a]][:2]),QPointF(*p[JOINT_NAMES[b]][:2]))
            for side,color in (('right','#d28700'),('left','#00a7c9')):
                painter.setPen(QPen(QColor(color),5))
                for a,b in ((side+'_ankle',side+'_heel'),(side+'_heel',side+'_toe')):
                    painter.drawLine(QPointF(*p[a][:2]),QPointF(*p[b][:2]))
            for i,(name,point) in enumerate(p.items()):
                painter.setPen(QPen(QColor('white'),2)); painter.setBrush(QColor(COLORS[i%len(COLORS)]))
                painter.drawEllipse(QPointF(*point[:2]),9 if name==self.dragged else 6,9 if name==self.dragged else 6)
        painter.restore(); painter.end()

    def rig_point(self,position):
        rect=self.canvas_rect(); return ((position.x()-rect.x())*768/rect.width(),(position.y()-rect.y())*1024/rect.height())

    def mousePressEvent(self,event):
        if not self.rig or event.button()!=Qt.MouseButton.LeftButton: return
        x,y=self.rig_point(event.position()); radius=14*768/self.canvas_rect().width()
        closest=min(self.rig['joints'],key=lambda name:math.dist((x,y),self.rig['joints'][name][:2]))
        if math.dist((x,y),self.rig['joints'][closest][:2])<=radius:
            self.dragged=closest; self.update()

    def mouseMoveEvent(self,event):
        if not self.dragged: return
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
        super().__init__(parent); self.analysis=analysis; self.motion=deepcopy(clip)
        self.setWindowTitle(ACTIONS[clip['action']][0]+' · 完整动作骨骼'); self.resize(790,850)
        available=self.screen().availableGeometry(); self.resize(min(790,available.width()-32),min(850,available.height()-48))
        layout=QVBoxLayout(self)
        note=QLabel('自动适配已生成完整动作。可直接保存使用，也可选择某帧拖动关节。\n先校准基准可改变全周期比例；逐帧编辑只修改所选帧。脚跟/脚尖用于定位，鞋面细节仍由模型生成。\n'+analysis.get('layout_note',''))
        if analysis.get('direction')=='left': note.setText(note.text()+'\n编辑使用向右标准坐标，导出恢复参考图的向左朝向。')
        note.setWordWrap(True); layout.addWidget(note)
        row=QHBoxLayout(); self.choice=QComboBox(); self.choice.addItem('基准骨架 · 调整角色比例',-1)
        for i in range(clip['frame_count']): self.choice.addItem(f'动作帧 {i+1} / {clip["frame_count"]}',i)
        row.addWidget(self.choice,1); self.play=QPushButton('预览骨骼'); row.addWidget(self.play)
        self.overlay=QCheckBox('显示参考图'); self.overlay.setChecked(True); row.addWidget(self.overlay); layout.addLayout(row)
        self.canvas=PoseCanvas(self); layout.addWidget(self.canvas,1)
        self.message=QLabel(''); self.message.setWordWrap(True); layout.addWidget(self.message)
        actions=QHBoxLayout(); reset=QPushButton('重置当前帧'); reset.clicked.connect(self.reset_frame); actions.addWidget(reset)
        reset_all=QPushButton('恢复自动周期'); reset_all.clicked.connect(self.reset_all); actions.addWidget(reset_all); actions.addStretch(); layout.addLayout(actions)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存并用于生成')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        self.buttons.accepted.connect(self.save); self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
        self.choice.currentIndexChanged.connect(self.select_frame); self.canvas.changed.connect(self.edited)
        self.overlay.toggled.connect(self.toggle_reference)
        self.timer=QTimer(self); self.timer.timeout.connect(lambda:self.choice.setCurrentIndex(1+self.choice.currentIndex()%self.motion['frame_count']))
        self.play.clicked.connect(self.toggle_play); self.select_frame()

    def select_frame(self):
        index=self.choice.currentData()
        self.canvas.set_pose(self.motion['base_rig'] if index==-1 else self.motion['frames'][index],self.analysis['rgba'])

    def edited(self,rig):
        self.timer.stop(); self.play.setText('预览骨骼')
        try:
            if self.choice.currentData()==-1:
                self.motion=make_clip(rig,self.motion['source_sha256'],self.motion['action'],self.motion['frame_count'],self.motion['fps'])
            else:
                self.motion['frames'][self.choice.currentData()]=rig; self.motion['edited']=True
                validate_clip(self.motion)
            self.message.setText('本次修改会写入相应姿态图，下一次生成使用此完整周期。')
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
        except (ValueError,KeyError) as exc:
            self.message.setText(str(exc)); self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)

    def toggle_reference(self,checked):
        self.canvas.show_reference=checked; self.canvas.update()

    def toggle_play(self):
        if self.timer.isActive(): self.timer.stop(); self.play.setText('预览骨骼')
        else: self.timer.start(round(1000/self.motion['fps'])); self.play.setText('暂停')

    def reset_frame(self):
        from .motion_clip import pose_at
        index=self.choice.currentData()
        if index==-1: return
        self.motion['frames'][index]=pose_at(self.motion['base_rig'],index/self.motion['frame_count'],self.motion['action'])
        self.select_frame()

    def reset_all(self):
        self.motion=make_clip(self.motion['base_rig'],self.motion['source_sha256'],self.motion['action'],self.motion['frame_count'],self.motion['fps'])
        self.select_frame(); self.message.setText('已恢复按当前基准生成的完整周期。')

    def save(self):
        try: save_clip(self.motion)
        except ValueError as exc: self.message.setText(str(exc)); return
        self.timer.stop(); self.accept()

    def done(self,result):
        self.timer.stop(); super().done(result)
