"""Chinese chat composer and local intent planning, independent of generation engines."""
import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel,
                              QPushButton, QCheckBox, QComboBox, QMessageBox, QInputDialog,QLineEdit)

from .storage import write_json


class IntentController:
    def __init__(self, window):
        self.window, self.data = window, window.api_controller.data
        self.config = None  # Manual workflow does not load the retired assistant settings.
        self.running = False
        self.cancel_event = threading.Event()
        self.applied = None
        self.applied_context = None
        self.current_record = None
        self.original_negative = ''
        self.generated_negative = None
        self.generated_positive = None
        self.original_brief = ''
        self.applied_input=None;self.unapplied_result=False;self.last_attempt=None
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.enabled = QCheckBox('本地创作助手'); self.enabled.setChecked(bool(self.config)); top.addWidget(self.enabled)
        self.role = QComboBox();self.role.addItem('人物／外观','appearance');self.role.addItem('风格','style');self.role.addItem('自定义','custom')
        self.role_note=QLineEdit();self.role_note.setMaxLength(2000);self.role_note.setPlaceholderText('说明参考图的用法，例如：只参考构图，替换人物与画风')
        self.role_note.hide();self.role.currentIndexChanged.connect(lambda:self.role_note.setVisible(self.role.currentData()=='custom'))
        self.role_note.textChanged.connect(self.source_changed)
        top.addWidget(self.role); top.addStretch()
        self.organize = QPushButton('整理提示词'); self.organize.clicked.connect(lambda: self.start(False)); top.addWidget(self.organize)
        self.prompt_actions=[self.organize]
        layout.addLayout(top)
        self.input = QPlainTextEdit(); self.input.setMinimumHeight(56)
        self.input.setAcceptDrops(False); self.input.setPlaceholderText('描述你想创作的内容…')
        window.preview.enable_file_drop();window.preview.files_dropped.connect(self.import_files)
        layout.addWidget(self.input,1)
        self.send_shortcut = QShortcut(QKeySequence('Ctrl+Return'), self.input)
        self.send_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.send_shortcut.setEnabled(False)
        self.note = QLabel()
        self.note.setWordWrap(True); self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setObjectName('muted'); layout.addWidget(self.note); self.note.hide()
        self.organize.setEnabled(bool(self.config)); self.enabled.setEnabled(bool(self.config))
        self.role.setEnabled(bool(self.config))
        self.role.currentIndexChanged.connect(self.source_changed)
        # Place before editable prompt pair, below the result area.
        window.workspace_layout.insertWidget(window.workspace_layout.indexOf(window.reference_label)+1, panel)
        self.panel = panel
        window.video_controller.motion.changed.connect(self.source_changed)

    def notify(self, text):
        self.note.setText(text); self.note.setVisible(bool(text))
        if hasattr(self.window,'workbench') and hasattr(self.window.workbench,'prompt_note'):
            b=self.window.workbench;b.prompt_note.setText(text);b.prompt_note.setVisible(bool(text))
            if b.prompts_dialog.isVisible():return
        if text and hasattr(self.window,'workbench'):
            workbench=self.window.workbench;workbench.right_tabs.setCurrentWidget(workbench.animation)
            if hasattr(workbench.reference_items,'ensureWidgetVisible'):
                workbench.reference_items.ensureWidgetVisible(self.note)

    def source_changed(self):
        self.applied = self.applied_context = None
        if hasattr(self.window,'workbench'):
            # Custom actions use output time and survive reference/purpose changes.
            self.window.workbench.plan=None

    def fingerprint(self, *, prompts=True) -> str:
        w = self.window; motion = w.video_controller.motion
        paths = [w.reference_path, motion.path]
        if hasattr(w,'reference_chat'):paths.extend(w.reference_chat.extra.values())
        stamps = [(str(p), Path(p).stat().st_size, Path(p).stat().st_mtime_ns) if p and Path(p).exists() else None for p in paths]
        value = [self.input.toPlainText(), w.positive.toPlainText() if prompts else None, w.negative.toPlainText() if prompts else None,
                 w.generation_type.currentData(), self.role.currentData(),self.role_note.text() if self.role.currentData()=='custom' else '', stamps, motion.start.value(),
                 w.video_controller.seconds.value(), motion.repeat.isChecked(), w.model_family.currentData(), w.custom_graph is not None]
        if prompts and hasattr(w,'workbench'):value.append(w.workbench.timeline.raw_rows())
        return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()

    def intercept(self) -> bool:
        # Analysis is an explicit action. Generation uses the visible prompts.
        return self.running

    def validate_generation(self):
        w=self.window
        if hasattr(w,'short_video') and w.short_video.active():return
        from .motion_prompt import DIRECT_MOTION_GUIDE
        visible=w.positive.toPlainText().strip()
        if w.generation_type.currentData()=='walk' and not w.video_controller.motion.path and DIRECT_MOTION_GUIDE in visible:
            raise ValueError('参考动画已移除，当前仍是旧的参考动作提示词。请按新的文字要求重新生成提示词，或直接修改正向提示词。')
        from .prompt_timeline import remove_owned_timeline
        unchanged=remove_owned_timeline(visible).strip()==(self.generated_positive or '').strip() and w.negative.toPlainText()==self.generated_negative
        if self.generated_positive and unchanged and (self.applied_input is not None and self.input.toPlainText().strip()!=self.applied_input.strip() or self.unapplied_result):
            raise ValueError('创作要求已修改，但当前仍是旧自动稿。请重新生成提示词，或直接修改可见正反提示词后再生成。')

    def start(self, generate: bool, *, frame_only=False, motion_detail=False):
        self.window.status.setText('请直接填写提示词，再点击生成。')

    def apply(self, result, *, manual_timeline=None):
        w = self.window; plan = result['plan']
        if manual_timeline is None:
            manual_timeline=w.workbench.timeline.effective_rows() if hasattr(w,'workbench') and plan['kind']=='animation' else []
        if plan['kind'] == 'animation':
            w.animation_action.setCurrentIndex(w.animation_action.findData('custom'))
            w.generation_type.setCurrentIndex(w.generation_type.findData('walk'))
            w.animation_source.setCurrentIndex(w.animation_source.findData('reference' if w.reference_path else 'text'))
        else:
            w.generation_type.setCurrentIndex(w.generation_type.findData('image'))
        # Automatic route uses tested engines. Explicit manual selections remain authoritative.
        w.positive.setPlainText(plan['positive_prompt']); w.negative.setPlainText(plan['negative_prompt'])
        self.generated_positive = plan['positive_prompt'].strip()
        self.generated_negative = plan['negative_prompt']
        self.applied_input=self.input.toPlainText();self.unapplied_result=False
        from .prompt_language import clear_pair,set_pair
        english=result.get('english') or {}
        if english.get('positive') and english.get('negative'):
            source=self.current_record/'english.json' if self.current_record else ''
            set_pair(self,plan['positive_prompt'],plan['negative_prompt'],
                     english['positive'],english['negative'],source)
        else:clear_pair(self)
        w.generation_type_changed()
        self.applied = self.fingerprint()
        self.applied_context = self.fingerprint(prompts=False)
        if hasattr(w, 'workbench'):
            w.workbench.show_plan(result)
            if manual_timeline:w.workbench.timeline.sync_prompt(manual_timeline)

    def cancel(self) -> bool:
        if not self.running:
            return False
        self.cancel_event.set(); self.window.status.setText('正在取消需求识别')
        return True

    def record(self, folder: Path, params: dict):
        if self.current_record and self.applied_context == self.fingerprint(prompts=False):
            multi=self.current_record/'result.json'
            if multi.is_file():
                result=json.loads(multi.read_text('utf-8'))
                if result.get('policy')=='numbered_references_v1':
                    params['intent_plan_source']=str(multi)
                    write_json(Path(folder)/'intent-plan.json',result)
                    return
            source = self.current_record/'plan.json'
            if source.is_file():
                result = json.loads(source.read_text('utf-8'))
                params['intent_model'] = result['model']
                params['intent_plan_source'] = str(source)
                write_json(Path(folder)/'intent-plan.json', result)

    def import_files(self, paths: list[Path]):
        w = self.window
        if self.running or w.preparing:
            self.notify('请等待素材准备或识别结束。'); return
        try:
            from .motion_guide import EXTENSIONS
            folders=[p for p in paths if p.is_dir()]
            if folders:
                other=[p for p in paths if not p.is_dir()]
                long=getattr(getattr(w,'workbench',None),'category','')=='long_video'
                if len(folders)!=1 or len(other)>(4 if long else 1) or any(not p.is_file() or p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.bmp') for p in other):
                    raise ValueError('每次可拖入一个PNG动画帧文件夹，并可附带一张角色或风格图。')
                if long and other:
                    if len(other)+len(w.reference_chat.references())>4:raise ValueError('最多4张参考图，请先移除不需要的图片。')
                    for path in other:w.reference_chat.validate(path)
                    w.reference_chat.import_images(other)
                elif other:w.set_reference(str(other[0]))
                self.animation_mode();w.video_controller.motion.set_folder(folders[0]);self.source_changed();return
            if any(not p.is_file() for p in paths):raise ValueError('请拖入有效的图片、视频、GIF或PNG动画帧文件夹。')
            images = [p for p in paths if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp')]
            motions = [p for p in paths if p.suffix.lower() in EXTENSIONS]
            if getattr(getattr(w,'workbench',None),'category','')=='long_video' and images:
                if len(motions)>1 or len(images)+len(motions)!=len(paths):raise ValueError('一次可导入最多4张参考图及一个参考视频。')
                if len(images)+len(w.reference_chat.references())>4:raise ValueError('最多4张参考图，请先移除不需要的图片。')
                for path in images:w.reference_chat.validate(path)
                w.reference_chat.import_images(images)
                if motions:self.animation_mode();w.video_controller.motion.set_file(motions[0])
                self.source_changed();return
            if images and not motions and len(images)==len(paths) and w.generation_type.currentData()!='walk' and hasattr(w,'reference_chat'):
                w.reference_chat.import_images(images);return
            if len(images)+len(motions) != len(paths) or len(motions)>1:
                raise ValueError('每次可添加一张外观图和一个动作视频/GIF；多张PNG可作为动作帧序列。')
            if len(images)>1:
                if motions or any(p.suffix.lower()!='.png' for p in images):
                    raise ValueError('多张图片请分别明确用途；目前生成支持一张外观图＋一组动作帧。')
                answer = QMessageBox.question(w, '导入图片', '这些PNG是否是按文件名顺序播放的动作帧？')
                if answer != QMessageBox.StandardButton.Yes:
                    return
                fps, ok = QInputDialog.getInt(w, '动作帧率', '每秒播放帧数（FPS）', 24, 1, 120)
                if ok:
                    self.animation_mode(); w.video_controller.motion.set_frames(images, fps)
                return
            if images:
                w.set_reference(str(images[0]))
            if motions:
                self.animation_mode(); w.video_controller.motion.set_file(motions[0])
            self.applied = None
            self.source_changed()
        except (OSError, ValueError) as exc:
            self.notify(str(exc))

    def animation_mode(self):
        w = self.window
        w.animation_action.setCurrentIndex(w.animation_action.findData('custom'))
        w.generation_type.setCurrentIndex(w.generation_type.findData('walk'))
        w.animation_source.setCurrentIndex(w.animation_source.findData('reference' if w.reference_path else 'text'))
