"""Common, inline generation workspace; references never share prompt editing."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QWidgetAction,QCheckBox,QPlainTextEdit,QPushButton,QComboBox


def install(b):
    w=b.window;c=w.intent_controller;motion=w.video_controller.motion
    # Keep the old table object for reading historical files, outside normal UX.
    b.timeline_region.setParent(b.hidden);b.timeline_region.hide();b.reference_skinning=True
    b.image_requirements.setParent(b.hidden);b.image_requirements.hide()
    b.motion_reference_page.setParent(b.reference_splitter);b.reference_splitter.addWidget(b.motion_reference_page)
    b.motion_reference_page.setMaximumHeight(16777215);b.motion_reference_page.show()
    content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(8,6,8,6);layout.setSpacing(7)
    b.requirement_title=QLabel('创作要求');layout.addWidget(b.requirement_title)
    c.input.setMinimumHeight(75);c.input.setMaximumHeight(170);layout.addWidget(c.input,1)
    c.input.setPlaceholderText('描述需要保留和修改的内容，例如：保留图1的主体、外形与姿势，仅改为图2的美术风格。')
    c.organize.setText('生成专业提示词');c.organize.setToolTip('只专业化文字要求，不分析参考图片；图号会原样传给生成引擎。');layout.addWidget(c.organize)
    w.short_video.setParent(content);layout.addWidget(w.short_video)
    b.prompts_dialog.layout().removeWidget(b.prompt_page)
    b.prompt_page.setParent(b.hidden);b.prompt_page.hide()
    layout.addWidget(b.prompts);b.prompts.show();b.prompts.setMaximumHeight(190)
    w.positive.setMaximumHeight(140)
    b.prepare_prompt=QPushButton('生成提示词');b.prepare_prompt.setObjectName('promptGenerate')
    b.prepare_prompt.clicked.connect(lambda:w.generation_intent.prepare());layout.addWidget(b.prepare_prompt)
    layout.addWidget(QLabel('提示词（可修改）'))
    b.prompt_output=QPlainTextEdit();b.prompt_output.setMinimumHeight(150)
    b.prompt_output.setPlaceholderText('点击“生成提示词”后在这里查看和修改；确认后再点击下方生成按钮。')
    layout.addWidget(b.prompt_output,3)
    b.structure_row=QWidget();structure_layout=QHBoxLayout(b.structure_row);structure_layout.setContentsMargins(0,0,0,0)
    structure_layout.addWidget(QLabel('姿势／结构来源'));b.structure_choice=QComboBox()
    b.structure_choice.addItem('自动按需求选择','auto')
    for n in range(1,5):b.structure_choice.addItem('图'+str(n),str(n))
    b.structure_choice.addItem('关闭结构约束','off');structure_layout.addWidget(b.structure_choice,1)
    b.structure_choice.setToolTip('选择提供姿势与构图的图片；主体外观来自另一张图片。适用于人形与非人形素材。')
    layout.addWidget(b.structure_row)
    b.subject_only=QCheckBox('仅借用主体外观，排除原场景干扰');b.subject_only.setChecked(True)
    b.subject_only.setToolTip('姿势替换时只提取主体作为外观参考，原图保持不变。需要保留原场景时可取消。')
    layout.addWidget(b.subject_only)
    b.structure_note=QLabel();b.structure_note.setWordWrap(True);b.structure_note.setObjectName('muted');layout.addWidget(b.structure_note)
    def structure_note():
        from .structure_control import resolve
        try:value=resolve(w.positive.toPlainText(),w.reference_chat.references(),b.structure_choice.currentData())
        except ValueError as exc:b.structure_note.setText(str(exc));b.subject_only.setEnabled(False);return
        b.subject_only.setEnabled(bool(value and value['structure']!=value['identity']))
        b.structure_note.setText(f'图{value["structure"]}提供姿势与构图；图{value["identity"]}提供主体外观。提示词只补充修改。' if value else '需要复刻姿势时，可指定结构来源；不会自动套用人体骨架。')
    b.structure_choice.currentIndexChanged.connect(structure_note);w.positive.textChanged.connect(structure_note)
    b.extra_constraints=QCheckBox('补充限制（可选）');layout.addWidget(b.extra_constraints)
    b.extra_constraints.toggled.connect(lambda checked:w.negative.parentWidget().setVisible(checked))
    layout.addWidget(c.note);c.note.setParent(content)
    parameters=QWidget();b.generation_parameters=parameters;rows=QVBoxLayout(parameters);rows.setContentsMargins(0,0,0,0)
    rows.addWidget(b.motion_selection);rows.addWidget(motion.frame_rate_row)
    duration=QHBoxLayout();b.duration_title=QLabel('时长 / 秒');duration.addWidget(b.duration_title);duration.addWidget(w.video_controller.seconds,1);rows.addLayout(duration)
    b.duration_note=QLabel();b.duration_note.setWordWrap(True);b.duration_note.setObjectName('muted');rows.addWidget(b.duration_note)
    layout.addWidget(parameters)
    b.generation_actions=QWidget();actions=QHBoxLayout(b.generation_actions);actions.setContentsMargins(0,6,0,0)
    bar=w.findChild(__import__('PySide6.QtWidgets',fromlist=['QToolBar']).QToolBar,'creationToolbar')
    for action in list(bar.actions()):
        if isinstance(action,QWidgetAction) and action.defaultWidget() in (w.generate_button,w.cancel_button):bar.removeAction(action)
    actions.addWidget(w.cancel_button);actions.addWidget(w.generate_button,1);w.cancel_button.show();w.generate_button.show()
    layout.addWidget(b.generation_actions)
    b.generation_layout=layout;b.generation_page=b.scroll_page(content)
    b.right_tabs.removeTab(1);b.right_tabs.addTab(b.generation_page,'生成')
    b.animation=b.generation_page;b.tool_pages={'reference':b.reference_items,'generation':b.generation_page}
    b.right_tabs.setTabText(0,'参考')
    audio=w.audio_controller
    audio.prompt.setMinimumHeight(80);audio.prompt.setMaximumHeight(140)
    w.short_video.send_shortcut.setEnabled(False)
    audio.right.hide();audio.prompt_tools.organize.hide();audio.prompt_tools.edit.hide();audio.prompt_tools.shortcut.setEnabled(False)
    layout.insertWidget(1,audio.prompt);layout.insertWidget(layout.count()-1,audio.parameters)
    layout.insertWidget(layout.count()-1,audio.note)
    b.prompt_button.hide();b.animation_prompt_button.hide();w.short_video.edit.setText('镜头脚本…')
    def update():
        long=b.category=='long_video';sound=b.category=='audio';walking=w.generation_type.currentData()=='walk'
        b.right_tabs.setTabText(0,'参考');b.right_tabs.setTabText(1,'生成')
        b.image_requirements.hide();b.timeline_region.hide();b.animation_header.hide()
        b.requirement_title.setText('用户需求');b.requirement_title.setVisible(sound);c.input.hide();c.organize.hide()
        b.positive_title.setText('用户需求');w.negative.parentWidget().hide();b.extra_constraints.hide();c.role.hide();c.role_note.hide()
        b.prompts.setVisible(not long and not sound)
        b.structure_row.setVisible(not walking and not sound and not long)
        b.subject_only.setVisible(not walking and not sound and not long)
        b.structure_note.setVisible(not walking and not sound and not long);structure_note()
        b.prepare_prompt.setEnabled(bool(c.config) and not w.preparing)
        if not walking and not sound:w.generate_button.setText('生成图片')
        if hasattr(w,'generation_intent'):w.generation_intent.sync_mode()
        audio.prompt.setVisible(sound);audio.parameters.setVisible(sound);audio.note.setVisible(sound)
        b.right_tabs.setTabEnabled(0,not sound)
        if sound:b.right_tabs.setCurrentWidget(b.generation_page)
        w.short_video.organize.hide();w.short_video.edit.hide()
        w.short_video.music.hide();w.short_video.import_music.hide();w.short_video.audio_note.hide()
        w.short_video.setVisible(long and not sound);b.generation_parameters.setVisible(walking and not sound)
        b.motion_selection.setVisible(walking and bool(motion.path));b.duration_title.setText('本段时长 / 秒' if long else '时长 / 秒')
        layout.addWidget(b.generation_actions)
        b.duration_note.setVisible(bool(motion.path) and walking)
        if motion.path:
            exact=abs(w.video_controller.seconds.value()-motion.meta['duration'])<=.002
            b.duration_note.setText('当前时长为参考动画时长。修改会改变动作对应关系，可能降低生成准确度。' if exact else
                '已修改参考动画时长，动作对应关系会变化，生成准确度可能降低。')
    b.update_generation_page=update
    w.generation_type.currentIndexChanged.connect(update);w.video_controller.seconds.valueChanged.connect(update);motion.changed.connect(update)
    from .generation_intent import GenerationIntent
    w.generation_intent=GenerationIntent(w,b)
    update()
