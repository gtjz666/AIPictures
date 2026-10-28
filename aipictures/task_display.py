"""Task name, progress and monotonic elapsed time, independent of worker events."""
import time
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QProgressBar,QSizePolicy
from PySide6.QtCore import Qt,QTimer
from PySide6.QtCore import Signal


def task_name(params):
    from .animation_actions import ACTIONS
    if params.get('mode')=='walk': return ACTIONS.get(params.get('action','walk'),('动作',))[0]+'动画'
    return '工作流生成' if params.get('mode')=='workflow_editor' else '图片生成'


class TaskLabel(QLabel):
    def __init__(self,owner):
        super().__init__('等待生成'); self.owner=owner; self.setWordWrap(True)

    def setText(self,text):
        self.setToolTip(str(text))
        display=getattr(self.owner,'task_display',None)
        if display: display.record_stage(str(text))
        current=getattr(self.owner,'current',None)
        if current:
            value=task_name(current['params'])
            if '失败' in text: value+=' · 失败'
            elif '取消' in text: value+=(' · 取消中' if '正在' in text else ' · 已取消')
            elif '完成' in text or '已保存' in text: value+=' · 完成'
            elif '断开' in text: value+=' · 引擎断开'
        else:
            value=('引擎已连接' if str(text).startswith('已连接') else
                   '引擎未连接' if any(word in str(text) for word in ('未连接','连接失败','已断开')) else str(text))
            if len(value)>26: value=value[:25]+'…'
        super().setText(value)


class TaskProgress(QProgressBar):
    rangeChanged=Signal()
    def setRange(self,minimum,maximum):
        super().setRange(minimum,maximum); self.rangeChanged.emit()


class TaskDisplay(QWidget):
    def __init__(self,owner):
        super().__init__(owner); self.setObjectName('taskDisplay')
        layout=QVBoxLayout(self); layout.setContentsMargins(10,10,10,10)
        heading=QLabel('当前任务'); heading.setObjectName('muted'); layout.addWidget(heading)
        row=QHBoxLayout(); self.status=TaskLabel(owner); self.percent=QLabel('0%')
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.percent.setFixedWidth(45); self.percent.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        row.setSpacing(4)
        row.addWidget(self.status,1); row.addWidget(self.percent); layout.addLayout(row)
        self.progress=TaskProgress(); self.progress.setRange(0,100); self.progress.setValue(0)
        self.progress.setMinimumWidth(0)
        self.progress.setTextVisible(False); self.progress.setMaximumHeight(5); layout.addWidget(self.progress)
        self.progress.valueChanged.connect(self.update_percent); self.progress.rangeChanged.connect(self.update_percent)
        self.elapsed=QLabel('尚未开始'); self.elapsed.setWordWrap(True); self.elapsed.setObjectName('muted'); layout.addWidget(self.elapsed)
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
        if self.started is None: return
        for words,label in ((('透明','分离','抠图'),'透明处理'),(('导出','保存连续帧','打包'),'保存资源'),
            (('亮度','偏色','颜色'),'颜色校验'),
            (('采样','推理','模型处理','动作生成','节点'),'模型推理'),(('排队','等待引擎'),'等待引擎'),
            (('参考','骨骼','准备','描述'),'准备素材')):
            if any(word in text for word in words): self.stage=label; break
        self.update_elapsed()

    def update_elapsed(self):
        seconds=int(self.seconds()); hours,remaining=divmod(seconds,3600); minutes,seconds=divmod(remaining,60)
        duration=f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'
        self.elapsed.setText(('已用时 ' if self.started is not None else '耗时 ')+duration+' · '+self.stage)

    def update_percent(self,*_):
        p=self.progress
        if p.maximum()==p.minimum(): self.percent.setText('…')
        else: self.percent.setText(f'{max(0,round(100*(p.value()-p.minimum())/(p.maximum()-p.minimum())))}%')
