import json
import secrets
import shutil
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFormLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QProgressBar, QListWidget, QListWidgetItem, QSplitter, QFileDialog, QMessageBox, QScrollArea, QTabWidget)
from .engine import ComfyClient, Cancelled
from .workflow import ImageRequest, build_workflow
from .storage import DATA, write_json, new_job
from .workflow_editor import WorkflowEditor


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
        self.tabs.addTab(image_page, '图像生成')
        left = QWidget(); lv = QVBoxLayout(left)
        lv.addWidget(QLabel('创作空间'))
        edit = QPushButton('打开工作流编辑器'); edit.clicked.connect(lambda: self.tabs.setCurrentIndex(1)); lv.addWidget(edit)
        lv.addWidget(QLabel('数据集 / 训练 / 骨骼 / 动画 / 视频\n后续阶段，尚未实现'))
        lv.addWidget(QLabel('本地生成记录（双击预览）'))
        self.gallery = QListWidget(); self.gallery.itemDoubleClicked.connect(self.open_history)
        lv.addWidget(self.gallery, 1)
        open_data = QPushButton('打开素材与结果目录'); open_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA))))
        lv.addWidget(open_data)
        self.gpu = QLabel('显存：等待连接'); self.gpu.setWordWrap(True); lv.addWidget(self.gpu)
        splitter.addWidget(left)
        center = QWidget(); cv = QVBoxLayout(center)
        self.preview = QLabel('连接本地 ComfyUI，开始第一次创作'); self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(400, 380); self.preview.setStyleSheet('background:#10141e;border:1px solid #31394c;border-radius:12px;color:#8d9bb4')
        cv.addWidget(self.preview, 1)
        self.caption = QLabel('生成结果自动保存 PNG、参数和完整工作流'); self.caption.setWordWrap(True); cv.addWidget(self.caption)
        save = QPushButton('将当前图片另存为…'); save.clicked.connect(self.save_as); cv.addWidget(save)
        splitter.addWidget(center)
        panel = QWidget(); form = QFormLayout(panel)
        self.model = QComboBox(); form.addRow('基础模型', self.model)
        self.lora = QComboBox(); self.lora.addItem('不使用 LoRA', ''); form.addRow('LoRA', self.lora)
        self.strength = QDoubleSpinBox(); self.strength.setRange(-2, 2); self.strength.setValue(.8); self.strength.setSingleStep(.1); form.addRow('LoRA 强度', self.strength)
        self.positive = QTextEdit('a cozy wooden cabin beside a lake, autumn forest, cinematic light, detailed digital painting'); self.positive.setMaximumHeight(150); form.addRow('正向提示词', self.positive)
        self.negative = QTextEdit('blurry, watermark, text, low quality'); self.negative.setMaximumHeight(85); form.addRow('负向提示词', self.negative)
        self.width = self.spin(64, 2048, 768, 64); self.height = self.spin(64, 2048, 768, 64)
        form.addRow('宽度', self.width); form.addRow('高度', self.height)
        self.steps = self.spin(1, 150, 24); form.addRow('采样步数', self.steps)
        self.cfg = QDoubleSpinBox(); self.cfg.setRange(0, 30); self.cfg.setValue(6.5); form.addRow('CFG', self.cfg)
        self.seed = QLineEdit('-1'); form.addRow('种子（-1 随机）', self.seed)
        self.sampler = QComboBox(); self.scheduler = QComboBox()
        form.addRow('采样器', self.sampler); form.addRow('调度器', self.scheduler)
        self.workflow_label = QLabel('内置 SDXL 文生图'); form.addRow(self.workflow_label)
        imp = QPushButton('导入独立 API 工作流 JSON'); imp.clicked.connect(self.import_graph); form.addRow(imp)
        reset = QPushButton('恢复内置 SDXL 工作流'); reset.clicked.connect(self.reset_graph); form.addRow(reset)
        self.generate_button = QPushButton('＋ 添加生成任务'); self.generate_button.setObjectName('primary'); self.generate_button.setEnabled(False); self.generate_button.clicked.connect(self.enqueue)
        self.cancel_button = QPushButton('取消当前任务'); self.cancel_button.clicked.connect(self.cancel_current)
        clear = QPushButton('清空本软件待执行队列'); clear.clicked.connect(self.clear_pending); form.addRow(clear)
        self.unload_button = QPushButton('空闲时卸载模型'); self.unload_button.clicked.connect(self.unload); form.addRow(self.unload_button)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(panel)
        right = QWidget(); rv = QVBoxLayout(right); rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(scroll, 1); rv.addWidget(self.generate_button); rv.addWidget(self.cancel_button)
        splitter.addWidget(right)
        splitter.setSizes([240, 760, 380])
        self.editor = WorkflowEditor()
        self.tabs.addTab(self.editor, '工作流编辑')
        self.editor.draft_requested.connect(self.load_draft_in_editor)
        self.editor.run_requested.connect(self.run_editor_graph)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.status = QLabel('未连接'); layout.addWidget(self.status)
        self.progress = QProgressBar(); layout.addWidget(self.progress)
        self.queue_list = QListWidget(); self.queue_list.setMaximumHeight(85); layout.addWidget(self.queue_list)
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(110); layout.addWidget(self.log)
        self.editor.message.connect(self.log.append)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_stats); self.timer.start(5000)
        self.stats_busy = False
        self.load_gallery()
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
        if self.current or self.pending:
            self.log.append('请等待任务结束后更换连接。'); return
        self.connected = False; self.generate_button.setEnabled(False); self.connect_button.setEnabled(False)
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
            self.model.clear(); self.model.addItems(data['checkpoints'])
            self.lora.clear(); self.lora.addItem('不使用 LoRA', '')
            for name in data['loras']: self.lora.addItem(name, name)
            self.sampler.clear(); self.sampler.addItems(data['samplers'])
            self.scheduler.clear(); self.scheduler.addItems(data['schedulers'])
            self.generate_button.setEnabled(True)
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
            self.custom_graph = graph; self.workflow_label.setText('自定义：' + Path(path).name)
            self.log.append('自定义模式使用 JSON 内参数；右侧提示词和模型参数只用于内置模式。请确保输入文件已在 ComfyUI 中存在。')
        except Exception as exc: QMessageBox.warning(self, '导入失败', str(exc))

    def reset_graph(self):
        self.custom_graph = None; self.workflow_label.setText('内置 SDXL 文生图')

    def tab_changed(self, index):
        if index == 1 and self.connected:
            self.editor.connect_url(self.client.url)

    def graph_snapshot(self):
        if self.custom_graph is not None:
            return json.loads(json.dumps(self.custom_graph)), {'mode': 'custom_api'}
        seed = int(self.seed.text())
        if seed == -1: seed = secrets.randbelow(2**63)
        if not 0 <= seed < 2**64: raise ValueError('种子范围为 0–2^64-1，或 -1 随机')
        r = ImageRequest(self.model.currentText(), self.positive.toPlainText(), self.negative.toPlainText(),
            self.width.value(), self.height.value(), self.steps.value(), self.cfg.value(), seed,
            self.sampler.currentText(), self.scheduler.currentText(), self.lora.currentData() or '', self.strength.value())
        return build_workflow(r), asdict(r)

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
            graph, params = self.graph_snapshot()
            self.queue_graph(graph, params)
        except Exception as exc: QMessageBox.warning(self, '无法创建任务', str(exc))

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

    def clear_pending(self):
        for _, params, folder, item in self.pending:
            write_json(folder / 'job.json', {'schema_version': 1, 'kind': 'image', 'status': 'cancelled', 'params': params})
            item.setText(folder.name + ' · 已清除')
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
        if self.current or self.workers or self.editor.pending:
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
