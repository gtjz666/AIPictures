"""Classic play/pause symbols, with names for keyboard and screen reader users."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton, QStyle


class PlaybackButton(QPushButton):
    def __init__(self, *, playing: bool = False):
        super().__init__()
        self.setFixedWidth(36)
        self.setIconSize(QSize(16, 16))
        self.set_playing(playing)

    def set_playing(self, playing: bool, *, replay: bool = False) -> None:
        symbol = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.setIcon(self.style().standardIcon(symbol))
        self.setAccessibleName('暂停' if playing else '重新播放' if replay else '播放')
