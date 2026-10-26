"""Compact desktop panels: settings accordion, assets drawer, reference/rig inspection."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
    QDialog, QLabel, QListWidget, QPushButton, QComboBox, QTabWidget, QPlainTextEdit)

from .storage import DATA


class Foldout(QWidget):
    def __init__(self, title, content, expanded=False):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6)
        toggle = QToolButton(); toggle.setText(title); toggle.setCheckable(True); toggle.setChecked(expanded)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        toggle.setMinimumHeight(32)
        layout.addWidget(toggle); layout.addWidget(content)
        content.setVisible(expanded)
        def changed(opened):
            content.setVisible(opened)
            toggle.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        toggle.toggled.connect(changed)


class AssetsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('素材与生成记录'); self.resize(820, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('双击生成记录查看图片；素材与工作流均保存在本地。'))
        tabs = QTabWidget(); layout.addWidget(tabs, 1)
        self.gallery = QListWidget(); tabs.addTab(self.gallery, '生成记录')
        files = QWidget(); fv = QVBoxLayout(files)
        for title, path in [('参考图与素材', DATA / 'references'), ('角色基准与骨骼', DATA / 'characters'),
                            ('本地工作流', DATA / 'workflows'), ('全部项目数据', DATA)]:
            button = QPushButton(title)
            button.clicked.connect(lambda _=False, path=path: self.open_folder(path)); fv.addWidget(button)
        fv.addStretch(); tabs.addTab(files, '素材文件夹')
        close = QPushButton('返回创作'); close.clicked.connect(self.close); layout.addWidget(close)

    @staticmethod
    def open_folder(path):
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class SkeletonDialog(QDialog):
    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.setWindowTitle(profile['title'] + ' / 骨骼预设'); self.resize(900, 860)
        self.profile = profile
        layout = QVBoxLayout(self)
        self.choice = QComboBox()
        for key, pose in profile['poses'].items(): self.choice.addItem(pose['title'], key)
        layout.addWidget(self.choice)
        tabs = QTabWidget(); layout.addWidget(tabs, 1)
        self.views = {}
        for key, title in [('reference', '角色基准'), ('image', 'OpenPose 条件图'), ('overlay', '骨骼叠加校对')]:
            label = QLabel(); label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(300, 450); self.views[key] = label; tabs.addTab(label, title)
        prompt_page = QWidget(); pv = QVBoxLayout(prompt_page)
        for title, text in [('角色固定提示词', profile['positive']), ('反向提示词', profile['negative'])]:
            pv.addWidget(QLabel(title)); box = QPlainTextEdit(text); box.setReadOnly(True); pv.addWidget(box, 1)
        tabs.addTab(prompt_page, '提示词')
        tabs.setCurrentIndex(2)
        notes = QLabel('18 关节侧视骨骼 · 面朝右 · 固定地面线。\n人工按图标定；裙下髋部和遮挡侧关节为估计值。伸手姿态是草案，尚未证明可用于动画。')
        notes.setWordWrap(True); layout.addWidget(notes)
        open_folder = QPushButton('打开骨骼文件与提示词'); open_folder.clicked.connect(lambda: AssetsDialog.open_folder(Path(profile['reference']).parent))
        layout.addWidget(open_folder)
        self.choice.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        pose = self.profile['poses'][self.choice.currentData()]
        self.paths = {'reference': self.profile['reference'], 'image': pose['image'], 'overlay': pose['overlay']}
        self.fit()

    def fit(self):
        for key, label in self.views.items():
            pixmap = QPixmap(self.paths[key])
            label.setPixmap(pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'paths'): QTimer.singleShot(0, self.fit)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.fit)
