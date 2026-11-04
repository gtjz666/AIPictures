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

from .local_intent import analyze, settings
from .storage import write_json


class IntentController:
    def __init__(self, window):
        self.window, self.data = window, window.api_controller.data
        self.config = settings(self.data)
        self.running = False
        self.cancel_event = threading.Event()
        self.applied = None
        self.applied_context = None
        self.current_record = None
        self.original_negative = ''
        self.generated_negative = None
        self.generated_positive = None
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.enabled = QCheckBox('本地创作助手'); self.enabled.setChecked(bool(self.config)); top.addWidget(self.enabled)
        self.role = QComboBox();self.role.addItem('人物／外观','appearance');self.role.addItem('风格','style');self.role.addItem('自定义','custom')
        self.role_note=QLineEdit();self.role_note.setMaxLength(2000);self.role_note.setPlaceholderText('说明参考图的用法，例如：只参考构图，替换人物与画风')
        self.role_note.hide();self.role.currentIndexChanged.connect(lambda:self.role_note.setVisible(self.role.currentData()=='custom'))
        self.role_note.textChanged.connect(self.source_changed)
        top.addWidget(self.role); top.addStretch()
        self.organize = QPushButton('整理提示词'); self.organize.clicked.connect(lambda: self.start(False)); top.addWidget(self.organize)
        layout.addLayout(top)
        self.input = QPlainTextEdit(); self.input.setMinimumHeight(56)
        self.input.setAcceptDrops(False); self.input.setPlaceholderText('描述你想创作的内容…')
        window.preview.enable_file_drop();window.preview.files_dropped.connect(self.import_files)
        layout.addWidget(self.input,1)
        self.send_shortcut = QShortcut(QKeySequence('Ctrl+Return'), self.input)
        self.send_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.send_shortcut.activated.connect(window.enqueue)
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
        if text and hasattr(self.window,'workbench'):
            self.window.workbench.right_tabs.setCurrentIndex(0)

    def source_changed(self):
        self.applied = self.applied_context = None
        if hasattr(self.window,'workbench'):
            workbench=self.window.workbench;workbench.plan=None;workbench.timeline.clear_plan();workbench.frame_review.clear()

    def fingerprint(self, *, prompts=True) -> str:
        w = self.window; motion = w.video_controller.motion
        paths = [w.reference_path, motion.path]
        stamps = [(str(p), Path(p).stat().st_size, Path(p).stat().st_mtime_ns) if p and Path(p).exists() else None for p in paths]
        value = [self.input.toPlainText(), w.positive.toPlainText() if prompts else None, w.negative.toPlainText() if prompts else None,
                 w.generation_type.currentData(), self.role.currentData(),self.role_note.text() if self.role.currentData()=='custom' else '', stamps, motion.start.value(),
                 w.video_controller.seconds.value(), motion.repeat.isChecked(), w.model_family.currentData(), w.custom_graph is not None]
        return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()

    def intercept(self) -> bool:
        # Analysis is an explicit action. Generation uses the visible prompts.
        return self.running

    def start(self, generate: bool, *, frame_only=False):
        w = self.window
        if self.running or w.preparing:
            self.notify('请等待素材准备或识别结束。'); return
        if w.current or w.pending:
            self.notify('请等待当前任务完成。'); return
        if not self.config:
            self.notify('本地识别模型不可用。'); return
        if w.custom_graph is not None:
            self.notify('请先将后台预设恢复为自动选择。'); return
        manual = w.positive.toPlainText().strip()
        brief = manual or self.input.toPlainText().strip()
        if not brief and (w.reference_path or w.video_controller.motion.path):
            brief = '依据已提供素材制作动画，外观与动作各按其参考用途。' if w.generation_type.currentData()=='walk' else '依据参考图整理主体外观、画风与构图，生成单张图片。'
        if not brief and frame_only:brief='分析当前参考帧的可见内容。'
        if not brief:
            self.notify('请描述想生成的内容。'); return
        folder = self.data/'intent'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
        reference = Path(w.reference_path) if w.reference_path else None
        reference_usage=self.role_note.text().strip() if self.role.currentData()=='custom' else ''
        if reference and not frame_only and self.role.currentData()=='custom' and not reference_usage:
            self.notify('请填写参考图的自定义用法，例如哪些部分保留、哪些部分改变。');return
        motion = w.video_controller.motion
        motion_path = Path(motion.path) if motion.path and w.generation_type.currentData() == 'walk' else None
        selected_frame=round(motion.start.value()*motion.meta['frame_fps']) if frame_only and motion.is_frames() else None
        if frame_only and selected_frame is None:
            self.notify('请先拖入PNG动画帧素材。');return
        kwargs = dict(selected_kind='animation' if w.generation_type.currentData()=='walk' else 'image',
                      role=self.role.currentData(), start=motion.start.value(), seconds=w.video_controller.seconds.value(),
                      output_seconds=w.video_controller.seconds.value(),reference_usage=reference_usage)
        if motion_path and motion.repeat.isChecked() and not frame_only:
            # A cycle wraps to source time zero, so observe the complete source once.
            kwargs.update(start=0.,seconds=motion.meta['duration'])
        negative = w.negative.toPlainText()
        if negative == self.generated_negative:
            negative = self.original_negative
        initial = self.fingerprint()
        if not frame_only:self.applied = self.applied_context = None;self.current_record = folder
        self.running = w.preparing = True; self.cancel_event.clear()
        w.generate_button.setEnabled(False); self.organize.setEnabled(False)
        if hasattr(w,'workbench'):w.workbench.analyze_motion.setEnabled(False)
        w.task_display.start(); w.progress.setRange(0, 0)
        self.notify(''); w.status.setText('正在识别生成需求…')
        def run(emit):
            if w.connected:
                queue = w.client.request('/queue')
                if queue.get('queue_running') or queue.get('queue_pending'):
                    raise ValueError('ComfyUI仍有生成任务，请等队列完成再识别。')
                from .engine_service import release_idle_models
                release_idle_models(w.client)
            if frame_only:
                from .local_intent import analyze_frame
                return analyze_frame(self.config,motion_path,selected_frame,folder,self.cancel_event,emit)
            return analyze(self.config, brief, negative, reference, motion_path, folder, self.cancel_event, emit, **kwargs)
        def finish(kind, data):
            if kind == 'intent_stage':
                w.status.setText(data['message']); return
            if kind not in ('result', 'error', 'cancelled'):
                return
            unchanged = motion.path==motion_path if frame_only else self.fingerprint() == initial
            self.running = w.preparing = False; self.organize.setEnabled(True)
            if hasattr(w,'workbench'):w.workbench.analyze_motion.setEnabled(bool(self.config))
            w.progress.setRange(0, 100); w.progress.setValue(100 if kind=='result' else 0)
            w.task_display.finish('completed' if kind=='result' else 'cancelled' if self.cancel_event.is_set() else 'failed')
            w.generation_type_changed()
            if kind != 'result':
                self.notify('识别已取消，原输入保留。' if self.cancel_event.is_set() else '识别未完成：'+str(data))
                w.status.setText(self.note.text()); w.add_chat('软件', self.note.text())
            elif self.cancel_event.is_set():
                self.notify('已取消；识别结果未应用。')
            elif not unchanged:
                self.notify('输入已修改，请重新整理。')
            elif frame_only:
                w.workbench.show_frame_analysis(data);w.status.setText('参考帧分析完成')
            elif data['plan']['questions']:
                self.notify('需要补充：'+'；'.join(data['plan']['questions']))
                w.add_chat('软件', self.note.text()); w.status.setText('请在需求栏补充后重新发送。')
            else:
                self.original_negative = negative
                self.apply(data)
                self.notify('')
                w.add_chat('你', brief, str(reference) if reference else None)
                w.add_chat('软件', data['plan']['summary'], job=str(folder))
                w.status.setText('需求识别完成')
                if generate:
                    QTimer.singleShot(0, w.enqueue)
            QTimer.singleShot(0, w.start_next)
        w.launch(run, finish)

    def apply(self, result):
        w = self.window; plan = result['plan']
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
        w.generation_type_changed()
        self.applied = self.fingerprint()
        self.applied_context = self.fingerprint(prompts=False)
        if hasattr(w, 'workbench'):
            w.workbench.show_plan(result)

    def cancel(self) -> bool:
        if not self.running:
            return False
        self.cancel_event.set(); self.window.status.setText('正在取消需求识别')
        return True

    def record(self, folder: Path, params: dict):
        if self.current_record and self.applied_context == self.fingerprint(prompts=False):
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
                if len(folders)!=1 or len(other)>1 or any(not p.is_file() or p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.bmp') for p in other):
                    raise ValueError('每次可拖入一个PNG动画帧文件夹，并可附带一张角色或风格图。')
                if other:w.set_reference(str(other[0]))
                self.animation_mode();w.video_controller.motion.set_folder(folders[0]);self.source_changed();return
            if any(not p.is_file() for p in paths):raise ValueError('请拖入有效的图片、视频、GIF或PNG动画帧文件夹。')
            images = [p for p in paths if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp')]
            motions = [p for p in paths if p.suffix.lower() in EXTENSIONS]
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
