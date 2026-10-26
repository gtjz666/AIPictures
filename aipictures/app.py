import json
import secrets
import shutil
import sys
import threading
import html
from uuid import uuid4
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices, QImageReader
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFormLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QProgressBar, QListWidget, QListWidgetItem, QSplitter, QFileDialog, QMessageBox, QScrollArea, QTabWidget, QTextBrowser)
from .engine import ComfyClient, Cancelled
from .workflow import ImageRequest, build_workflow
from .storage import DATA, write_json, new_job
from .workflow_editor import WorkflowEditor
from .prompt_binding import bind_request, bindings, check_models
from .workflow_library import list_workflows, workflow_path, digest


class Worker(QThread):
    event = Signal(str, object)
    def __init__(self, action):
        super().__init__()
        self.action = action
    def run(self):
        try:
            self.event.emit('result', self.action(self.event.emit))
        except Cancelled as exc:
            self.event.emit('cancelled', str(exc))
        except Exception as exc:
            self.event.emit('error', str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AIPictures · 本地创作工作室')
        self.resize(1440, 940)
        self.workers = []
        self.pending = []
        self.current = None
        self.pixmap = QPixmap()
        self.output = None
        self.custom_graph = None
        self.active_title = '自动选择'
        self.reference_path = None
        self.preparing = False
        self.prepare_cancel = threading.Event()
        self.last_chat_graph = None
        self.editor_needs_sync = False
        self.chat_messages = []
        self.template_restored = False
        self.connected = False
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        header.addWidget(QLabel('AIPictures  /  本地 AI 创作'))
        self.url = QLineEdit('http://127.0.0.1:8188'); self.url.setMaximumWidth(300)
        config = DATA / 'settings.json'
        if config.exists():
            try: self.url.setText(json.loads(config.read_text('utf-8'))['url'])
            except (ValueError, KeyError): pass
        header.addStretch(); header.addWidget(self.url)
        self.connect_button = QPushButton('连接 / 刷新模型'); self.connect_button.clicked.connect(self.connect_engine)
        header.addWidget(self.connect_button); layout.addLayout(header)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        image_page = QWidget(); image_layout = QVBoxLayout(image_page); image_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(); image_layout.addWidget(splitter, 1)
        self.tabs.addTab(image_page, '对话创作')
        left = QWidget(); lv = QVBoxLayout(left)
        lv.addWidget(QLabel('创作空间'))
        edit = QPushButton('高级：工作流编辑'); edit.clicked.connect(lambda: self.tabs.setCurrentIndex(1)); lv.addWidget(edit)
        lv.addWidget(QLabel('数据集 / 训练 / 骨骼 / 动画 / 视频\n后续阶段，尚未实现'))
        lv.addWidget(QLabel('本地生成记录（双击预览）'))
        self.gallery = QListWidget(); self.gallery.itemDoubleClicked.connect(self.open_history)
        lv.addWidget(self.gallery, 1)
        open_data = QPushButton('打开素材与结果目录'); open_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA))))
        lv.addWidget(open_data)
        self.gpu = QLabel('显存：等待连接'); self.gpu.setWordWrap(True); lv.addWidget(self.gpu)
        splitter.addWidget(left)
        center = QWidget(); cv = QVBoxLayout(center)
        mode_bar = QHBoxLayout(); mode_bar.addWidget(QLabel('生成方式'))
        self.workflow_selector = QComboBox(); self.workflow_selector.addItem('自动选择 · 文字生成 / 参考图生成', None)
        for entry in list_workflows(): self.workflow_selector.addItem(entry['title'], entry)
        self.workflow_selector.currentIndexChanged.connect(self.select_chat_workflow)
        mode_bar.addWidget(self.workflow_selector, 1); cv.addLayout(mode_bar)
        self.preview = QLabel('描述你想创作的画面，或添加一张参考图'); self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(360, 240); self.preview.setStyleSheet('background:#10141e;border:1px solid #31394c;border-radius:12px;color:#8d9bb4')
        cv.addWidget(self.preview, 1)
        self.caption = QLabel('生成结果自动保存 PNG、参数和完整工作流'); self.caption.setWordWrap(True); cv.addWidget(self.caption)
        save_bar = QHBoxLayout()
        save = QPushButton('将当前图片另存为…'); save.clicked.connect(self.save_as); save_bar.addWidget(save)
        reuse = QPushButton('用这张图继续创作'); reuse.clicked.connect(self.use_current_as_reference); save_bar.addWidget(reuse)
        cv.addLayout(save_bar)
        self.chat = QTextBrowser(); self.chat.setMinimumHeight(85); self.chat.setMaximumHeight(150)
        cv.addWidget(self.chat)
        self.reference_label = QLabel('可选：添加参考图，让软件按原图构图进行创作'); self.reference_label.setWordWrap(True)
        cv.addWidget(self.reference_label)
        self.positive = QTextEdit(); self.positive.setPlaceholderText('输入你想生成的画面，例如：a small blue robot reading a book, watercolor illustration')
        self.positive.setMaximumHeight(95); self.positive.setMinimumHeight(65); cv.addWidget(self.positive)
        compose = QHBoxLayout()
        attach = QPushButton('＋ 参考图'); attach.clicked.connect(self.choose_reference); compose.addWidget(attach)
        remove = QPushButton('移除参考图'); remove.clicked.connect(self.clear_reference); compose.addWidget(remove)
        self.generate_button = QPushButton('发送并生成'); self.generate_button.setObjectName('primary'); self.generate_button.setEnabled(False); self.generate_button.clicked.connect(self.enqueue)
        compose.addWidget(self.generate_button, 1); cv.addLayout(compose)
        splitter.addWidget(center)
        panel = QWidget(); form = QFormLayout(panel)
        form.addRow(QLabel('生成设置 · 可选调整'))
        self.model = QComboBox(); form.addRow('基础模型', self.model)
        self.lora = QComboBox(); self.lora.addItem('不使用 LoRA', ''); form.addRow('LoRA', self.lora)
        self.strength = QDoubleSpinBox(); self.strength.setRange(-2, 2); self.strength.setValue(.8); self.strength.setSingleStep(.1); form.addRow('LoRA 强度', self.strength)
        self.negative = QTextEdit('blurry, watermark, text, low quality'); self.negative.setMaximumHeight(85); form.addRow('负向提示词', self.negative)
        self.width = self.spin(64, 2048, 768, 64); self.height = self.spin(64, 2048, 768, 64)
        form.addRow('宽度', self.width); form.addRow('高度', self.height)
        self.steps = self.spin(1, 150, 24); form.addRow('采样步数', self.steps)
        self.cfg = QDoubleSpinBox(); self.cfg.setRange(0, 30); self.cfg.setValue(6.5); form.addRow('CFG', self.cfg)
        self.denoise = QDoubleSpinBox(); self.denoise.setRange(.05, 1); self.denoise.setValue(.6); self.denoise.setSingleStep(.05); form.addRow('参考图重绘幅度', self.denoise)
        self.seed = QLineEdit('-1'); form.addRow('种子（-1 随机）', self.seed)
        self.sampler = QComboBox(); self.scheduler = QComboBox()
        form.addRow('采样器', self.sampler); form.addRow('调度器', self.scheduler)
        self.workflow_label = QLabel('后台自动选择工作流；输入会直接用于生成。'); self.workflow_label.setWordWrap(True); form.addRow(self.workflow_label)
        imp = QPushButton('导入高级工作流 API…'); imp.clicked.connect(self.import_graph); form.addRow(imp)
        reset = QPushButton('恢复自动选择工作流'); reset.clicked.connect(self.reset_graph); form.addRow(reset)
        self.cancel_button = QPushButton('取消当前任务'); self.cancel_button.clicked.connect(self.cancel_current)
        clear = QPushButton('清空本软件待执行队列'); clear.clicked.connect(self.clear_pending); form.addRow(clear)
        self.unload_button = QPushButton('空闲时卸载模型'); self.unload_button.clicked.connect(self.unload); form.addRow(self.unload_button)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel)
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(scroll, 1); rv.addWidget(self.cancel_button)
        splitter.addWidget(right)
        splitter.setSizes([240, 760, 380])
        self.editor = WorkflowEditor()
        self.tabs.addTab(self.editor, '工作流编辑')
        self.editor.draft_requested.connect(self.load_draft_in_editor)
        self.editor.run_requested.connect(self.run_editor_graph)
        self.editor.template_requested.connect(self.activate_editor_template)
        self.editor.became_ready.connect(self.sync_editor_if_needed)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.status = QLabel('未连接'); layout.addWidget(self.status)
        self.progress = QProgressBar(); layout.addWidget(self.progress)
        details = QPushButton('展开 / 收起任务队列与日志'); layout.addWidget(details)
        diagnostic = QWidget(); dv = QVBoxLayout(diagnostic); dv.setContentsMargins(0, 0, 0, 0)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(65); dv.addWidget(self.queue_list)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(80); dv.addWidget(self.log)
        diagnostic.setVisible(False); details.clicked.connect(lambda: diagnostic.setVisible(not diagnostic.isVisible())); layout.addWidget(diagnostic)
        self.editor.message.connect(self.log.append)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_stats); self.timer.start(5000)
        self.stats_busy = False
        self.load_gallery()
        self.restore_chat()
        QTimer.singleShot(200, self.connect_engine)

    @staticmethod
    def spin(minimum, maximum, value, step=1):
        w = QSpinBox(); w.setRange(minimum, maximum); w.setValue(value); w.setSingleStep(step); return w

    def launch(self, action, callback):
        worker = Worker(action); self.workers.append(worker)
        worker.event.connect(callback)
        worker.finished.connect(lambda: self.workers.remove(worker))
        worker.finished.connect(worker.deleteLater); worker.start()

    def connect_engine(self):
        if self.current or self.pending or self.preparing:
            self.log.append('请等待任务结束后更换连接。'); return
        self.connected = False; self.generate_button.setEnabled(False); self.connect_button.setEnabled(False); self.workflow_selector.setEnabled(False)
        try: client = ComfyClient(self.url.text())
        except Exception as exc:
            self.connect_button.setEnabled(True); self.log.append(str(exc)); return
        self.status.setText('正在检测 ComfyUI 和模型…')
        def done(kind, data):
            self.connect_button.setEnabled(True)
            if kind == 'error':
                self.status.setText('连接失败：请启动 ComfyUI 后重试'); self.log.append(data); return
            if kind != 'result': return
            self.client = client; self.info = data; self.connected = True
            self.editor.set_node_info(data['object_info'])
            self.model.clear(); self.model.addItems(data['checkpoints'])
            self.lora.clear(); self.lora.addItem('不使用 LoRA', '')
            for name in data['loras']: self.lora.addItem(name, name)
            self.sampler.clear(); self.sampler.addItems(data['samplers'])
            self.scheduler.clear(); self.scheduler.addItems(data['schedulers'])
            self.generate_button.setEnabled(True)
            self.workflow_selector.setEnabled(True)
            if not self.template_restored:
                self.template_restored = True
                try:
                    saved = DATA / 'chat' / 'active-workflow.json'
                    if saved.exists():
                        preset = json.loads(saved.read_text('utf-8'))
                        if preset.get('graph'): self.activate_template(preset['graph'], preset['title'], preset.get('entry_id'))
                except (OSError, ValueError, KeyError) as exc: self.log.append('未恢复上次工作流：' + str(exc))
            self.status.setText(f'已连接 · {len(data["checkpoints"])} 个 checkpoint · {len(data["loras"])} 个 LoRA')
            write_json(DATA / 'settings.json', {'url': client.url}); self.refresh_stats()
            if self.tabs.currentIndex() == 1: self.editor.connect_url(client.url)
        self.launch(lambda _: client.discover(), done)

    def refresh_stats(self):
        if not self.connected or self.stats_busy: return
        self.stats_busy = True
        def done(kind, data):
            self.stats_busy = False
            if kind == 'result':
                devices = data.get('devices', [])
                if devices:
                    d = devices[0]; total = d.get('vram_total', 0); free = d.get('vram_free', 0)
                    self.gpu.setText(f'{d.get("name", "GPU")}\n显存使用 {(total-free)/2**30:.1f} / {total/2**30:.1f} GB')
        self.launch(lambda _: self.client.request('/system_stats'), done)

    def import_graph(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 ComfyUI API JSON（非 UI 格式）', '', 'JSON (*.json)')
        if not path: return
        try:
            graph = json.loads(Path(path).read_text('utf-8-sig'))
            if not isinstance(graph, dict) or not graph or any(not isinstance(n, dict) or 'class_type' not in n or 'inputs' not in n for n in graph.values()):
                raise ValueError('必须使用 ComfyUI 导出的 API 格式工作流')
            self.activate_template(graph, Path(path).stem)
        except Exception as exc: QMessageBox.warning(self, '导入失败', str(exc))

    def reset_graph(self):
        self.custom_graph = None; self.active_title = '自动选择'
        self.last_chat_graph = None; self.editor_needs_sync = False
        self.workflow_label.setText('后台自动选择：只输入文字走文生图，添加参考图走图生图。')
        self.lora.setEnabled(True); self.strength.setEnabled(True)
        self.workflow_selector.blockSignals(True); self.workflow_selector.setCurrentIndex(0); self.workflow_selector.blockSignals(False)
        write_json(DATA / 'chat' / 'active-workflow.json', {'graph': None})

    def select_chat_workflow(self, index):
        entry = self.workflow_selector.itemData(index)
        if entry is None:
            self.reset_graph(); return
        if not isinstance(entry, dict): return
        try:
            path = workflow_path(entry)
            api = path.with_name('api_snapshot.json')
            if not api.exists() or digest(path) != entry.get('source_sha256'):
                raise ValueError('此工作流尚未绑定。请在高级工作流编辑器打开后点击“用于对话生成”。')
            self.activate_template(json.loads(api.read_text('utf-8')), entry['title'], entry['id'])
        except Exception as exc:
            self.reset_graph(); self.add_chat('软件', str(exc))

    def activate_editor_template(self, payload):
        try:
            self.activate_template(payload['graph'], '高级编辑器工作流')
            self.tabs.setCurrentIndex(0)
            self.add_chat('软件', '已绑定编辑器工作流。输入新的画面描述即可生成，提示词会自动写入工作流。')
        except Exception as exc:
            self.editor.report_error({'error': str(exc)})

    def activate_template(self, graph, title, entry_id=None):
        mapping = bindings(graph)
        self.custom_graph = json.loads(json.dumps(graph))
        self.last_chat_graph = None
        self.active_title = title
        sampler = graph[mapping['sampler']]['inputs']
        self.negative.setPlainText(str(graph[mapping['negative'][0][0]]['inputs'][mapping['negative'][0][1]]))
        self.steps.setValue(int(sampler['steps'])); self.cfg.setValue(float(sampler['cfg']))
        self.sampler.setCurrentText(sampler['sampler_name']); self.scheduler.setCurrentText(sampler['scheduler'])
        for node in graph.values():
            if node['class_type'] == 'EmptyLatentImage':
                self.width.setValue(node['inputs']['width']); self.height.setValue(node['inputs']['height'])
            if node['class_type'] == 'CheckpointLoaderSimple':
                name = node['inputs']['ckpt_name']
                if self.model.findText(name) < 0: self.model.addItem(name)
                self.model.setCurrentText(name)
        self.lora.setEnabled(False); self.strength.setEnabled(False)
        self.workflow_label.setText('后台：' + title + '\n聊天输入、负向词和采样设置会写入此工作流。LoRA 由工作流编辑器配置。')
        self.workflow_selector.blockSignals(True)
        chosen = next((i for i in range(self.workflow_selector.count())
                       if isinstance(self.workflow_selector.itemData(i), dict)
                       and self.workflow_selector.itemData(i).get('id') == entry_id), -1) if entry_id else -1
        if chosen < 0:
            chosen = self.workflow_selector.findData('editor')
            if chosen < 0: self.workflow_selector.addItem(title, 'editor'); chosen = self.workflow_selector.count() - 1
            else: self.workflow_selector.setItemText(chosen, title)
        self.workflow_selector.setCurrentIndex(chosen); self.workflow_selector.blockSignals(False)
        self.editor_needs_sync = True
        write_json(DATA / 'chat' / 'active-workflow.json', {'graph': self.custom_graph, 'title': title, 'entry_id': entry_id})

    def add_chat(self, role, text, image=None, job=None):
        message = {'role': role, 'text': text, 'image': image, 'job': job}
        self.chat_messages.append(message)
        self.render_message(message)
        write_json(DATA / 'chat' / 'history.json', {'schema_version': 1, 'messages': self.chat_messages[-200:]})

    def render_message(self, message):
        role = html.escape(message['role']); text = html.escape(message['text']).replace('\n', '<br>')
        content = f'<p><b>{role}</b>　{text}</p>'
        if message.get('image') and Path(message['image']).is_file():
            src = html.escape(QUrl.fromLocalFile(message['image']).toString(), quote=True)
            content += f'<p><img src="{src}" width="96"></p>'
        self.chat.append(content)
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def restore_chat(self):
        try:
            path = DATA / 'chat' / 'history.json'
            if path.exists():
                self.chat_messages = json.loads(path.read_text('utf-8'))['messages'][-200:]
                for message in self.chat_messages: self.render_message(message)
        except (OSError, ValueError, KeyError): self.chat_messages = []
        if not self.chat_messages:
            self.add_chat('软件', '输入画面描述后发送即可生成，也可以添加参考图。每次发送按本次输入生成；需要沿用上次图片时，将它作为参考图添加。')

    def choose_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, '添加参考图', '', 'Images (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:
            try: self.set_reference(path)
            except Exception as exc: self.add_chat('软件', '参考图读取失败：' + str(exc))

    def set_reference(self, path):
        source = Path(path)
        reader = QImageReader(str(source))
        if not reader.canRead(): raise ValueError('不是可读取的图片文件')
        target = DATA / 'references' / (uuid4().hex + source.suffix.lower())
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        self.reference_path = target
        size = reader.size()
        if size.width() > 0 and size.height() > 0:
            scale = min(1, 1024 / max(size.width(), size.height()))
            self.width.setValue(max(64, round(size.width() * scale / 8) * 8))
            self.height.setValue(max(64, round(size.height() * scale / 8) * 8))
        self.reference_label.setText('已添加参考图：' + source.name + ' · 后续发送会使用此图，可随时移除。')

    def use_current_as_reference(self):
        if self.output:
            try: self.set_reference(self.output)
            except Exception as exc: self.add_chat('软件', '读取参考图失败：' + str(exc))

    def clear_reference(self):
        self.reference_path = None
        self.reference_label.setText('可选：添加参考图，让软件按原图构图进行创作')

    def tab_changed(self, index):
        if index == 1 and self.connected:
            self.editor.connect_url(self.client.url)
            self.sync_editor_if_needed()

    def sync_editor_if_needed(self):
        if self.editor_needs_sync and self.editor.ready and not self.editor.pending:
            graph = self.last_chat_graph or self.custom_graph
            if graph:
                self.editor_needs_sync = False
                self.editor.sync_inputs(graph)

    def graph_snapshot(self, reference_name=''):
        seed = int(self.seed.text())
        if seed == -1: seed = secrets.randbelow(2**53)
        if not 0 <= seed < 2**64: raise ValueError('种子范围为 0–2^64-1，或 -1 随机')
        r = ImageRequest(self.model.currentText(), self.positive.toPlainText(), self.negative.toPlainText(),
            self.width.value(), self.height.value(), self.steps.value(), self.cfg.value(), seed,
            self.sampler.currentText(), self.scheduler.currentText(), self.lora.currentData() or '', self.strength.value())
        user_prompt = r.positive
        if not r.positive.strip():
            if reference_name: r.positive = 'high quality, detailed image'
            else: raise ValueError('请先输入画面描述，或添加一张参考图。')
        if any(v % 8 for v in (r.width, r.height)): raise ValueError('宽高需为 8 的倍数')
        graph = self.custom_graph if self.custom_graph is not None else build_workflow(r)
        graph, mapping = bind_request(graph, r, reference_name, self.denoise.value())
        params = asdict(r)
        params.update(mode='chat', user_prompt=user_prompt, template=self.active_title, bindings=mapping, denoise=self.denoise.value())
        return graph, params

    def load_draft_in_editor(self):
        try:
            graph, _ = self.graph_snapshot()
            self.editor.load_graph(graph)
        except Exception as exc:
            self.editor.report_error({'error': str(exc)})

    def run_editor_graph(self, payload):
        try:
            self.queue_graph(payload['graph'], {'mode': 'workflow_editor'}, payload['workflow'])
            self.tabs.setCurrentIndex(0)
        except Exception as exc:
            self.editor.report_error({'error': str(exc)})

    def enqueue(self):
        try:
            if not self.connected: raise ValueError('请先连接 ComfyUI')
            if self.preparing: return
            reference = self.reference_path
            graph, params = self.graph_snapshot('__aipictures_reference__' if reference else '')
            check_models(graph, self.info['object_info'])
            params['reference'] = str(reference) if reference else None
            self.add_chat('你', params['user_prompt'].strip() or '使用这张参考图生成', str(reference) if reference else None)
            if reference:
                self.preparing = True; self.prepare_cancel.clear()
                self.status.setText('正在准备并上传参考图…')
                self.generate_button.setEnabled(False); self.connect_button.setEnabled(False); self.workflow_selector.setEnabled(False)
                client = self.client
                def uploaded(kind, data):
                    self.preparing = False
                    self.generate_button.setEnabled(self.connected); self.connect_button.setEnabled(self.current is None); self.workflow_selector.setEnabled(True)
                    if self.prepare_cancel.is_set():
                        self.status.setText('生成准备已取消'); self.add_chat('软件', '本次生成准备已取消。'); return
                    if kind == 'error':
                        self.status.setText('参考图上传失败'); self.add_chat('软件', '参考图上传失败：' + str(data)); return
                    if kind != 'result': return
                    for key in params['bindings']['reference']: graph[key]['inputs']['image'] = data
                    params['uploaded_reference'] = data
                    self.submit_chat_graph(graph, params)
                self.launch(lambda _: client.upload_image(reference), uploaded)
            else:
                self.submit_chat_graph(graph, params)
        except Exception as exc:
            self.add_chat('软件', str(exc)); self.log.append(str(exc))

    def submit_chat_graph(self, graph, params):
        try:
            folder = self.queue_graph(graph, params)
            self.last_chat_graph = json.loads(json.dumps(graph))
            self.editor_needs_sync = True
            self.sync_editor_if_needed()
            self.add_chat('软件', '已加入生成队列 · ' + self.active_title, job=str(folder))
        except Exception as exc:
            self.add_chat('软件', '提交失败：' + str(exc))

    def queue_graph(self, graph, params, editor_workflow=None):
        if not self.connected: raise ValueError('请先连接 ComfyUI')
        graph = json.loads(json.dumps(graph))
        if not graph: raise ValueError('工作流没有可运行节点')
        missing = {n['class_type'] for n in graph.values()} - set(self.info['nodes'])
        if missing: raise ValueError('缺少节点：' + ', '.join(sorted(missing)))
        folder = new_job(graph, params)
        if editor_workflow is not None: write_json(folder / 'editor_workflow.json', editor_workflow)
        item = QListWidgetItem(folder.name + ' · 等待'); self.queue_list.addItem(item)
        self.pending.append((graph, params, folder, item))
        self.start_next()
        return folder

    def start_next(self):
        if self.current or not self.pending: return
        graph, params, folder, item = self.pending.pop(0)
        item.setText(folder.name + ' · 执行中')
        cancel = threading.Event()
        self.current = {'folder': folder, 'cancel': cancel, 'params': params}
        self.connect_button.setEnabled(False); self.progress.setRange(0, 0)
        self.status.setText('排队 / 加载模型…'); self.update_job('running')
        def event(kind, data):
            if kind == 'queued':
                self.current['prompt_id'] = data['prompt_id']; self.update_job('queued')
            elif kind == 'progress':
                self.progress.setRange(0, int(data['max'])); self.progress.setValue(int(data['value']))
                self.status.setText(f'采样 {data["value"]} / {data["max"]}')
            elif kind == 'executing':
                self.status.setText('正在执行节点 ' + str(data.get('node') or '结果保存'))
            elif kind in ('result', 'error', 'cancelled'):
                if kind == 'result':
                    write_json(folder / 'result.json', data); self.show_image(data['images'][0]); self.load_gallery()
                if params.get('mode') == 'chat':
                    if kind == 'result': self.add_chat('软件', '生成完成，图片和本次实际工作流已保存。', data['images'][0], str(folder))
                    elif kind == 'cancelled': self.add_chat('软件', '任务已取消。', job=str(folder))
                    else: self.add_chat('软件', '生成失败：' + str(data), job=str(folder))
                self.update_job({'result': 'completed', 'error': 'failed', 'cancelled': 'cancelled'}[kind], None if kind == 'result' else data)
                self.log.append(f'{folder.name} · {kind}' + (f'：{data}' if kind != 'result' else ' · 已自动保存'))
                item.setText(folder.name + ' · ' + {'result':'完成','error':'失败','cancelled':'取消'}[kind])
                self.status.setText({'result':'生成完成，已保存','error':'任务失败，详见日志','cancelled':'任务已取消'}[kind])
                self.progress.setRange(0, 100); self.progress.setValue(100 if kind == 'result' else 0)
                self.current = None; self.connect_button.setEnabled(True); QTimer.singleShot(0, self.start_next)
        self.launch(lambda emit: self.client.generate(graph, folder, emit, cancel), event)

    def update_job(self, status, error=None):
        if self.current:
            write_json(self.current['folder'] / 'job.json', {'schema_version': 1, 'kind': 'image',
                'status': status, 'params': self.current['params'], 'prompt_id': self.current.get('prompt_id'), 'error': error})

    def cancel_current(self):
        if self.current: self.current['cancel'].set(); self.status.setText('正在请求取消本任务…')
        elif self.preparing: self.prepare_cancel.set(); self.status.setText('正在取消生成准备…')

    def clear_pending(self):
        for _, params, folder, item in self.pending:
            write_json(folder / 'job.json', {'schema_version': 1, 'kind': 'image', 'status': 'cancelled', 'params': params})
            item.setText(folder.name + ' · 已清除')
            if params.get('mode') == 'chat': self.add_chat('软件', '已从队列移除此任务。', job=str(folder))
        self.pending.clear()

    def unload(self):
        if not self.connected or self.current or self.pending: return
        def action(_):
            queue = self.client.request('/queue')
            if queue.get('queue_running') or queue.get('queue_pending'): raise RuntimeError('ComfyUI 有其他任务，暂不卸载')
            return self.client.request('/free', {'unload_models': True, 'free_memory': True})
        self.launch(action, lambda kind, data: self.log.append('已请求释放显存' if kind == 'result' else str(data)))

    def load_gallery(self):
        self.gallery.clear()
        for path in sorted((DATA / 'jobs').glob('*/image_*.png'), reverse=True):
            self.gallery.addItem(str(path.relative_to(DATA)))

    def open_history(self, item): self.show_image(str(DATA / item.text()))

    def show_image(self, path):
        self.pixmap = QPixmap(path); self.output = path
        self.caption.setText(path); self.fit_preview()

    def fit_preview(self):
        if not self.pixmap.isNull(): self.preview.setPixmap(self.pixmap.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'preview'): self.fit_preview()

    def save_as(self):
        if not self.output: return
        path, _ = QFileDialog.getSaveFileName(self, '另存图片', 'image.png', 'PNG (*.png)')
        if path:
            try:
                if Path(path).resolve() != Path(self.output).resolve(): shutil.copy2(self.output, path)
            except OSError as exc: QMessageBox.warning(self, '保存失败', str(exc))

    def closeEvent(self, event):
        if self.current or self.workers or self.editor.pending or self.preparing:
            self.status.setText('后台操作尚未结束，请先取消任务并稍候，再关闭窗口。')
            self.log.append('请先取消任务并等待后台操作结束，再关闭窗口。'); event.ignore(); return
        self.clear_pending(); event.accept()


def create_application(args=None):
    app = QApplication(sys.argv if args is None else args)
    app.setStyle('Fusion')
    app.setStyleSheet('''QWidget{background:#191e2b;color:#e4eaf7;font-size:13px;} QLineEdit,QTextEdit,QComboBox,QSpinBox,QDoubleSpinBox,QListWidget{background:#111725;border:1px solid #354056;border-radius:5px;padding:6px;} QPushButton{background:#303c56;border:0;border-radius:6px;padding:9px;} QPushButton:hover{background:#415575;} QPushButton:disabled{color:#6b768b;} QPushButton#primary{background:#6554d9;font-weight:bold;} QProgressBar{border:0;background:#111725;text-align:center;max-height:16px;} QProgressBar::chunk{background:#8875ee;}''')
    return app


def main():
    app = create_application()
    window = Window(); window.show()
    sys.exit(app.exec())


if __name__ == '__main__': main()
