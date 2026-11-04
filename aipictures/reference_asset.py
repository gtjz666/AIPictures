"""Compact, keyboard-accessible source selectors above the shared canvas."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QPushButton,QHBoxLayout,QToolButton,QLabel,QSizePolicy
from .transparent_preview import TransparentPreview


class ReferenceAsset(QPushButton):
    closed=Signal()
    def __init__(self,title:str):
        super().__init__();self.setCheckable(True);self.setObjectName('referenceAsset')
        self.setFixedSize(54,54);self.setAccessibleName(title)
        row=QHBoxLayout(self);row.setContentsMargins(5,4,5,4)
        self.thumb=TransparentPreview();self.thumb.setFixedSize(40,44)
        row.addWidget(self.thumb);self.thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button=QToolButton(self);self.close_button.setObjectName('assetClose');self.close_button.setText('×')
        self.close_button.setFixedSize(18,18);self.close_button.move(self.width()-19,1)
        self.close_button.setAccessibleName('移除'+title);self.close_button.clicked.connect(lambda:self.closed.emit())
        self.close_button.hide()

    def enterEvent(self,event):
        super().enterEvent(event);self.close_button.show();self.close_button.raise_()

    def leaveEvent(self,event):
        super().leaveEvent(event);self.close_button.hide()

    def set_source(self,poster:str):
        self.thumb.setPixmap(QPixmap(poster).scaled(self.thumb.size(),Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))


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
