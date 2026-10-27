from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QLabel


class TransparentPreview(QLabel):
    """Checkerboard belongs to the viewer; exported pixels stay transparent."""
    def paintEvent(self,event):
        painter=QPainter(self); tile=16
        for y in range(0,self.height(),tile):
            for x in range(0,self.width(),tile):
                painter.fillRect(x,y,tile,tile,QColor('#242b38' if (x//tile+y//tile)%2 else '#303948'))
        pixmap=self.pixmap()
        if pixmap and not pixmap.isNull():
            painter.drawPixmap((self.width()-pixmap.width())//2,(self.height()-pixmap.height())//2,pixmap)
        else:
            painter.setPen(QColor('#aebbd0')); painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,self.text())
