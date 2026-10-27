"""Floating settings, cached results and reference/rig inspection."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
    QDialog, QLabel, QListWidget, QPushButton, QComboBox, QTabWidget, QPlainTextEdit,
    QScrollArea, QAbstractItemView)

from .storage import DATA


class SettingsDialog(QDialog):
    """Owns the real controls; closing/reopening never resets their values."""
    def __init__(self,title,content,parent,height=480):
        super().__init__(parent)
        self.setWindowTitle(title); self.setMinimumWidth(400); self.resize(470,height)
        layout=QVBoxLayout(self)
        heading=QLabel(title); heading.setStyleSheet('font-size:17px;font-weight:600;'); layout.addWidget(heading)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll.setWidget(content)
        layout.addWidget(scroll,1)
        note=QLabel('修改立即生效，用于下一次生成。'); note.setWordWrap(True); layout.addWidget(note)
        done=QPushButton('完成'); done.clicked.connect(self.close); layout.addWidget(done)

    def show_near(self,anchor):
        screen=anchor.screen().availableGeometry()
        self.resize(min(self.width(),screen.width()-32),min(self.height(),screen.height()-48))
        point=anchor.mapToGlobal(anchor.rect().topRight())
        x=min(point.x()+12,screen.right()-self.width()-12)
        y=max(screen.top()+12,min(point.y(),screen.bottom()-self.height()-12))
        self.move(max(screen.left()+12,x),y); self.show(); self.raise_(); self.activateWindow()


class AssetsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('素材与生成记录'); self.resize(820, 600)
        layout = QVBoxLayout(self)
        hint=QLabel('生成结果先放入本地缓存。需要长期保留时点“另存为”或“导出动画”，自行选择保存地址。')
        hint.setWordWrap(True); layout.addWidget(hint)
        tabs = QTabWidget(); self.tabs=tabs; layout.addWidget(tabs, 1)
        self.cache_buttons=[]
        for kind,title,attribute in [('image','图片缓存','gallery'),('walk','动画缓存','animations')]:
            page=QWidget(); pv=QVBoxLayout(page)
            listing=QListWidget(); listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            setattr(self,attribute,listing); pv.addWidget(listing,1)
            note=QLabel('双击预览；清理按整次生成任务处理，包含该任务的图片、参数与工作流副本。')
            note.setWordWrap(True); pv.addWidget(note)
            actions=QHBoxLayout()
            selected=QPushButton('清除选中'); selected.clicked.connect(lambda _=False,kind=kind:parent.clear_result_cache(kind,False))
            all_cached=QPushButton('清空此类缓存'); all_cached.clicked.connect(lambda _=False,kind=kind:parent.clear_result_cache(kind,True))
            actions.addWidget(selected); actions.addWidget(all_cached); pv.addLayout(actions)
            self.cache_buttons.extend([selected,all_cached]); tabs.addTab(page,title)
        saved=QWidget(); saved_layout=QVBoxLayout(saved)
        self.saved_files=QListWidget(); saved_layout.addWidget(self.saved_files,1)
        self.saved_files.itemDoubleClicked.connect(lambda item:QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole))))
        location=QPushButton('打开保存位置'); location.clicked.connect(self.open_saved_location); saved_layout.addWidget(location)
        tabs.addTab(saved,'已保存文件')
        files = QWidget(); fv = QVBoxLayout(files)
        for title, path in [('参考图与素材', DATA / 'references'), ('角色基准与骨骼', DATA / 'characters'),
                            ('本地工作流', DATA / 'workflows'), ('全部项目数据', DATA)]:
            button = QPushButton(title)
            button.clicked.connect(lambda _=False, path=path: self.open_folder(path)); fv.addWidget(button)
        fv.addStretch(); tabs.addTab(files, '素材文件夹')
        self.cache_status=QLabel('清理缓存会跳过正在运行和排队的任务，已另存的文件保留。'); self.cache_status.setWordWrap(True); layout.addWidget(self.cache_status)
        close = QPushButton('返回创作'); close.clicked.connect(self.close); layout.addWidget(close)

    def set_cache_busy(self,busy):
        for button in self.cache_buttons: button.setEnabled(not busy)

    def open_saved_location(self):
        item=self.saved_files.currentItem()
        if item: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(item.data(Qt.ItemDataRole.UserRole)).parent)))

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
