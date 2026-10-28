"""A quiet light desktop theme: neutral sidebar, white canvas and black primary action."""
from PySide6.QtGui import QColor,QFont,QPalette


LIGHT_STYLE = '''
QWidget { background:#ffffff; color:#242528; font-family:"Microsoft YaHei UI"; font-size:13px; }
QWidget#sidebar { background:#f7f7f8; border:1px solid #ececee; border-radius:12px; }
QWidget#sidebar QLabel { background:transparent; }
QWidget#sidebar QPushButton { background:transparent; border:0; border-radius:8px; padding:12px 10px; text-align:left; }
QWidget#sidebar QPushButton:hover { background:#eaeaec; }
QDialog { background:#ffffff; }
QDockWidget { border-top:1px solid #e5e7eb; }
QDockWidget::title { padding:7px; background:#f7f7f8; }
QLabel#muted { color:#72757c; background:transparent; }
QScrollArea { border:0; background:transparent; }
QLineEdit,QTextEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox,QListWidget {
    background:#ffffff; color:#242528; border:1px solid #dedfe3; border-radius:8px; padding:8px;
    selection-background-color:#e4e7ec; selection-color:#17181a;
}
QTextEdit:focus,QPlainTextEdit:focus,QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus { border:1px solid #969ba5; }
QComboBox:hover,QSpinBox:hover,QDoubleSpinBox:hover { border:1px solid #b8bcc4; }
QComboBox::drop-down { border:0; width:22px; }
QComboBox QAbstractItemView { background:#ffffff; color:#242528; selection-background-color:#eceef1; selection-color:#17181a; }
QTextBrowser { background:#fafafa; border:1px solid #ebebed; border-radius:12px; padding:8px; }
QPushButton { background:#ffffff; color:#292a2d; border:1px solid #dedfe3; border-radius:8px; padding:9px 12px; }
QPushButton:hover { background:#f3f4f6; border-color:#c7c9ce; }
QPushButton:pressed { background:#e8eaed; }
QPushButton:disabled { color:#a6a9b0; background:#f6f7f8; border-color:#ebedf0; }
QPushButton#primary { background:#202123; color:#ffffff; border:1px solid #202123; font-weight:600; border-radius:10px; }
QPushButton#primary:hover { background:#3c3e42; border-color:#3c3e42; }
QPushButton#primary:disabled { background:#bfc1c5; color:#f4f4f4; border-color:#bfc1c5; }
QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled { background:#f7f8fa; color:#9ea3ab; }
QTabWidget::pane { border:1px solid #e5e7eb; border-radius:10px; background:#ffffff; }
QTabBar::tab { background:#ffffff; color:#757982; padding:9px 14px; border:0; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#202123; border-bottom:2px solid #202123; }
QTabBar::tab:hover { background:#f5f6f8; }
QTabBar::tab:disabled { color:#b5b8be; }
QListWidget::item { padding:7px; border-radius:6px; }
QListWidget::item:selected { background:#e9ebef; color:#17181a; }
QProgressBar { border:0; background:#eff0f2; color:#41454c; border-radius:5px; text-align:center; max-height:14px; }
QProgressBar::chunk { background:#b6bbc4; border-radius:5px; }
QSlider::groove:horizontal { background:#e7e9ed; height:4px; border-radius:2px; }
QSlider::handle:horizontal { background:#36393f; width:12px; margin:-4px 0; border-radius:6px; }
QScrollBar:vertical { background:transparent; width:9px; margin:0; }
QScrollBar::handle:vertical { background:#d3d6dc; border-radius:4px; min-height:24px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QSplitter::handle { background:#ffffff; width:3px; }
QToolTip { background:#ffffff; color:#40434a; border:1px solid #dedfe3; border-radius:6px; padding:8px; font-size:12px; }
'''


def apply_light_theme(app):
    app.setStyle('Fusion'); app.setFont(QFont('Microsoft YaHei UI',10))
    palette=QPalette()
    for role,color in ((QPalette.ColorRole.Window,'#ffffff'),(QPalette.ColorRole.Base,'#ffffff'),
        (QPalette.ColorRole.AlternateBase,'#f7f7f8'),(QPalette.ColorRole.WindowText,'#242528'),
        (QPalette.ColorRole.Text,'#242528'),(QPalette.ColorRole.Button,'#ffffff'),
        (QPalette.ColorRole.ButtonText,'#242528'),(QPalette.ColorRole.PlaceholderText,'#9599a1'),
        (QPalette.ColorRole.Highlight,'#e4e7ec'),(QPalette.ColorRole.HighlightedText,'#17181a'),
        (QPalette.ColorRole.ToolTipBase,'#ffffff'),(QPalette.ColorRole.ToolTipText,'#242528')):
        palette.setColor(role,QColor(color))
    app.setPalette(palette); app.setStyleSheet(LIGHT_STYLE)
