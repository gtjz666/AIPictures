"""Compact task name and percentage; identifiers remain in logs and metadata."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QProgressBar,QSizePolicy
from PySide6.QtCore import Qt
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

    def update_percent(self,*_):
        p=self.progress
        if p.maximum()==p.minimum(): self.percent.setText('…')
        else: self.percent.setText(f'{max(0,round(100*(p.value()-p.minimum())/(p.maximum()-p.minimum())))}%')
