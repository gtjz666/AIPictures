from pathlib import Path
from PySide6.QtCore import Qt, Signal,QPointF,QRect
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QLabel


class TransparentPreview(QLabel):
    """Checkerboard belongs to the viewer; exported pixels stay transparent."""
    activated = Signal()
    resized = Signal()
    files_dropped = Signal(list)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clickable = False
        self.file_drop_enabled = False
        self.file_dragging = False
        self.source_hint = ''

    def set_source_hint(self,text:str):
        if text!=self.source_hint:
            self.source_hint=text;self.setAccessibleDescription(text);self.update()

    def enable_file_drop(self):
        self.file_drop_enabled = True
        self.setAcceptDrops(True)

    def drop_paths(self, mime):
        if not self.file_drop_enabled or not mime.hasUrls(): return []
        urls=mime.urls()
        allowed={'.png','.jpg','.jpeg','.webp','.bmp','.mp4','.gif','.mkv','.mov','.webm','.avi'}
        if not 1<=len(urls)<=1501 or any(not u.isLocalFile() for u in urls): return []
        paths=[Path(u.toLocalFile()) for u in urls]
        return paths if all(p.suffix.lower() in allowed for p in paths) else []

    def dragEnterEvent(self,event):
        if self.drop_paths(event.mimeData()):
            self.file_dragging=True;self.update();event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        if self.drop_paths(event.mimeData()):event.acceptProposedAction()
        else:event.ignore()

    def dragLeaveEvent(self,event):
        self.file_dragging=False;self.update();event.accept()

    def dropEvent(self,event):
        self.file_dragging=False;self.update()
        paths=self.drop_paths(event.mimeData())
        if paths:
            self.files_dropped.emit(paths);event.acceptProposedAction()
        else:event.ignore()

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
        if self.source_hint:
            painter.save()
            font=painter.font();font.setPixelSize(11);painter.setFont(font)
            metrics=painter.fontMetrics()
            text=metrics.elidedText(self.source_hint,Qt.TextElideMode.ElideMiddle,max(0,self.width()-24))
            rect=QRect(9,self.height()-metrics.height()-10,metrics.horizontalAdvance(text)+6,metrics.height()+4)
            painter.fillRect(rect,QColor(250,251,253,210));painter.setPen(QColor('#727987'))
            painter.drawText(rect.adjusted(3,0,-3,0),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)
            painter.restore()
        if self.file_dragging:
            painter.fillRect(self.rect(),QColor(64,86,161,24))
            painter.setPen(QPen(QColor('#4056a1'),2));painter.drawRect(self.rect().adjusted(1,1,-2,-2))
            painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'释放以导入')
