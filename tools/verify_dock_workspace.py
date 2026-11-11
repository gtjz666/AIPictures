"""Real Qt file drops, explicit analysis, fixed tabs and size persistence. No GPU."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDropEvent,QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QDockWidget

from aipictures.app import Window,create_application
from aipictures.storage import write_json


def wait_until(predicate,seconds=20):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        QTest.qWait(20);time.sleep(.005)  # Let Python worker threads run between Qt waits.
    assert predicate(),'Qt operation did not finish.'


def drop(app,widget,paths):
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    enter=QDragEnterEvent(QPoint(10,10),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(widget,enter);assert enter.isAccepted()
    event=QDropEvent(QPointF(10,10),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(widget,event);assert event.isAccepted()


def main():
    from tools.verify_game_workspace import verify
    verify('layout')


if __name__=='__main__':main()
