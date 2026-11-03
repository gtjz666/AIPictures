"""Task name, progress and monotonic elapsed time, independent of worker events."""
import time
import re
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QProgressBar,QSizePolicy,QMessageBox
from PySide6.QtCore import Qt,QTimer
from PySide6.QtCore import Signal


def task_name(params):
    if params.get('mode')=='video':return '完整动画 · '+('H3' if params.get('engine')=='h3' else 'Wan2.2')
    if params.get('mode')=='smart_image':
        return '云端图片生成' if params.get('backend')=='api' else '智能本地生图' if params.get('smart') else '本地图片生成'
    from .animation_actions import ACTIONS
    if params.get('mode')=='walk': return ACTIONS.get(params.get('action','walk'),('动作',))[0]+'动画'
    return '工作流生成' if params.get('mode')=='workflow_editor' else '图片生成'


class TaskLabel(QLabel):
    def __init__(self,owner):
        super().__init__('等待生成'); self.owner=owner; self.setWordWrap(False);self.failure=''

    def setText(self,text):
        text=str(text)
        self.failure=text if any(word in text for word in ('失败','错误','无法','未完成')) else ''
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.failure else Qt.CursorShape.ArrowCursor)
        display=getattr(self.owner,'task_display',None)
        if display: display.record_stage(str(text))
        current=getattr(self.owner,'current',None)
        if current:
            value=task_name(current['params'])
            part=re.match(r'第\d+/\d+段',text)
            if part:value+=' · '+part.group()
            if self.failure: value+=' · 失败'
            elif '取消' in text: value+=(' · 取消中' if '正在' in text else ' · 已取消')
            elif '完成' in text or '已保存' in text: value+=' · 完成'
            elif '断开' in text: value+=' · 引擎断开'
        else:
            value=super().text()
            for words,name in ((('导出','选帧','精灵图'),'导出素材'),(('识别','需求'),'需求识别'),
                (('云端',),'云端图片生成'),(('动画',),'动画生成'),(('图片','生图'),'图片生成'),
                (('参考','上传','准备素材'),'准备素材'),(('连接','断开'),'引擎连接')):
                if any(word in text for word in words):value=name;break
            if self.failure:value=value.split(' · ')[0]+' · 失败'
            elif '取消' in text:value=value.split(' · ')[0]+' · 已取消'
            elif '完成' in text or '已导出' in text or '已保存' in text:value=value.split(' · ')[0]+' · 完成'
        super().setText(value)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.failure:
            QMessageBox.warning(self.owner,'任务未完成',self.failure)
        else:super().mouseReleaseEvent(event)


class TaskProgress(QProgressBar):
    rangeChanged=Signal()
    def setRange(self,minimum,maximum):
        super().setRange(minimum,maximum); self.rangeChanged.emit()


class TaskDisplay(QWidget):
    def __init__(self,owner):
        super().__init__(owner); self.setObjectName('taskDisplay')
        layout=QHBoxLayout(self); layout.setContentsMargins(10,4,10,4)
        self.status=TaskLabel(owner); self.percent=QLabel('0%')
        self.status.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred)
        self.percent.setFixedWidth(45); self.percent.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        self.status.setMinimumWidth(150);layout.addWidget(self.status)
        self.progress=TaskProgress(); self.progress.setRange(0,100); self.progress.setValue(0)
        self.progress.setMinimumWidth(0)
        self.progress.setTextVisible(False); self.progress.setMaximumHeight(5); layout.addWidget(self.progress,1);layout.addWidget(self.percent)
        self.progress.valueChanged.connect(self.update_percent); self.progress.rangeChanged.connect(self.update_percent)
        self.elapsed=QLabel('00:00'); self.elapsed.setObjectName('muted'); layout.addWidget(self.elapsed)
        self.detail=QLabel(self);self.detail.hide()
        self.setMaximumHeight(40)
        self.started=None; self.finished_seconds=0.; self.stage='准备'
        self.clock=QTimer(self); self.clock.setInterval(250); self.clock.timeout.connect(self.update_elapsed)

    def start(self):
        self.started=time.monotonic(); self.finished_seconds=0.; self.stage='准备'; self.clock.start(); self.update_elapsed()

    def seconds(self):
        return max(0.,time.monotonic()-self.started) if self.started is not None else self.finished_seconds

    def finish(self,status='completed'):
        self.finished_seconds=self.seconds(); self.started=None; self.clock.stop()
        self.stage={'completed':'完成','failed':'失败','cancelled':'已取消'}.get(status,status); self.update_elapsed()

    def record_stage(self,text):
        self.detail.setText(text[:220])
        self.detail.setToolTip(text)
        if self.started is None: return
        for words,label in ((('云端图片模型',),'云端生图'),(('整理画面需求',),'理解需求'),
            (('接收图片',),'保存资源'),(('透明','分离','抠图'),'透明处理'),(('导出','保存连续帧','打包'),'保存资源'),
            (('取消',),'等待后端停止'),(('下载',),'下载结果'),(('解码',),'解码动画帧'),
            (('编码','加载',),'准备模型与条件'),
            (('亮度','偏色','颜色'),'颜色校验'),
            (('采样','推理','模型处理','动作生成','节点'),'模型推理'),(('排队','等待引擎'),'等待引擎'),
            (('参考','骨骼','准备','描述'),'准备素材')):
            if any(word in text for word in words): self.stage=label; break
        self.update_elapsed()

    def update_elapsed(self):
        seconds=int(self.seconds()); hours,remaining=divmod(seconds,3600); minutes,seconds=divmod(remaining,60)
        duration=f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'
        self.elapsed.setText(duration)

    def update_percent(self,*_):
        p=self.progress
        if p.maximum()==p.minimum(): self.percent.setText('…')
        else: self.percent.setText(f'{max(0,round(100*(p.value()-p.minimum())/(p.maximum()-p.minimum())))}%')
