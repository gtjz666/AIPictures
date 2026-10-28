"""Read-only, full-resolution image inspection independent of animation playback."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QGraphicsView, QGraphicsScene, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QCheckBox)


class ImageView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = None
        self.fit_mode = True
        self.smooth=True
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        tile = QPixmap(32, 32); tile.fill(QColor('#f7f8fa'))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 16, 16, QColor('#e8eaed'))
        painter.fillRect(16, 16, 16, 16, QColor('#e8eaed'))
        painter.end()
        self.setBackgroundBrush(QBrush(tile))

    def load(self, pixmap):
        self.scene().clear()
        self.item = self.scene().addPixmap(pixmap)
        self.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation if self.smooth else Qt.TransformationMode.FastTransformation)
        self.setSceneRect(self.item.boundingRect())
        self.fit_mode = True
        QTimer.singleShot(0, self.fit_image)

    def fit_image(self):
        if self.item is None: return
        self.fit_mode = True
        self.fitInView(self.item.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._updated()

    def zoom(self, factor):
        if self.item is None: return
        current = self.transform().m11()
        target = max(.02, min(16, current * factor))
        self.fit_mode = False
        self.scale(target / current, target / current)
        self._updated()

    def original_size(self):
        if self.item is None: return
        self.fit_mode = False
        self.resetTransform()
        self.centerOn(self.item)
        self._updated()

    def _updated(self):
        scale = self.transform().m11()
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,self.smooth)
        self.zoom_changed.emit(scale)

    def set_smooth(self,enabled):
        self.smooth=enabled
        if self.item is not None:
            self.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation if enabled else Qt.TransformationMode.FastTransformation)
        self._updated()

    def wheelEvent(self, event):
        if event.angleDelta().y():
            self.zoom(1.25 if event.angleDelta().y() > 0 else .8)
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode and self.item is not None:
            QTimer.singleShot(0, self.fit_image)


class ImageViewer(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.source_path = None
        self.setWindowTitle('图片预览')
        self.setMinimumSize(480, 360); self.resize(1100, 820)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        layout = QVBoxLayout(self); controls = QHBoxLayout()
        self.info = QLabel(); controls.addWidget(self.info, 1)
        self.zoom_label = QLabel(); controls.addWidget(self.zoom_label)
        self.view = ImageView()
        self.zoom_out = QPushButton('－'); self.zoom_out.clicked.connect(lambda: self.view.zoom(.8))
        self.zoom_in = QPushButton('＋'); self.zoom_in.clicked.connect(lambda: self.view.zoom(1.25))
        self.original = QPushButton('100%'); self.original.clicked.connect(self.view.original_size)
        self.fit = QPushButton('适应窗口'); self.fit.clicked.connect(self.view.fit_image)
        self.smoothing=QCheckBox('平滑缩放'); self.smoothing.setChecked(True)
        self.smoothing.setToolTip('关闭后按原像素显示，适合检查像素画。')
        self.smoothing.toggled.connect(self.view.set_smooth); controls.addWidget(self.smoothing)
        close = QPushButton('关闭'); close.clicked.connect(self.close)
        for button in (self.zoom_out, self.zoom_in, self.original, self.fit, close):
            button.setAutoDefault(False); controls.addWidget(button)
        layout.addLayout(controls); layout.addWidget(self.view, 1)
        layout.addWidget(QLabel('滚轮缩放 · 拖动查看细节 · Esc 关闭'))
        self.view.zoom_changed.connect(lambda scale: self.zoom_label.setText(f'{scale * 100:.0f}%'))

    def open_image(self, path):
        path = Path(path).resolve()
        if path != self.source_path or not self.isVisible():
            pixmap = QPixmap(str(path))
            if pixmap.isNull(): raise ValueError('无法读取图片：' + str(path))
            self.source_path = path; self.view.load(pixmap)
            self.info.setText(f'{path.name} · {pixmap.width()} × {pixmap.height()}')
        available = self.parentWidget().screen().availableGeometry()
        self.resize(min(self.width(), available.width() - 40), min(self.height(), available.height() - 60))
        self.show(); self.raise_(); self.activateWindow()
