"""Reference previews with an accessible hover-to-remove control."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QPushButton,QHBoxLayout,QToolButton,QLabel,QSizePolicy
from .transparent_preview import TransparentPreview


class ReferenceAsset(QPushButton):
    closed=Signal()
    def __init__(self,title:str,*,large:bool=False):
        super().__init__();self.setCheckable(True);self.setObjectName('referenceAsset')
        self.large=large;self._pixmap=QPixmap();self.setAccessibleName(title)
        if large:
            self.setMinimumSize(160,100);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        else:self.setFixedSize(54,54)
        row=QHBoxLayout(self);row.setContentsMargins(5,4,5,4)
        self.thumb=TransparentPreview();self.thumb.setText(title)
        if large:self.thumb.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        else:self.thumb.setFixedSize(40,44)
        row.addWidget(self.thumb);self.thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.thumb.resized.connect(self.fit_preview)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button=QToolButton(self);self.close_button.setObjectName('assetClose');self.close_button.setText('×')
        self.close_button.setFixedSize(18,18);self.close_button.move(self.width()-19,1)
        self.close_button.setAccessibleName('移除'+title);self.close_button.clicked.connect(lambda:self.closed.emit())
        self.close_button.hide()

    def enterEvent(self,event):
        super().enterEvent(event);self.close_button.setVisible(not self._pixmap.isNull());self.close_button.raise_()

    def leaveEvent(self,event):
        super().leaveEvent(event);self.close_button.hide()

    def set_source(self,poster:str):
        self._pixmap=QPixmap(poster) if poster else QPixmap();self.fit_preview()
        self.close_button.setVisible(not self._pixmap.isNull() and self.underMouse())

    def fit_preview(self):
        if self._pixmap.isNull():self.thumb.clear();self.thumb.setText(self.accessibleName());return
        ratio=self.thumb.devicePixelRatioF()
        pixmap=self._pixmap.scaled(self.thumb.size()*ratio,Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio);self.thumb.setPixmap(pixmap)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'close_button'):self.close_button.move(self.width()-19,1)

    def enable_file_drop(self,callback):
        self.thumb.enable_file_drop();self.thumb.files_dropped.connect(callback);self.setAcceptDrops(True)

    def dragEnterEvent(self,event):self.thumb.dragEnterEvent(event)
    def dragMoveEvent(self,event):self.thumb.dragMoveEvent(event)
    def dragLeaveEvent(self,event):self.thumb.dragLeaveEvent(event)
    def dropEvent(self,event):self.thumb.dropEvent(event)


class SourceCaption(QLabel):
    """Source name in the action row; never painted over the source image."""
    def __init__(self):
        super().__init__();self.full_text='';self.setObjectName('sourceCaption')
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)

    def set_hint(self,text:str):
        if text==self.full_text:return
        self.full_text=text;self.setAccessibleDescription(text);self.fit_text()

    def fit_text(self):
        self.setText(self.fontMetrics().elidedText(self.full_text,Qt.TextElideMode.ElideMiddle,max(0,self.width())))

    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_text()
