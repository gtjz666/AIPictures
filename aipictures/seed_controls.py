"""A visible random/fixed choice; -1 remains only the internal random sentinel."""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QHBoxLayout,QComboBox,QLineEdit,QPushButton,QLabel,QApplication


def install(window,form):
    row=QWidget();layout=QHBoxLayout(row);layout.setContentsMargins(0,0,0,0)
    window.seed_mode=QComboBox();window.seed_mode.addItem('每次随机','random');window.seed_mode.addItem('固定种子','fixed')
    window.seed=QLineEdit('-1');window.seed.setPlaceholderText('输入固定整数');window.seed.hide()
    layout.addWidget(window.seed_mode);layout.addWidget(window.seed,1);form.addRow('种子',row)
    last=['0']
    def mode_changed():
        random=window.seed_mode.currentData()=='random'
        if random:
            if window.seed.text()!='-1':last[0]=window.seed.text()
            window.seed.setText('-1')
        elif window.seed.text()=='-1':window.seed.setText(last[0])
        window.seed.setVisible(not random)
    def typed(text):
        window.seed_mode.blockSignals(True);window.seed_mode.setCurrentIndex(0 if text=='-1' else 1);window.seed_mode.blockSignals(False)
        window.seed.setVisible(text!='-1')
    window.seed_mode.currentIndexChanged.connect(mode_changed);window.seed.textChanged.connect(typed)
    actual=QWidget();a=QHBoxLayout(actual);a.setContentsMargins(0,0,0,0)
    window.actual_seed=QLineEdit();window.actual_seed.setReadOnly(True);window.actual_seed.setPlaceholderText('生成后显示实际值')
    copy=QPushButton('复制');copy.clicked.connect(lambda:copy_seed(window));reuse=QPushButton('复用')
    reuse.clicked.connect(lambda:window.seed.setText(window.actual_seed.text()) if window.actual_seed.text() else None)
    a.addWidget(window.actual_seed,1);a.addWidget(copy);a.addWidget(reuse);form.addRow('实际种子',actual)


def install_notice(window,layout):
    window.seed_notice=QLabel();window.seed_notice.setObjectName('muted')
    window.seed_notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    window.seed_notice.hide();layout.addWidget(window.seed_notice)


def show_seed(window,seed):
    value=str(seed) if isinstance(seed,int) and 0<=seed<2**64 else ''
    window.actual_seed.setText(value)
    window.seed_notice.setText('实际种子：'+value+' · 可在生成参数中复制或复用' if value else '此素材没有记录生成种子')
    # The current seed is available with copy/reuse in the sampling panel.


def copy_seed(window):
    if window.actual_seed.text():QApplication.clipboard().setText(window.actual_seed.text())


def from_folder(window,folder):
    for name in ('params.json','job.json','video.json','sequence.json'):
        try:
            record=json.loads((Path(folder)/name).read_text('utf-8'))
            seed=record.get('seed',record.get('params',{}).get('seed'))
            if isinstance(seed,int) and seed>=0:show_seed(window,seed);return
        except (OSError,ValueError,AttributeError):pass
    show_seed(window,None)
