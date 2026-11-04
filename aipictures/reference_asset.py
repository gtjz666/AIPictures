"""Compact, keyboard-accessible source selectors above the shared canvas."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QPushButton,QHBoxLayout
from .transparent_preview import TransparentPreview


class ReferenceAsset(QPushButton):
    def __init__(self,title:str):
        super().__init__();self.setCheckable(True);self.setObjectName('referenceAsset')
        self.setFixedSize(54,54);self.setAccessibleName(title)
        row=QHBoxLayout(self);row.setContentsMargins(5,4,5,4)
        self.thumb=TransparentPreview();self.thumb.setFixedSize(40,44)
        row.addWidget(self.thumb);self.thumb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_source(self,poster:str):
        self.thumb.setPixmap(QPixmap(poster).scaled(self.thumb.size(),Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
