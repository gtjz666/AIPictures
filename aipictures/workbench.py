"""Native desktop presentation: four clear stages, one settings hub, editable plans."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QToolButton,
    QButtonGroup, QDialog, QTabWidget, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy)


class Workbench:
    def __init__(self, w):
        self.window = w
        self.settings = QDialog(w); self.settings.setWindowTitle('创作设置'); self.settings.resize(560, 680)
        layout = QVBoxLayout(self.settings)
        heading = QLabel('创作设置'); heading.setObjectName('dialogHeading'); layout.addWidget(heading)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1); self.sections = {}
        for key, title in [('creation', '生成'), ('image', '画面'), ('sampling', '采样'), ('connection', '连接')]:
            dialog = w.settings_dialogs.get(key)
            if dialog is None:
                continue
            scroll = dialog.findChild(QScrollArea)
            if scroll:
                content = scroll.takeWidget()
                container = QScrollArea(); container.setWidgetResizable(True); container.setWidget(content)
                self.sections[key] = self.tabs.addTab(container, title)
        # A provider retains its own deliberate key entry dialog, never duplicated.
        connection_page = QWidget(); cp = QVBoxLayout(connection_page)
        cp.addWidget(QLabel('可选：使用自己的云端服务商与模型。'))
        api = QPushButton('配置 API 与密钥…'); api.clicked.connect(w.api_controller.open_settings); cp.addWidget(api); cp.addStretch()
        self.tabs.addTab(connection_page, 'API')
        note = QLabel('参数立即生效，用于下一次生成。'); note.setObjectName('muted'); layout.addWidget(note)
        done = QPushButton('完成'); done.clicked.connect(self.settings.close); layout.addWidget(done)
        self.hidden = QWidget(w); self.hidden.hide()
        for button in w.settings_buttons.values():
            button.setParent(self.hidden)
        w.api_controller.button.setParent(self.hidden)
        w.api_controller.summary.setParent(self.hidden)
        side = w.inspector.layout()
        self.settings_button = QPushButton('⚙  创作设置'); self.settings_button.clicked.connect(lambda: self.open_settings('image'))
        side.insertWidget(3, self.settings_button)
        # Large result area, compact composer, optional technical prompt details.
        w.preview.setMinimumSize(360, 240)
        # A loaded pixmap must not enlarge the scrollable workspace to its native
        # size. Otherwise reference previews push the composer below the screen.
        w.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        w.sequence_preview.sheet.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        w.sequence_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        if w.pixmap.isNull():
            w.preview.setText('创作从一个想法开始\n\n添加素材、描述需求，结果会显示在这里')
        w.inspector.setMaximumWidth(240)
        w.inspector.setMinimumWidth(200)
        w.creation_summary.setMinimumHeight(52)
        w.context_label.setObjectName('engineBadge'); w.context_label.setStyleSheet('')
        w.generation_type.hide()
        mode_layout = w.workspace_layout.itemAt(1).layout()
        if mode_layout:
            first = mode_layout.itemAt(0).widget()
            if first:
                first.hide()
            self.group = QButtonGroup(w); self.group.setExclusive(True); self.modes = []
            for i, (title, sub) in enumerate([('单张图片', '角色 · 物件 · 场景'), ('动画制作', '动作参考 · 自由描述')]):
                button = QPushButton(title+'   /   '+sub); button.setCheckable(True); button.setObjectName('modeCard')
                button.setMinimumHeight(42); self.group.addButton(button, i); self.modes.append(button)
                mode_layout.insertWidget(i, button)
            self.group.idClicked.connect(w.generation_type.setCurrentIndex)
            def sync(index):
                self.modes[index].setChecked(True)
            w.generation_type.currentIndexChanged.connect(sync); sync(w.generation_type.currentIndex())
            mode_layout.removeWidget(w.animation_action);mode_layout.removeWidget(w.animation_action_label)
            w.walk_form.insertRow(0,w.animation_action_label,w.animation_action)
            w.animation_action.setCurrentIndex(w.animation_action.findData('custom'))
        header = QWidget(); hv = QVBoxLayout(header); hv.setContentsMargins(0, 0, 0, 4); hv.setSpacing(4)
        top = QHBoxLayout(); title = QLabel('创作工作台'); title.setObjectName('pageHeading'); top.addWidget(title); top.addStretch()
        w.workspace_layout.removeWidget(w.context_label)
        top.addWidget(w.context_label); hv.addLayout(top)
        steps = QLabel('01  选择类型     /     02  素材与需求     /     03  生成     /     04  预览与保存')
        steps.setObjectName('workflowSteps'); hv.addWidget(steps)
        w.workspace_layout.insertWidget(0, header)
        self.prompts = w.positive.parentWidget().parentWidget()
        self.prompts.hide()
        self.details = QToolButton(); self.details.setText('正反提示词'); self.details.setCheckable(True)
        self.details.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details.setArrowType(Qt.ArrowType.RightArrow)
        def toggle(checked):
            self.prompts.setVisible(checked)
            self.details.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.details.toggled.connect(toggle)
        index = w.workspace_layout.indexOf(self.prompts)
        tools = QWidget(); tl = QHBoxLayout(tools); tl.setContentsMargins(0, 0, 0, 0); tl.addWidget(self.details)
        self.timeline = QPushButton('动作时间轴'); self.timeline.clicked.connect(self.show_timeline); self.timeline.hide()
        tl.addWidget(self.timeline); tl.addStretch(); w.workspace_layout.insertWidget(index, tools)
        w.positive.setMinimumHeight(80); w.negative.setMinimumHeight(80)
        w.positive.setMaximumHeight(110); w.negative.setMaximumHeight(110)
        self.plan = None
        w.style_status.hide()
        w.intent_hint.setMaximumHeight(32)
        w.sequence_preview.setMinimumHeight(260)
        # Manual mode still needs its original prompt entry, immediately.
        w.intent_controller.enabled.toggled.connect(lambda enabled: self.details.setChecked(not enabled))
        if not w.intent_controller.enabled.isChecked():
            self.details.setChecked(True)

    def open_settings(self, key):
        if key in self.sections:
            self.tabs.setCurrentIndex(self.sections[key])
        self.settings.show(); self.settings.raise_(); self.settings.activateWindow()

    def show_plan(self, result):
        self.plan = result
        self.timeline.setVisible(bool(result.get('reference_timeline') or result['plan']['timeline']))
        self.details.setChecked(True)

    def show_timeline(self):
        if not self.plan:
            return
        dialog = QDialog(self.window); dialog.setWindowTitle('识别出的动作时间轴'); dialog.resize(720, 440)
        layout = QVBoxLayout(dialog)
        hint = QLabel('时间对应原始动作素材，表中是源角色的逐帧观察。需要调整目标动作时，在需求栏补充后重新整理。')
        hint.setWordWrap(True); layout.addWidget(hint)
        rows = self.plan.get('reference_timeline') or self.plan['plan']['timeline']; table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(['开始 / 秒', '结束 / 秒', '动作描述'])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i, row in enumerate(rows):
            for j, value in enumerate((row['start'], row['end'], row['description'])):
                table.setItem(i, j, QTableWidgetItem(str(value)))
        table.resizeRowsToContents(); layout.addWidget(table)
        done = QPushButton('返回创作'); done.clicked.connect(dialog.close); layout.addWidget(done)
        self.timeline_dialog = dialog; dialog.show()
