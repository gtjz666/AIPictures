"""Embedded local ComfyUI frontend; no files are installed into ComfyUI."""
import json
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                              QPushButton, QVBoxLayout, QWidget, QComboBox)

from .storage import DATA, write_json
from .workflow_library import list_workflows, workflow_path, inspect_workflow, dependency_summary


class WorkflowEditor(QWidget):
    run_requested = Signal(dict)
    draft_requested = Signal()
    message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.url = None
        self.ready = False
        self.pending = {}
        self.object_info = None
        self.page_generation = 0
        self.ready_signature = None
        self.ready_since = None
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.reload_button = QPushButton('连接 / 重新加载编辑器')
        self.reload_button.clicked.connect(self.reload)
        toolbar.addWidget(self.reload_button)
        self.draft_button = QPushButton('载入图像页工作流')
        self.draft_button.clicked.connect(self.draft_requested.emit)
        toolbar.addWidget(self.draft_button)
        self.import_button = QPushButton('打开工作流副本…')
        self.import_button.clicked.connect(self.import_file)
        toolbar.addWidget(self.import_button)
        self.save_button = QPushButton('保存工作流副本…')
        self.save_button.clicked.connect(self.save_file)
        toolbar.addWidget(self.save_button)
        toolbar.addStretch()
        self.run_button = QPushButton('运行到软件任务队列')
        self.run_button.setObjectName('primary')
        self.run_button.clicked.connect(self.run_graph)
        toolbar.addWidget(self.run_button)
        layout.addLayout(toolbar)
        library_bar = QHBoxLayout()
        library_bar.addWidget(QLabel('本地工作流库'))
        self.library = QComboBox()
        self.library.setMinimumWidth(350)
        self.library.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.library.currentIndexChanged.connect(self.library_selection_changed)
        library_bar.addWidget(self.library, 1)
        self.library_open_button = QPushButton('打开选中工作流')
        self.library_open_button.clicked.connect(self.open_library_entry)
        library_bar.addWidget(self.library_open_button)
        refresh = QPushButton('刷新工作流库')
        refresh.clicked.connect(self.refresh_library)
        library_bar.addWidget(refresh)
        layout.addLayout(library_bar)
        self.library_info = QLabel()
        self.library_info.setWordWrap(True)
        layout.addWidget(self.library_info)
        self.status = QLabel('先连接本地 ComfyUI，再打开工作流编辑器。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        hint = QLabel('在画布内编辑节点、拖动连线和调整参数。使用上方“运行到软件任务队列”可在图像页查看进度和自动保存结果。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        # The app owns this profile for its lifetime, independently of Desktop/browser profiles.
        self.profile = QWebEngineProfile('AIPictures-workflows', QApplication.instance())
        self.profile.setPersistentStoragePath(str(DATA / 'browser' / 'storage'))
        self.profile.setCachePath(str(DATA / 'browser' / 'cache'))
        self.profile.downloadRequested.connect(self.download_requested)
        self.web = QWebEngineView(self)
        self.page = QWebEnginePage(self.profile, self.web)
        self.page.setBackgroundColor(Qt.GlobalColor.black)
        self.web.setPage(self.page)
        self.web.loadStarted.connect(self.load_started)
        self.web.loadFinished.connect(self.load_finished)
        layout.addWidget(self.web, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(200)
        self.ready_deadline = None
        self.refresh_library()
        self.set_ready(False)

    def set_ready(self, ready):
        self.ready = ready
        for button in (self.draft_button, self.import_button, self.save_button, self.run_button):
            button.setEnabled(ready and not self.pending)
        self.library_open_button.setEnabled(ready and not self.pending and self.library.currentData() is not None)

    def set_node_info(self, info):
        self.object_info = info
        self.refresh_library()

    def refresh_library(self):
        selected = self.library.currentData()
        selected_id = selected.get('id') if selected else None
        self.library.blockSignals(True)
        self.library.clear()
        try:
            entries = list_workflows()
            for entry in entries:
                if self.object_info:
                    graph = json.loads(workflow_path(entry).read_text('utf-8-sig'))
                    entry['compatibility'] = inspect_workflow(graph, self.object_info)
                report = entry.get('compatibility', {})
                verified = entry.get('validation', {}).get('generation_verified')
                status = ('出图已验证' if verified else '依赖齐全') if report.get('dependencies_ready') else '待补依赖'
                self.library.addItem(entry['title'] + ' · ' + status, entry)
                if entry.get('id') == selected_id:
                    self.library.setCurrentIndex(self.library.count() - 1)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.message.emit('读取本地工作流库失败：' + str(exc))
        if not self.library.count():
            self.library.addItem('暂无已导入工作流', None)
        self.library.blockSignals(False)
        self.library_selection_changed()
        self.set_ready(self.ready)

    def library_selection_changed(self, _index=None):
        entry = self.library.currentData()
        self.library_info.setText(dependency_summary(entry.get('compatibility', {})) if entry else '可通过“打开工作流副本…”载入已有 JSON。')
        self.library_open_button.setEnabled(self.ready and not self.pending and entry is not None)

    def open_library_entry(self):
        entry = self.library.currentData()
        if not entry:
            return
        try:
            path = workflow_path(entry)
            graph = json.loads(path.read_text('utf-8-sig'))
            self.load_graph(graph, path.stem + '-AIPictures-copy',
                            callback=lambda result: self.fit_graph() if result['ok'] else None,
                            show_missing_models=False)
        except (OSError, ValueError, KeyError) as exc:
            self.report_error({'error': str(exc)})

    def fit_graph(self):
        self.action('''
            const nodes = app.rootGraph._nodes;
            if (!nodes.length) return {};
            const x1 = Math.min(...nodes.map(n => n.pos[0]));
            const y1 = Math.min(...nodes.map(n => n.pos[1]));
            const x2 = Math.max(...nodes.map(n => n.pos[0] + n.size[0]));
            const y2 = Math.max(...nodes.map(n => n.pos[1] + n.size[1]));
            const rect = app.canvas.canvas.getBoundingClientRect();
            const scale = Math.max(.05, Math.min(1, rect.width / (x2-x1+160), rect.height / (y2-y1+160)));
            app.canvas.ds.scale = scale;
            app.canvas.ds.offset = [(rect.width/scale-(x2-x1))/2-x1, (rect.height/scale-(y2-y1))/2-y1];
            app.canvas.setDirty(true, true);
            return {};
        ''', lambda result: self.report_error(result) if not result['ok'] else None)

    def connect_url(self, url):
        if self.url != url:
            self.url = url
            self.web.setUrl(QUrl(url))

    def reload(self):
        if self.url:
            self.web.setUrl(QUrl(self.url))
        else:
            self.status.setText('请先在窗口顶部连接 ComfyUI。')

    def load_started(self):
        self.page_generation += 1
        callbacks = [item['callback'] for item in self.pending.values()]
        self.pending.clear()
        for callback in callbacks:
            callback({'ok': False, 'error': '编辑器已重新加载，请重试操作'})
        self.set_ready(False)
        self.ready_deadline = None
        self.ready_signature = None
        self.ready_since = None
        self.status.setText('正在加载本地 ComfyUI 节点编辑器…')

    def load_finished(self, ok):
        if not ok:
            self.status.setText('编辑器加载失败。确认 ComfyUI 已启动，再点“重新加载”。')
        else:
            self.ready_deadline = time.monotonic() + 90

    def poll(self):
        if not self.ready and self.ready_deadline:
            if time.monotonic() > self.ready_deadline:
                self.ready_deadline = None
                self.status.setText('节点编辑器初始化超时，请重新加载。')
            else:
                generation = self.page_generation
                self.page.runJavaScript('''(() => {
                    const graph = window.app?.rootGraph;
                    if (!window.app?.canvas || !window.LiteGraph?.registered_node_types?.KSampler ||
                        document.getElementById('splash-loader') ||
                        window.comfyAPI?.changeTracker?.ChangeTracker?.isLoadingGraph ||
                        !graph || (!graph._nodes.length && !graph._version)) return '';
                    return JSON.stringify([graph.id, graph._version, graph._nodes.length]);
                })()''',
                    lambda value: self.check_ready(value, generation))
        for token, item in list(self.pending.items()):
            if item['polling']:
                continue
            if time.monotonic() > item['deadline']:
                self.pending.pop(token)
                self.set_ready(self.ready)
                item['callback']({'ok': False, 'error': '编辑器操作超时，请检查画布中的提示'})
                continue
            item['polling'] = True
            self.page.runJavaScript(f'window.__aipResults?.[{json.dumps(token)}] ?? null',
                lambda value, token=token: self.receive(token, value))

    def check_ready(self, value, generation):
        if generation != self.page_generation or not self.ready_deadline:
            return
        if not value:
            self.ready_signature = None
            self.ready_since = None
            return
        if value != self.ready_signature:
            self.ready_signature = value
            self.ready_since = time.monotonic()
            return
        # Startup restores saved tabs after registering the canvas. Let that graph settle
        # before accepting an import, so restoration cannot replace the just-imported graph.
        if self.ready_since is not None and time.monotonic() - self.ready_since >= 1:
            self.ready_deadline = None
            self.set_ready(True)
            self.status.setText('工作流编辑器已就绪 · 使用独立编辑器缓存；打开文件不会覆盖源文件。')

    def action(self, script, callback):
        if not self.ready:
            callback({'ok': False, 'error': '工作流编辑器尚未就绪'})
            return
        token = uuid4().hex
        self.pending[token] = {'callback': callback, 'deadline': time.monotonic() + 60, 'polling': False}
        self.set_ready(self.ready)
        # Qt's JavaScript callback cannot await Promise values; poll a JSON result instead.
        self.page.runJavaScript('''(() => {
            window.__aipResults ??= {};
            (async () => {
                const app = window.comfyAPI?.app?.app;
                if (!app?.canvas || !app?.rootGraph) throw new Error('ComfyUI 编辑器尚未就绪');
                return await (async () => {''' + script + '''})();
            })().then(value => {
                window.__aipResults[''' + json.dumps(token) + '''] = JSON.stringify({ok: true, value});
            }).catch(error => {
                window.__aipResults[''' + json.dumps(token) + '''] = JSON.stringify({ok: false, error: String(error)});
            });
        })()''')

    def receive(self, token, value):
        item = self.pending.get(token)
        if not item:
            return
        item['polling'] = False
        if not isinstance(value, str) or not value:
            return
        self.pending.pop(token)
        self.set_ready(self.ready)
        self.page.runJavaScript(f'delete window.__aipResults[{json.dumps(token)}]')
        try:
            result = json.loads(value)
        except ValueError:
            result = {'ok': False, 'error': '编辑器返回了无效数据'}
        item['callback'](result)

    def report_error(self, result):
        message = result.get('error', '未知错误')
        self.status.setText(message)
        self.message.emit(message)

    def load_graph(self, graph, name='AIPictures-draft', callback=None, show_missing_models=True):
        # handleFile uses the installed frontend's own API/UI workflow conversion.
        is_ui = isinstance(graph, dict) and isinstance(graph.get('nodes'), list)
        is_api = isinstance(graph, dict) and bool(graph) and all(
            isinstance(node, dict) and isinstance(node.get('class_type'), str)
            and isinstance(node.get('inputs'), dict) for node in graph.values())
        if not (is_ui or is_api):
            result = {'ok': False, 'error': '请选择有效的 ComfyUI UI 或 API 格式工作流 JSON'}
            self.report_error(result)
            if callback:
                callback(result)
            return
        script = 'const graph = ' + json.dumps(graph, ensure_ascii=True) + ';'
        if is_ui and not show_missing_models:
            script += ('await app.loadGraphData(graph, true, true, ' + json.dumps(name) +
                       ', {showMissingModelsDialog: false});')
        else:
            script += ('const file = new File([JSON.stringify(graph)], ' + json.dumps(name + '.json') +
                       ', {type: "application/json"});await app.handleFile(file);')
        script += 'return {nodes: app.rootGraph._nodes.length};'
        def done(result):
            if result['ok']:
                self.status.setText(f'已载入独立副本：{name} · 可直接编辑节点和连线')
            else:
                self.report_error(result)
            if callback:
                callback(result)
        self.action(script, done)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开 ComfyUI 工作流副本（UI 或 API JSON）', '', 'JSON (*.json)')
        if not path:
            return
        try:
            graph = json.loads(Path(path).read_text('utf-8-sig'))
            if not isinstance(graph, dict):
                raise ValueError('工作流 JSON 顶层必须是对象')
            self.load_graph(graph, Path(path).stem + '-AIPictures-copy')
        except (OSError, ValueError) as exc:
            self.report_error({'error': str(exc)})

    def snapshot(self, callback):
        self.action('''const prompt = await app.graphToPrompt();
            return {graph: prompt.output, workflow: prompt.workflow};''', callback)

    def run_graph(self):
        self.run_button.setEnabled(False)
        def done(result):
            self.run_button.setEnabled(self.ready)
            if not result['ok']:
                self.report_error(result)
                return
            payload = result['value']
            if not payload.get('graph'):
                self.report_error({'error': '当前画布没有可运行的输出节点'})
                return
            self.run_requested.emit(payload)
        self.snapshot(done)

    def save_file(self):
        default = DATA / 'workflows' / 'workflow.json'
        default.parent.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, '保存 UI 工作流副本（保留节点位置和连线）', str(default), 'JSON (*.json)')
        if not path:
            return
        def done(result):
            if not result['ok']:
                self.report_error(result)
                return
            try:
                write_json(Path(path), result['value']['workflow'])
                self.status.setText('已保存工作流副本：' + path)
            except (OSError, KeyError) as exc:
                self.report_error({'error': str(exc)})
        self.snapshot(done)

    def download_requested(self, download):
        path, _ = QFileDialog.getSaveFileName(self, '保存编辑器导出的文件', str(DATA / 'workflows' / download.downloadFileName()))
        if not path:
            download.cancel()
            return
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            download.setDownloadDirectory(str(target.parent))
            download.setDownloadFileName(target.name)
            download.accept()
        except OSError as exc:
            download.cancel()
            self.report_error({'error': str(exc)})
