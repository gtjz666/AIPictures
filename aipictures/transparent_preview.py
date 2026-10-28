from PySide6.QtCore import Qt, Signal,QPointF
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QLabel


class TransparentPreview(QLabel):
    """Checkerboard belongs to the viewer; exported pixels stay transparent."""
    activated = Signal()
    resized = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clickable = False

    def set_clickable(self, enabled):
        self.clickable = enabled
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.setToolTip('点击放大图片' if enabled else '')

    def mouseReleaseEvent(self, event):
        if self.clickable and event.button() == Qt.MouseButton.LeftButton and not self.pixmap().isNull():
            self.activated.emit()
        else:
            super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def paintEvent(self,event):
        painter=QPainter(self); tile=16
        for y in range(0,self.height(),tile):
            for x in range(0,self.width(),tile):
                painter.fillRect(x,y,tile,tile,QColor('#e8eaed' if (x//tile+y//tile)%2 else '#f7f8fa'))
        pixmap=self.pixmap()
        if pixmap and not pixmap.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,True)
            size=pixmap.deviceIndependentSize()
            painter.drawPixmap(QPointF((self.width()-size.width())/2,(self.height()-size.height())/2),pixmap)
        else:
            painter.setPen(QColor('#7d838d')); painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,self.text())
