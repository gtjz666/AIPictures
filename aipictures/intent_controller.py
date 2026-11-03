"""Chinese chat composer and local intent planning, independent of generation engines."""
import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QLabel,
                              QPushButton, QCheckBox, QComboBox, QMessageBox, QInputDialog)

from .local_intent import analyze, settings
from .storage import write_json


class BriefInput(QPlainTextEdit):
    files_dropped = Signal(list)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if not urls or len(urls) > 1501 or not all(u.isLocalFile() for u in urls):
                event.ignore(); return
            self.files_dropped.emit([Path(u.toLocalFile()) for u in urls])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


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
        self.role = QComboBox(); self.role.addItem('参考图：角色 / 外观', 'appearance')
        self.role.addItem('参考图：画风 / 布局', 'style'); self.role.addItem('参考图：编辑底图', 'edit')
        top.addWidget(self.role); top.addStretch()
        self.organize = QPushButton('整理提示词'); self.organize.clicked.connect(lambda: self.start(False)); top.addWidget(self.organize)
        layout.addLayout(top)
        self.input = BriefInput(); self.input.setMinimumHeight(56); self.input.setMaximumHeight(80)
        self.input.setPlaceholderText('描述想要的结果，可拖入角色图片、动作视频或 GIF。例如：让这个角色模仿视频的动作，保持自己的服装与配色。')
        self.input.files_dropped.connect(self.import_files); layout.addWidget(self.input)
        self.send_shortcut = QShortcut(QKeySequence('Ctrl+Return'), self.input)
        self.send_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.send_shortcut.activated.connect(window.enqueue)
        self.note = QLabel('本地理解素材并整理正反提示词；可直接发送生成，也可先整理后修改。' if self.config else
                           '本地识别模型尚未安装或验收；手动提示词生成仍可使用。')
        self.note.setWordWrap(True); self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setObjectName('muted'); layout.addWidget(self.note)
        self.organize.setEnabled(bool(self.config)); self.enabled.setEnabled(bool(self.config))
        self.role.setEnabled(bool(self.config))
        self.role.currentIndexChanged.connect(self.source_changed)
        # Place before editable prompt pair, below the result area.
        window.workspace_layout.insertWidget(window.workspace_layout.indexOf(window.reference_label)+1, panel)
        self.panel = panel
        window.video_controller.motion.changed.connect(self.source_changed)

    def source_changed(self):
        if self.enabled.isChecked() and not self.running:
            QTimer.singleShot(250, self.auto_organize)

    def auto_organize(self):
        w = self.window
        if (self.enabled.isChecked() and not self.running and not w.preparing and not w.current and not w.pending
                and (w.reference_path or w.video_controller.motion.path)
                and self.applied_context != self.fingerprint(prompts=False)):
            self.start(False)

    def fingerprint(self, *, prompts=True) -> str:
        w = self.window; motion = w.video_controller.motion
        paths = [w.reference_path, motion.path]
        stamps = [(str(p), Path(p).stat().st_size, Path(p).stat().st_mtime_ns) if p and Path(p).exists() else None for p in paths]
        value = [self.input.toPlainText(), w.positive.toPlainText() if prompts else None, w.negative.toPlainText() if prompts else None,
                 w.generation_type.currentData(), self.role.currentData(), stamps, motion.start.value(),
                 w.video_controller.seconds.value(), w.model_family.currentData(), w.custom_graph is not None]
        return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()

    def intercept(self) -> bool:
        if not self.enabled.isChecked():
            return False
        if self.applied == self.fingerprint():
            return False
        if self.applied_context == self.fingerprint(prompts=False):
            return False  # A reviewed prompt edit is authoritative, never silently rewritten.
        self.start(True)
        return True

    def start(self, generate: bool):
        w = self.window
        if self.running or w.preparing:
            self.note.setText('请等待素材准备或识别结束。'); return
        if w.current or w.pending:
            self.note.setText('请等待当前生成队列完成，再识别新需求；识别和生成串行使用显卡。'); return
        if not self.config:
            self.note.setText('本地识别模型尚未完成验收。'); return
        if w.custom_graph is not None:
            self.note.setText('请先将后台预设恢复为自动选择，再使用创作助手。'); return
        manual = w.positive.toPlainText().strip()
        brief = self.input.toPlainText().strip() or (manual if manual != self.generated_positive else '')
        if not brief and (w.reference_path or w.video_controller.motion.path):
            brief = '依据已提供素材制作动画，外观与动作各按其参考用途。' if w.generation_type.currentData()=='walk' else '依据参考图整理主体外观、画风与构图，生成单张图片。'
        if not brief:
            self.note.setText('请描述想生成的内容。'); return
        folder = self.data/'intent'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
        reference = Path(w.reference_path) if w.reference_path else None
        motion = w.video_controller.motion
        motion_path = Path(motion.path) if motion.path and w.generation_type.currentData() == 'walk' else None
        kwargs = dict(selected_kind='animation' if w.generation_type.currentData()=='walk' else 'image',
                      role=self.role.currentData(), start=motion.start.value(), seconds=w.video_controller.seconds.value(),
                      output_seconds=w.video_controller.seconds.value())
        negative = w.negative.toPlainText()
        if negative == self.generated_negative:
            negative = self.original_negative
        initial = self.fingerprint()
        self.applied = self.applied_context = None
        self.running = w.preparing = True; self.cancel_event.clear(); self.current_record = folder
        w.generate_button.setEnabled(False); self.organize.setEnabled(False)
        w.task_display.start(); w.progress.setRange(0, 0)
        self.note.setText('正在识别…'); w.status.setText('正在识别生成需求…')
        def run(emit):
            if w.connected:
                queue = w.client.request('/queue')
                if queue.get('queue_running') or queue.get('queue_pending'):
                    raise ValueError('ComfyUI仍有生成任务，请等队列完成再识别。')
                from .engine_service import release_idle_models
                release_idle_models(w.client)
            return analyze(self.config, brief, negative, reference, motion_path, folder, self.cancel_event, emit, **kwargs)
        def finish(kind, data):
            if kind == 'intent_stage':
                self.note.setText(data['message']); w.status.setText(data['message']); return
            if kind not in ('result', 'error', 'cancelled'):
                return
            unchanged = self.fingerprint() == initial
            self.running = w.preparing = False; self.organize.setEnabled(True)
            w.progress.setRange(0, 100); w.progress.setValue(100 if kind=='result' else 0)
            w.task_display.finish('completed' if kind=='result' else 'cancelled' if self.cancel_event.is_set() else 'failed')
            w.generation_type_changed()
            if kind != 'result':
                self.note.setText('识别已取消，原输入保留。' if self.cancel_event.is_set() else '识别未完成：'+str(data))
                w.status.setText(self.note.text()); w.add_chat('软件', self.note.text())
            elif self.cancel_event.is_set():
                self.note.setText('已取消；识别结果未应用，未提交生成。')
            elif not unchanged:
                self.note.setText('识别期间输入已修改，结果已保存但没有覆盖新输入，请重新整理。')
            elif data['plan']['questions']:
                self.note.setText('需要补充：'+'；'.join(data['plan']['questions']))
                w.add_chat('软件', self.note.text()); w.status.setText('请在需求栏补充后重新发送。')
            else:
                self.original_negative = negative
                self.apply(data)
                self.note.setText(data['plan']['summary']+f" · 识别用时 {data['elapsed_seconds']:.1f} 秒")
                w.add_chat('你', brief, str(reference) if reference else None)
                w.add_chat('软件', self.note.text(), job=str(folder))
                w.status.setText('需求已整理，可修改提示词或直接生成。')
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
        self.cancel_event.set(); self.note.setText('正在取消本地识别，未提交生成。')
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
            self.note.setText('请等待当前素材准备或识别结束，再添加素材。'); return
        try:
            from .motion_guide import EXTENSIONS
            if any(not p.is_file() for p in paths):
                raise ValueError('请拖入图片、视频或GIF文件，不支持整个文件夹。')
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
            self.note.setText(str(exc))

    def animation_mode(self):
        w = self.window
        w.animation_action.setCurrentIndex(w.animation_action.findData('custom'))
        w.generation_type.setCurrentIndex(w.generation_type.findData('walk'))
        w.animation_source.setCurrentIndex(w.animation_source.findData('reference' if w.reference_path else 'text'))
