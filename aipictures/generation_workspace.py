"""Common, inline generation workspace; references never share prompt editing."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QWidgetAction,QCheckBox


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
    layout.addWidget(b.prompts,3);b.prompts.show()
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
    w.short_video.send_shortcut.setEnabled(False)
    audio.right.hide();audio.prompt_tools.organize.hide();audio.prompt_tools.edit.hide();audio.prompt_tools.shortcut.setEnabled(False)
    layout.insertWidget(1,audio.prompt,2);layout.insertWidget(layout.count()-1,audio.parameters)
    layout.insertWidget(layout.count()-1,audio.note)
    b.prompt_button.hide();b.animation_prompt_button.hide();w.short_video.edit.setText('镜头脚本…')
    def update():
        long=b.category=='long_video';sound=b.category=='audio';walking=w.generation_type.currentData()=='walk'
        b.right_tabs.setTabText(0,'参考');b.right_tabs.setTabText(1,'生成')
        b.image_requirements.hide();b.timeline_region.hide();b.animation_header.hide()
        b.requirement_title.setText('用户需求');b.requirement_title.setVisible(sound);c.input.hide();c.organize.hide()
        b.positive_title.setText('用户需求');w.negative.parentWidget().hide();b.extra_constraints.hide();c.role.hide();c.role_note.hide()
        b.prompts.setVisible(not long and not sound)
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
    w.generation_intent=GenerationIntent(w)
    update()
