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
from PySide6.QtGui import QPixmap, QImageReader
from PySide6.QtWidgets import QApplication, QMainWindow, QSpinBox, QListWidgetItem, QFileDialog, QMessageBox
from .engine import ComfyClient, Cancelled
from .workflow import ImageRequest, build_workflow
from .storage import DATA, write_json, new_job
from .workflow_editor import WorkflowEditor
from .prompt_binding import bind_request, bindings, check_models
from .workflow_library import list_workflows, workflow_path, digest
from .character_profile import load_profile
from .action_intent import parse_intent, walk_intent
from .prompt_text import negative_text
from .lora_catalog import entry_for,display_name,style_prompt,validate_selection
from .panels import SkeletonDialog
from .result_cache import ResultCache, within_any


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
        self.preview_path=None
        self.preview_role=None
        self.image_viewer = None
        self.custom_graph = None
        self.active_title = '自动选择'
        self.reference_path = None
        self.reference_display_name = None
        self.reference_character=False
        self.preparing = False
        self.prepare_cancel = threading.Event()
        self.last_chat_graph = None
        self.editor_needs_sync = False
        self.chat_messages = []
        self.template_restored = False
        self.connected = False
        self.character_profile = None
        self.character_loading = False
        self.cache_store=ResultCache(); self.cache_busy=False
        from .studio_layout import build_studio
        build_studio(self)
        config = DATA / 'settings.json'
        if config.exists():
            try: self.url.setText(json.loads(config.read_text('utf-8'))['url'])
            except (ValueError, KeyError): pass
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

    def refresh_loras(self):
        selected=self.lora.currentData(); category=self.lora_category.currentText()
        self.lora.blockSignals(True); self.lora.clear(); self.lora.addItem('不使用 LoRA','')
        for name in getattr(self,'info',{}).get('loras',[]):
            entry=entry_for(name)
            if category!='全部类型' and (entry['category'] if entry else '未分类')!=category: continue
            self.lora.addItem(display_name(name),name)
            if entry: self.lora.setItemData(self.lora.count()-1,entry['description'],Qt.ItemDataRole.ToolTipRole)
        index=self.lora.findData(selected)
        self.lora.setCurrentIndex(max(0,index)); self.lora.blockSignals(False)
        self.update_lora_state()

    def lora_changed(self):
        entry=entry_for(self.lora.currentData())
        if entry: self.strength.setValue(entry['recommended_strength'])
        self.update_lora_state()

    def update_lora_state(self):
        if not hasattr(self,'lora_details'): return
        walking=self.generation_type.currentData()=='walk'
        enabled=not walking or (self.animation_engine.currentData()=='wan' and self.animation_source.currentData()=='text')
        self.lora.setEnabled(enabled); self.lora_category.setEnabled(enabled)
        self.strength.setEnabled(enabled and bool(self.lora.currentData()))
        if not enabled:
            self.lora_details.setText('当前模式不使用 SDXL 风格 LoRA。文字动画可用于角色图；参考图动画沿用参考外观。\n如需改变参考画风，可先用单张 + LoRA 生成，再作为动画参考。')
            return
        entry=entry_for(self.lora.currentData())
        scope='文字动画：仅角色图生效，Wan 沿用角色外观。' if walking else '本次单图生效，自动接入当前工作流。'
        if entry:
            trigger='、'.join(entry['triggers']) or '无需触发词'
            self.lora_details.setText(f'{entry["description"]}\n适用 SDXL · 推荐强度 {entry["recommended_strength"]:g}\n触发词：{trigger}\n选中后加入对应风格词和触发词。\n'+scope)
            try: validate_selection(self.lora.currentData(),self.model.currentText())
            except ValueError: self.lora_details.setText(self.lora_details.text()+'\n当前基础模型未确认兼容，请选择 SDXL。')
        else:
            self.lora_details.setText(('未分类本地 LoRA，请核对其基础模型。\n' if self.lora.currentData() else '可按类型选择风格。\n')+scope)
        if self.custom_graph and any(n['class_type']=='LoraLoader' and not n.get('_meta',{}).get('aipictures_lora') for n in self.custom_graph.values()):
            self.lora_details.setText(self.lora_details.text()+'\n原工作流另有 LoRA，当前选择会叠加；可在高级编辑器调整原配置。')

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
            profile = load_profile()
            required_pose = profile['pose_requires'] if profile else 'controlnet-openpose-sdxl-1.0-xinsir.safetensors'
            pose_weights = data['object_info'].get('ControlNetLoader', {}).get('input', {}).get('required', {}).get('control_net_name', [[]])[0]
            self.character_route.setItemText(1, '骨骼约束 · 已识别' if required_pose in pose_weights else '骨骼约束 · 缺权重')
            previous_model=self.model.currentText(); previous_sampler=self.sampler.currentText() or 'dpmpp_2m'
            previous_scheduler=self.scheduler.currentText() or 'karras'
            self.model.clear(); self.model.addItems(data['checkpoints'])
            if self.model.findText(previous_model)>=0: self.model.setCurrentText(previous_model)
            self.refresh_loras()
            self.sampler.clear(); self.sampler.addItems(data['samplers'])
            self.scheduler.clear(); self.scheduler.addItems(data['schedulers'])
            if self.sampler.findText(previous_sampler)>=0: self.sampler.setCurrentText(previous_sampler)
            if self.scheduler.findText(previous_scheduler)>=0: self.scheduler.setCurrentText(previous_scheduler)
            self.generate_button.setEnabled(True)
            self.workflow_selector.setEnabled(self.generation_type.currentData()!='walk')
            if not self.template_restored:
                self.template_restored = True
                try:
                    saved = DATA / 'chat' / 'active-workflow.json'
                    if saved.exists():
                        preset = json.loads(saved.read_text('utf-8'))
                        # References are session choices: never restore a bundled image implicitly.
                        if preset.get('graph') and not preset.get('character_id') and not any(
                            node['class_type']=='LoadImage' for node in preset['graph'].values()):
                            self.activate_template(preset['graph'], preset['title'], preset.get('entry_id'))
                except (OSError, ValueError, KeyError) as exc: self.log.append('未恢复上次工作流：' + str(exc))
            self.status.setText(f'已连接 · {len(data["checkpoints"])} 个 checkpoint · {len(data["loras"])} 个 LoRA')
            write_json(DATA / 'settings.json', {'url': client.url}); self.refresh_stats()
            if self.tabs.currentIndex() == 1: self.editor.connect_url(client.url)
        self.launch(lambda _: client.discover(), done)

    def refresh_stats(self):
        if not self.connected or self.stats_busy or self.current or self.preparing: return
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
        self.reference_character=False
        self.character_profile = None; self.context_label.setText('创作')
        self.character_summary.setText('当前为通用创作，可随时应用角色基准。')
        self.pose_choice.setEnabled(False)
        self.positive.setPlaceholderText('描述画面或动作要求…')
        self.last_chat_graph = None; self.editor_needs_sync = False
        self.workflow_label.setText('后台自动选择：只输入文字走文生图，添加参考图走图生图。')
        self.update_lora_state()
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
        self.character_profile = None
        self.reference_character=False
        self.context_label.setText(title)
        if not self.character_loading:
            self.character_summary.setText('当前使用自定义工作流，可重新应用角色基准。')
            self.pose_choice.setEnabled(False)
            self.positive.setPlaceholderText('描述画面或动作要求…')
        self.custom_graph = json.loads(json.dumps(graph))
        self.last_chat_graph = None
        self.active_title = title
        sampler = graph[mapping['sampler']]['inputs']
        self.negative.setPlainText(str(graph[mapping['negative'][0][0]]['inputs'][mapping['negative'][0][1]]))
        self.steps.setValue(int(sampler['steps'])); self.cfg.setValue(float(sampler['cfg']))
        self.sampler.setCurrentText(sampler['sampler_name']); self.scheduler.setCurrentText(sampler['scheduler'])
        for node in graph.values():
            if node['class_type'] in ('EmptyLatentImage', 'ImageScale'):
                self.width.setValue(node['inputs']['width']); self.height.setValue(node['inputs']['height'])
            if node['class_type'] == 'CheckpointLoaderSimple':
                name = node['inputs']['ckpt_name']
                if self.model.findText(name) < 0: self.model.addItem(name)
                self.model.setCurrentText(name)
        self.update_lora_state()
        self.workflow_label.setText('后台：' + title + '\n聊天输入、负向词、采样和所选风格 LoRA 会写入工作流副本。')
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

    def open_assets(self):
        self.load_gallery(); self.assets_dialog.show(); self.assets_dialog.raise_()

    def open_settings(self,key):
        for name,dialog in self.settings_dialogs.items():
            if name!=key: dialog.hide()
        self.settings_dialogs[key].show_near(self.settings_buttons[key])

    def update_sidebar_summary(self):
        walking=self.generation_type.currentData()=='walk'
        text=('走路动画序列帧' if walking else '单张图片')+'\n'
        if walking:
            text+=('AI 连续 · 14B' if self.animation_engine.currentData()=='wan' else '旧版人体骨骼')+'\n'
            text+=f'{self.walk_count.currentData()} 帧 · {self.walk_fps.value()} FPS\n'
        text+=f'{self.width.value()} × {self.height.value()} · 透明输出'
        self.creation_summary.setText(text)

    def open_skeleton(self):
        profile = load_profile()
        if not profile:
            self.add_chat('软件', '尚未安装角色基准，请先导入基准图片。'); return
        self.skeleton_dialog = SkeletonDialog(profile, self)
        self.skeleton_dialog.show()

    def character_selection_changed(self, _index=None):
        if self.character_loading: return
        if self.character_profile: self.apply_character()

    def generation_type_changed(self, _index=None):
        walking = self.generation_type.currentData() == 'walk'
        self.walk_settings.setVisible(walking)
        self.generate_button.setText('生成行走动画' if walking else '发送并生成')
        for control in (self.width,self.height,self.denoise,self.cfg,self.lora,self.strength):
            control.setEnabled(not walking)
        if not walking and self.custom_graph is not None:
            self.lora.setEnabled(False); self.strength.setEnabled(False)
        if walking:
            self.width.setValue(768); self.height.setValue(1024)
        self.animation_steps.setEnabled(walking and self.animation_engine.currentData()=='wan')
        temporal=walking and self.animation_engine.currentData()=='wan'
        self.model.setEnabled(not temporal or self.animation_source.currentData()=='text')
        self.steps.setEnabled(not temporal)
        self.sampler.setEnabled(not walking); self.scheduler.setEnabled(not walking)
        self.workflow_selector.setEnabled(not walking and self.connected and not self.preparing)
        self.update_lora_state()
        title=(self.reference_display_name or Path(self.reference_path).name) if self.reference_path else (
            self.character_profile['title'] if self.character_profile else '导入参考图')
        if walking and self.animation_source.currentData()=='text': title='文字创建角色'
        if walking and self.animation_source.currentData()=='text':
            self.reference_label.setText('文字创建角色 · 本次动画不使用已添加的参考图。')
        elif self.reference_path:
            self.reference_label.setText('已添加参考图：'+(self.reference_display_name or Path(self.reference_path).name))
        elif self.character_profile:
            self.reference_label.setText('使用角色基准：'+self.character_profile['title'])
        else: self.reference_label.setText('可添加参考图')
        self.context_label.setText('走路动画 · '+title if walking else self.active_title)
        self.update_intent_hint()
        self.update_sidebar_summary()

    def update_intent_hint(self):
        walking = self.generation_type.currentData() == 'walk'
        intent = walk_intent(self.positive.toPlainText()) if walking else parse_intent(self.positive.toPlainText())
        labels = {'walk':'行走','reach':'向前伸手','stand':'站立','run':'奔跑','jump':'跳跃'}
        title = labels.get(intent.action,'未指定动作')
        text = ('已选择动画 · ' if walking else '动作识别 · ') + title
        if walking and self.animation_engine.currentData()=='wan' and not intent.direction_explicit:
            text += ' · 朝向沿用参考图'
        elif not walking and not intent.direction_explicit and not self.character_profile:
            text += ' · 朝向未指定'
        else: text += ' · 朝' + ('左' if intent.direction == 'left' else '右')
        if intent.action in ('run','jump'): text += '\n此动作暂未提供骨骼周期。'
        elif intent.action == 'walk' and not walking: text += '\n当前只生成单张；连续动作请选人物行走动画帧。'
        if walking and self.animation_engine.currentData()=='wan':
            text += ' · 中文描述直接送入动画工作流'
        elif intent.unmatched: text += '\n暂未识别：' + intent.unmatched
        self.intent_hint.setText(text)

    def apply_character(self, _checked=False, route=None):
        if not self.connected:
            self.status.setText('请先连接本地引擎。'); return
        profile = load_profile()
        if not profile:
            self.add_chat('软件', '未找到角色基准文件。'); return
        try:
            self.character_loading = True
            mode = route or self.character_route.currentData()
            self.character_route.setCurrentIndex(0 if mode == 'baseline' else 1)
            self.pose_choice.setEnabled(mode == 'pose')
            pose_key = self.pose_choice.currentData()
            path = profile['baseline_graph'] if mode == 'baseline' else profile['poses'][pose_key]['graph']
            graph = json.loads(Path(path).read_text('utf-8'))
            title = profile['title'] + (' / 参考重绘' if mode == 'baseline' else ' / 骨骼约束')
            self.activate_template(graph, title)
            self.character_profile = profile
            self.set_reference(profile['reference'])
            self.width.setValue(768); self.height.setValue(1024)
            self.denoise.setValue(.3 if mode == 'baseline' else 1.)
            self.seed.setText('20261026')
            self.positive.setPlaceholderText('输入动作或补充要求；留空可按角色基准生成。')
            self.show_image(profile['reference'],role='reference'); self.caption.setText('角色基准 · 尚未生成')
            missing = None
            try: check_models(graph, self.info['object_info'])
            except ValueError as exc: missing = str(exc)
            self.character_summary.setText(profile['title'] + '\n' + (missing or '参考图与模型已就绪。') +
                '\n根据动作关键词选择骨骼参考，默认输出透明背景。')
            write_json(DATA / 'chat' / 'active-workflow.json', {'graph': graph, 'title': title,
                'character_id': profile['id'], 'route': mode})
            self.add_chat('软件', '已应用角色基准：' + ('参考重绘。固定角色提示词会自动保留。' if mode == 'baseline'
                          else '骨骼约束。' + (missing or '依赖检查通过。')))
        except Exception as exc:
            self.add_chat('软件', '应用角色基准失败：' + str(exc))
        finally:
            self.character_loading = False
            self.generation_type_changed()

    def add_chat(self, role, text, image=None, job=None):
        message = {'role': role, 'text': text, 'image': image, 'job': job}
        self.chat_messages.append(message)
        self.render_message(message)
        if role == '软件':
            self.output_toggle.setToolTip(text + '\n\n展开 / 隐藏输出面板：Ctrl+J')
            if not self.current and not self.preparing:
                self.status.setText(text.splitlines()[0][:110] if text else '')
                self.status.setToolTip(text)
        write_json(DATA / 'chat' / 'history.json', {'schema_version': 1, 'messages': self.chat_messages[-200:]})

    def render_message(self, message):
        role = html.escape(message['role']); text = html.escape(message['text']).replace('\n', '<br>')
        content = f'<p><b>{role}</b>　{text}</p>'
        if message.get('image') and Path(message['image']).is_file():
            src = html.escape(QUrl.fromLocalFile(message['image']).toString(), quote=True)
            content += f'<p><img src="{src}" width="72"></p>'
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
        self.reference_display_name = source.name
        self.animation_source.setCurrentIndex(0)
        if not self.character_loading and self.character_profile and digest(target)!=self.character_profile['source_sha256']:
            from .character_profile import character_workflow
            from .reference_analysis import REFERENCE_POSITIVE,REFERENCE_NEGATIVE
            graph=character_workflow('__reference__')
            graph['2']['inputs']['text']=REFERENCE_POSITIVE; graph['3']['inputs']['text']=REFERENCE_NEGATIVE
            self.activate_template(graph,'导入参考图 · 自动适配')
            self.reference_character=True
            self.character_summary.setText('使用新导入的参考图。AI 连续动画按完整主体生成；旧版骨骼方式仅适用于人物。')
        elif self.character_loading:
            self.reference_character=bool(self.character_profile and self.character_profile.get('adaptive'))
        size = reader.size()
        if size.width() > 0 and size.height() > 0:
            scale = min(1, 1024 / max(size.width(), size.height()))
            self.width.setValue(max(64, round(size.width() * scale / 8) * 8))
            self.height.setValue(max(64, round(size.height() * scale / 8) * 8))
        self.reference_label.setText('已添加参考图：' + source.name + ' · 后续发送会使用此图，可随时移除。')
        self.show_image(str(target),role='reference')
        if not self.character_loading: self.generation_type_changed()

    def use_current_as_reference(self):
        if self.output:
            try: self.set_reference(self.output)
            except Exception as exc: self.add_chat('软件', '读取参考图失败：' + str(exc))

    def clear_reference(self):
        self.reference_path = None
        self.reference_display_name = None
        self.reference_character=False
        self.animation_source.setCurrentIndex(1)
        if self.character_profile or self.custom_graph is not None: self.reset_graph()
        if self.preview_role=='reference':
            self.pixmap=QPixmap(); self.output=None; self.preview_path=None; self.preview_role=None
            self.preview.clear(); self.preview.setText(''); self.preview.set_clickable(False)
            self.caption.setText('尚未选择参考图')
        self.reference_label.setText('已移除参考图：仅按文字描述生成，可重新添加参考图。')
        self.generation_type_changed()

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
        raw_negative = r.negative
        r.negative, negative_unmatched = negative_text(raw_negative)
        intent = parse_intent(user_prompt)
        source_graph = self.custom_graph
        pose_key = self.pose_choice.currentData()
        route = self.character_route.currentData()
        adaptive_action=None
        pose_unavailable=False
        object_info=getattr(self,'info',{}).get('object_info',{})
        pose_choices=object_info.get('ControlNetLoader',{}).get('input',{}).get('required',{}).get('control_net_name',[[]])[0]
        pose_model=(self.character_profile or {}).get('pose_requires','controlnet-openpose-sdxl-1.0-xinsir.safetensors')
        pose_available=pose_model in pose_choices
        if self.character_profile and route=='pose' and not pose_available:
            raise ValueError('骨骼约束需要模型：'+pose_model+'。可切换为参考重绘或 AI 连续动画。')
        adaptive_reference=bool(reference_name and (self.reference_character or (self.character_profile and self.character_profile.get('adaptive'))))
        if adaptive_reference:
            from .reference_analysis import REFERENCE_POSITIVE
            r.positive=REFERENCE_POSITIVE+(', '+intent.english if intent.english else '')
            if intent.action in ('stand','reach','walk') and pose_available and 'DWPreprocessor' in getattr(self,'info',{}).get('nodes',[]):
                from .walk_cycle import frame_workflow
                adaptive_action=intent.action
                pose_key='reach' if intent.action=='reach' else 'stand'; route='pose'
                r.width=768; r.height=1024
                self.width.setValue(768); self.height.setValue(1024)
                source_graph=frame_workflow(reference_name,'__adaptive_pose__','__adaptive_guide__',seed,r.positive,r.checkpoint,r.steps,r.negative)
            else:
                from .character_profile import character_workflow
                source_graph=character_workflow(reference_name); route='baseline'
                pose_unavailable=intent.action in ('stand','reach','walk')
        elif self.character_profile:
            if intent.action in ('stand','reach','walk') and pose_available:
                pose_key = 'reach' if intent.action == 'reach' else 'stand'
                route = 'pose'
                if intent.action == 'walk':
                    from .walk_cycle import walk_rig
                    from .character_profile import paint_pose
                    pose_path = DATA/'characters'/'blue_side_v3'/'poses'/'walk_contact.png'
                    paint_pose(walk_rig(0)).save(str(pose_path))
                else: pose_path = Path(self.character_profile['poses'][pose_key]['image'])
                source_graph = json.loads(Path(self.character_profile['poses'][pose_key]['graph']).read_text('utf-8'))
                # Uploaded during preparation along with the identity reference.
                source_graph['21']['inputs']['image'] = '__aipictures_pose__'
            elif intent.action in ('stand','reach','walk') and route=='baseline':
                pose_unavailable=True
                source_graph=json.loads(Path(self.character_profile['baseline_graph']).read_text('utf-8'))
            key = 'positive' if route == 'baseline' else 'pose_positive'
            r.positive = self.character_profile[key] + ('\nAdditional target: ' + intent.english if intent.english else '')
        elif intent.english:
            r.positive = intent.english
        elif intent.unmatched:
            raise ValueError('这些中文暂未识别：'+intent.unmatched+'。当前支持站立、伸手、走路及侧视等动作词；其他画面描述请补充英文。')
        if not r.positive.strip():
            if reference_name: r.positive = 'high quality, detailed image'
            else: raise ValueError('请先输入画面描述，或添加一张参考图。')
        r.positive,lora_info=style_prompt(r.positive,r.lora)
        if any(v % 8 for v in (r.width, r.height)): raise ValueError('宽高需为 8 的倍数')
        graph = source_graph if source_graph is not None else build_workflow(r)
        graph, mapping = bind_request(graph, r, reference_name, self.denoise.value())
        from .image_quality import append_quality
        quality=self.quality_mode.currentData()
        append_quality(graph,quality,r.width,r.height)
        params = asdict(r)
        params.update(mode='chat', user_prompt=user_prompt, template=self.active_title, bindings=mapping, denoise=self.denoise.value())
        params['intent'] = intent.to_dict()
        params['lora_style']=lora_info
        params.update(quality_mode=quality,edge_smoothing=(entry_for(r.lora) or {}).get('quality')!='pixel')
        params.update(user_negative=raw_negative, negative_unmatched=negative_unmatched)
        if pose_unavailable: params['pose_fallback']='optional_pose_model_unavailable'
        if adaptive_action: params['adaptive_action']=adaptive_action
        if self.character_profile and not adaptive_reference and intent.action in ('stand','reach','walk') and not pose_unavailable:
            params['pose_upload'] = str(pose_path)
        if self.character_profile and self.character_profile.get('adaptive'):
            params['prepared_reference']=self.character_profile['analysis']['opaque']
        if self.character_profile and intent.direction == 'left':
            params['mirror_output'] = True
        if self.character_profile:
            params.update(character_id=self.character_profile['id'], rig_id='blue_side_right_v3',
                          pose=pose_key, character_route=route)
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
            if self.generation_type.currentData() == 'walk':
                self.enqueue_walk(); return
            reference = self.reference_path
            graph, params = self.graph_snapshot('__aipictures_reference__' if reference else '')
            if not reference and params['bindings']['reference']:
                raise ValueError('此工作流需要参考图。请主动添加一张图，或恢复自动工作流进行纯文字生成。')
            from .image_quality import check_quality_models
            check_quality_models(self.info['object_info'],params['quality_mode'])
            from .background import model_file
            if not model_file().is_file(): raise ValueError('透明输出需要本地去背景模型，请先运行 setup.bat 安装。')
            check_models(graph, self.info['object_info'])
            params['reference'] = str(reference) if reference else None
            fallback = '按角色基准生成' if self.character_profile else '使用这张参考图生成'
            self.add_chat('你', params['user_prompt'].strip() or fallback, str(reference) if reference else None)
            if params['intent']['unmatched']:
                self.add_chat('软件','未识别的中文暂未写入模型提示词：'+params['intent']['unmatched'])
            if params['negative_unmatched']:
                self.add_chat('软件','部分反向中文没有词表映射，已保留原文：'+params['negative_unmatched'])
            if params.get('pose_fallback'):
                self.add_chat('软件','可选姿态模型当前不可用，本次按参考图重绘。')
            if reference:
                self.preparing = True; self.prepare_cancel.clear()
                self.status.setText('正在准备并上传参考图…')
                self.generate_button.setEnabled(False); self.connect_button.setEnabled(False); self.workflow_selector.setEnabled(False)
                client = self.client
                def uploaded(kind, data):
                    if kind=='reference_stage': self.status.setText(data['message']); return
                    if kind not in ('result','error','cancelled'): return
                    self.preparing = False
                    self.generate_button.setEnabled(self.connected); self.connect_button.setEnabled(self.current is None)
                    self.workflow_selector.setEnabled(self.generation_type.currentData()!='walk')
                    if self.prepare_cancel.is_set():
                        self.status.setText('生成准备已取消'); self.add_chat('软件', '本次生成准备已取消。'); return
                    if kind == 'error':
                        self.status.setText('参考图准备失败'); self.add_chat('软件', '参考图识别或上传失败：' + str(data)); return
                    if kind != 'result': return
                    if data.get('fallback_graph'):
                        graph.clear(); graph.update(data['fallback_graph']); params['bindings']=bindings(graph)
                        params['pose_fallback']=data['pose_fallback']; params.pop('adaptive_action',None)
                        self.add_chat('软件','这张图未适用人体骨骼，本次按参考主体重绘，不强行套用人体姿态。')
                    for key in params['bindings']['reference']: graph[key]['inputs']['image'] = data['reference']
                    if data.get('pose'): graph['21']['inputs']['image'] = data['pose']
                    if data.get('guide'): graph['30']['inputs']['image'] = data['guide']
                    if data.get('analysis'): params['reference_analysis']=data['analysis']
                    params['uploaded_reference'] = data['reference']
                    self.submit_chat_graph(graph, params)
                def prepare(emit):
                    from .reference_analysis import prepare_reference,action_rig,opaque_reference,PoseNotApplicable
                    from PIL import Image,ImageOps
                    result={}
                    if params.get('adaptive_action'):
                        from .character_profile import paint_pose
                        from .skin_warp import AdaptiveCutout
                        try:
                            analysis=prepare_reference(reference,client,emit,self.prepare_cancel)
                        except PoseNotApplicable as exc:
                            from .character_profile import character_workflow
                            from .temporal_animation import prepare_subject
                            staging=DATA/'references'/(uuid4().hex+'_subject'); staging.mkdir()
                            prepare_subject(reference,staging/'reference_rgb.png',self.prepare_cancel)
                            request=ImageRequest(**{field:params[field] for field in ImageRequest.__dataclass_fields__})
                            fallback,_=bind_request(character_workflow('__reference__'),request,'__reference__',params['denoise'])
                            from .image_quality import append_quality
                            append_quality(fallback,params.get('quality_mode','off'),request.width,request.height)
                            return {'reference':client.upload_image(staging/'reference_rgb.png'),
                                    'fallback_graph':fallback,'pose_fallback':str(exc)}
                        base=json.loads(Path(analysis['rig']).read_text('utf-8'))
                        rig=action_rig(base,params['adaptive_action'])
                        staging=DATA/'references'/(uuid4().hex+'_pose'); staging.mkdir()
                        paint_pose(rig).save(str(staging/'pose.png'))
                        if params['adaptive_action']=='stand':
                            shutil.copy2(analysis['opaque'],staging/'guide.png')
                        else:
                            guide,_,_=AdaptiveCutout(analysis).render(rig); guide.save(staging/'guide.png')
                        result.update(reference=client.upload_image(analysis['opaque']),pose=client.upload_image(staging/'pose.png'),
                                      guide=client.upload_image(staging/'guide.png'),analysis=analysis)
                    else:
                        selected=params.get('prepared_reference') or reference
                        with Image.open(selected) as image:
                            image=ImageOps.exif_transpose(image).convert('RGBA')
                            opaque=opaque_reference(image)
                        prepared=DATA/'references'/(uuid4().hex+'_rgb.png'); opaque.save(prepared)
                        result['reference']=client.upload_image(prepared)
                    if self.prepare_cancel.is_set(): raise Cancelled('准备已取消')
                    if params.get('pose_upload'): result['pose'] = client.upload_image(params['pose_upload'])
                    return result
                self.launch(prepare, uploaded)
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
        if params.get('mode') == 'walk':
            self.start_walk(params,folder,item); return
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
                self.status.setText(f'生成进度 {data["value"]} / {data["max"]}')
            elif kind == 'executing':
                self.status.setText('正在执行节点 ' + str(data.get('node') or '结果保存'))
            elif kind == 'monitor_waiting':
                self.status.setText('本地引擎繁忙，继续等待当前任务…')
            elif kind == 'postprocess':
                self.status.setText('正在本地分离主体并生成透明背景…')
            elif kind in ('result', 'error', 'cancelled'):
                if kind == 'result':
                    if params.get('mirror_output'):
                        from PIL import Image, ImageOps
                        for path in data['images']:
                            with Image.open(path) as image: mirrored = ImageOps.mirror(image)
                            mirrored.save(path)
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
        def generate(emit):
            from .background import process_result
            result=self.client.generate(graph,folder,emit,cancel)
            return process_result(result,folder,emit,cancel,params.get('edge_smoothing',True))
        self.launch(generate, event)

    def enqueue_walk(self):
        from .walk_cycle import new_sequence, frame_workflow
        profile = self.character_profile
        engine=self.animation_engine.currentData()
        reference=self.reference_path if self.animation_source.currentData()=='reference' else None
        if not reference and self.animation_source.currentData()=='reference': raise ValueError('请添加参考图，或将角色来源切换为“仅文字描述”。')
        if not reference and not self.positive.toPlainText().strip(): raise ValueError('文字模式请先描述角色外观。')
        if not profile: profile={'reference':str(reference) if reference else None}
        seed = int(self.seed.text())
        if seed == -1: seed = secrets.randbelow(2**53)
        if not 0 <= seed < 2**64: raise ValueError('种子范围不正确')
        if engine=='wan':
            from .temporal_animation import check_video_models
            from .background import model_file
            from .image_quality import check_quality_models
            check_video_models(self.info['object_info'])
            check_quality_models(self.info['object_info'],self.quality_mode.currentData())
            if reference is None: validate_selection(self.lora.currentData() or '',self.model.currentText())
            if not model_file().is_file(): raise ValueError('透明动画需要本地去背景模型，请先运行 setup.bat。')
        else:
            if not reference: raise ValueError('旧版骨骼流程需要人物参考图；仅文字模式请选择 AI 连续动画。')
            if 'DWPreprocessor' not in self.info['nodes']: raise ValueError('旧版人体骨骼适配需要本地 DWPose 节点。')
            graph = frame_workflow('__ref__','__pose__','__guide__',seed,'walk',self.model.currentText(),self.steps.value(),self.negative.toPlainText())
            missing = {node['class_type'] for node in graph.values()}-set(self.info['nodes'])
            if missing: raise ValueError('缺少节点：'+', '.join(sorted(missing)))
            check_models(graph,self.info['object_info'])
        folder = new_sequence()
        params = {'mode':'walk','engine':engine,'source':self.animation_source.currentData(),'profile':profile if engine=='rig' else None,
                  'reference':str(reference) if reference else None,'prompt':self.positive.toPlainText(),
                  'checkpoint':self.model.currentText(),'seed':seed,'count':self.walk_count.currentData(),
                  'fps':self.walk_fps.value(),'steps':self.animation_steps.value() if engine=='wan' else self.steps.value(),
                  'negative':self.negative.toPlainText(),
                  'lora':(self.lora.currentData() or '') if engine=='wan' and reference is None else '',
                  'lora_strength':self.strength.value(),'quality_mode':self.quality_mode.currentData()}
        write_json(folder/'job.json',{'schema_version':1,'kind':'walk','status':'queued','params':params})
        item = QListWidgetItem(folder.name+' · 行走动画 · 等待'); self.queue_list.addItem(item)
        self.pending.append((None,params,folder,item))
        self.add_chat('你',params['prompt'] or '按参考图生成走路动画')
        detail=('Wan2.2 整段连续推理，不依赖人体关节识别。' if engine=='wan' else '旧版人体分层与关节局部修复。')
        self.add_chat('软件',f'已选择走路动画：{params["count"]} 帧。'+detail,job=str(folder))
        self.start_next()

    def start_walk(self, params, folder, item):
        from .walk_cycle import generate_walk
        cancel = threading.Event(); self.current={'folder':folder,'cancel':cancel,'params':params}
        self.connect_button.setEnabled(False); self.progress.setRange(0,100); self.progress.setValue(0)
        item.setText(folder.name+' · 行走动画执行中')
        temporal=params.get('engine')=='wan'
        self.status.setText('准备参考主体与连续动画…' if temporal else '准备行走骨骼与角色分层…')
        write_json(folder/'job.json',{'schema_version':1,'kind':'walk','status':'running','params':params})
        def event(kind,data):
            if kind == 'reference_stage': self.status.setText(data['message'])
            elif kind=='quality_event':
                if data['event']=='queued': self.current['prompt_id']=data['data']['prompt_id']
                self.status.setText('正在进行手动选择的高清修复…')
            elif kind in ('video_event','character_event'):
                stage='连续动画' if kind=='video_event' else '角色图片'
                if data['event']=='progress':
                    if kind=='video_event': stage='细节完善' if self.current.get('video_expert',0) else '动作生成'
                    step=data['data']; self.status.setText(f'{stage}推理 {step["value"]}/{step["max"]}')
                    fraction=step['value']/max(1,step['max'])
                    offset=10 if params.get('source')=='text' else 0
                    if kind=='character_event': value=10*fraction
                    else: value=offset+(80-offset)*(self.current.get('video_expert',0)+fraction)/2
                    self.progress.setValue(max(self.progress.value(),round(value)))
                elif data['event']=='queued': self.current['prompt_id']=data['data']['prompt_id']
                elif data['event']=='executing':
                    node=str(data['data'].get('node') or '')
                    if kind=='video_event' and node in ('11','12'): self.current['video_expert']=int(node=='12')
                    labels={'1':'加载模型','2':'加载模型','3':'处理描述','4':'准备图像',
                        '5':'处理描述','6':'处理描述','7':'读取参考','8':'准备连续帧',
                        '9':'准备推理','10':'准备推理','11':'动作生成','12':'细节完善',
                        '13':'解码连续帧','14':'保存连续帧'} if kind=='video_event' else {
                        '1':'加载模型','2':'处理描述','3':'处理描述','4':'准备画布','5':'绘制角色','6':'解码图片','7':'保存图片'}
                    self.status.setText(stage+' · '+labels.get(node,'保存结果'))
            elif kind=='matte_progress':
                self.progress.setValue(round(80+15*data['value']/max(1,data['max'])))
            elif kind == 'frame_started':
                self.status.setText(f'行走第 {data["index"]+1}/{data["count"]} 帧 · {data["stage"]}')
            elif kind == 'frame_event':
                if data['event'] == 'progress':
                    step=data['data']; self.status.setText(f'第 {data["index"]+1}/{data["count"]} 帧 · 采样 {step["value"]}/{step["max"]}')
            elif kind == 'frame_ready':
                fraction=(data['index']+1)/data['count']
                self.progress.setValue(round(95+4*fraction) if temporal else round(fraction*100))
                self.show_image(data['image'], allow_zoom=False)
            elif kind in ('result','error','cancelled'):
                status={'result':'completed','error':'failed','cancelled':'cancelled'}[kind]
                write_json(folder/'job.json',{'schema_version':1,'kind':'walk','status':status,'params':params,
                                            'result':data if kind=='result' else None,'error':None if kind=='result' else str(data)})
                if kind == 'result':
                    self.animation_player.load(data['manifest']); self.load_gallery()
                    last=Path(data.get('workflow') or folder/f'frame_{params["count"]-1:03d}'/'workflow.json')
                    self.last_chat_graph=json.loads(last.read_text('utf-8')); self.editor_needs_sync=True; self.sync_editor_if_needed()
                    message='行走序列已完成，可循环播放、逐帧查看或导出 PNG / Sprite Sheet / GIF。'
                else: message=('行走任务已取消。' if kind=='cancelled' else '行走生成失败：'+str(data))+' 已完成的帧保留在本地。'
                self.add_chat('软件',message,job=str(folder)); self.log.append(folder.name+' · '+status)
                if kind=='result': self.progress.setValue(100)
                item.setText(folder.name+' · 行走动画 · '+status); self.status.setText(message)
                self.current=None; self.connect_button.setEnabled(True); QTimer.singleShot(0,self.start_next)
        if params.get('engine')=='wan':
            from .temporal_animation import generate_temporal
            self.launch(lambda emit:generate_temporal(self.client,folder,params['prompt'],params['negative'],
                params['seed'],params['count'],params['fps'],emit,cancel,params['reference'],params['checkpoint'],params['steps'],
                params.get('lora',''),params.get('lora_strength',.8),params.get('quality_mode','off')),event)
        else:
            self.launch(lambda emit:generate_walk(self.client,folder,params['profile'],params['prompt'],params['checkpoint'],
                params['seed'],params['count'],params['fps'],emit,cancel,params['steps'],params['negative'],params['reference']),event)

    def update_job(self, status, error=None):
        if self.current:
            write_json(self.current['folder'] / 'job.json', {'schema_version': 1, 'kind': 'image',
                'status': status, 'params': self.current['params'], 'prompt_id': self.current.get('prompt_id'), 'error': error})

    def cancel_current(self):
        if self.current: self.current['cancel'].set(); self.status.setText('正在请求取消本任务…')
        elif self.preparing: self.prepare_cancel.set(); self.status.setText('正在取消生成准备…')

    def clear_pending(self):
        for _, params, folder, item in self.pending:
            write_json(folder / 'job.json', {'schema_version': 1, 'kind': 'walk' if params.get('mode')=='walk' else 'image', 'status': 'cancelled', 'params': params})
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
        for folder in self.cache_store.entries('image'):
            images=sorted(folder.glob('image_*.png'))
            for path in images or [None]:
                item = QListWidgetItem(folder.name + ' · '+(path.name if path else '尚无图片')+' · 缓存')
                item.setData(Qt.ItemDataRole.UserRole, str(path) if path else None)
                item.setData(Qt.ItemDataRole.UserRole+1,str(folder)); item.setToolTip(str(folder)); self.gallery.addItem(item)
        self.assets_dialog.animations.clear()
        for folder in self.cache_store.entries('walk'):
            path=folder/'sequence.json'
            try: sequence=json.loads(path.read_text('utf-8')) if path.exists() else {'frames':[],'status':'queued'}
            except (OSError,ValueError): sequence={'frames':[],'status':'unreadable'}
            item=QListWidgetItem(folder.name+' · '+str(len(sequence['frames']))+' 帧 · '+sequence['status'])
            item.setData(Qt.ItemDataRole.UserRole,str(path)); item.setData(Qt.ItemDataRole.UserRole+1,str(folder))
            self.assets_dialog.animations.addItem(item)
        self.assets_dialog.saved_files.clear()
        try:
            for entry in reversed(self.cache_store.saved_files()):
                exists=Path(entry['path']).is_file()
                item=QListWidgetItem(Path(entry['path']).name+('' if exists else ' · 文件已移动或删除'))
                item.setData(Qt.ItemDataRole.UserRole,entry['path']); item.setToolTip(entry['path'])
                self.assets_dialog.saved_files.addItem(item)
        except (OSError,ValueError,KeyError) as exc: self.log.append('读取已保存文件记录失败：'+str(exc))

    def clear_result_cache(self,kind,all_cached=False):
        if self.cache_busy: return
        listing=self.gallery if kind=='image' else self.assets_dialog.animations
        folders=self.cache_store.entries(kind) if all_cached else [item.data(Qt.ItemDataRole.UserRole+1) for item in listing.selectedItems()]
        if not folders:
            self.assets_dialog.cache_status.setText('暂无可清理缓存。' if all_cached else '请先选中要清除的记录。'); return
        protected=[entry[2] for entry in self.pending]
        if self.current: protected.append(self.current['folder'])
        self.cache_busy=True; self.assets_dialog.set_cache_busy(True)
        self.assets_dialog.cache_status.setText('正在清理本地缓存…')
        # Pause a cached sequence before the worker removes its frame files.
        if self.animation_player.manifest and within_any(self.animation_player.manifest,folders):
            if self.animation_player.timer.isActive(): self.animation_player.toggle()
        def done(event,data):
            if event not in ('result','error'): return
            self.cache_busy=False; self.assets_dialog.set_cache_busy(False)
            if event=='error': self.assets_dialog.cache_status.setText('清理失败：'+str(data)); return
            removed=data['deleted']
            if self.image_viewer and within_any(self.image_viewer.source_path,removed): self.image_viewer.close()
            if within_any(self.output,removed) or within_any(self.animation_player.manifest,removed):
                self.animation_player.reset(); self.sequence_preview.clear_sequence()
                self.output=None; self.pixmap=QPixmap(); self.preview.clear(); self.preview.setText('缓存已清除，可继续生成或打开已保存文件。')
                self.preview_path=None; self.preview_role=None
                self.preview.set_clickable(False)
                self.caption.setText('未另存的生成结果保存在本地缓存')
            for message in self.chat_messages:
                for field in ('image','job'):
                    if within_any(message.get(field),removed): message[field]=None
            self.chat.clear()
            for message in self.chat_messages: self.render_message(message)
            self.load_gallery()
            text=f'已清除 {len(removed)} 个任务缓存；跳过 {len(data["skipped"])} 个正在运行或排队的任务。已另存文件保留。'
            if data['errors']: text+=f' {len(data["errors"])} 项清理失败，详见日志。'; self.log.append('\n'.join(data['errors']))
            self.assets_dialog.cache_status.setText(text); self.add_chat('软件',text)
        store=self.cache_store
        self.launch(lambda _:store.clear(folders,protected),done)

    def open_animation_history(self,item):
        try:
            self.animation_player.load(item.data(Qt.ItemDataRole.UserRole)); self.assets_dialog.close()
        except (OSError,ValueError,KeyError) as exc: self.add_chat('软件','读取动画失败：'+str(exc))

    def open_history(self, item):
        path=item.data(Qt.ItemDataRole.UserRole)
        if not path:
            self.assets_dialog.cache_status.setText('此任务尚无可预览的图片。'); return
        self.show_image(path)
        self.assets_dialog.close()

    def show_image(self, path, allow_zoom=True,role='result'):
        self.animation_player.stop()
        self.sequence_preview.clear_sequence()
        self.pixmap = QPixmap(path); self.output = path if role=='result' else None
        self.preview_path=path; self.preview_role=role
        self.preview.set_clickable(allow_zoom and not self.pixmap.isNull() and Path(path).suffix.lower() != '.gif')
        self.caption.setText(('参考图 · ' if role=='reference' else '本地图片 · ') + Path(path).name); self.fit_preview()

    def open_current_image(self):
        if self.preview.clickable and self.preview_path: self.open_image_viewer(self.preview_path)

    def open_image_viewer(self, path):
        if not path: return
        try:
            if self.image_viewer is None:
                from .image_viewer import ImageViewer
                self.image_viewer = ImageViewer(self)
            self.image_viewer.open_image(path)
        except (OSError, ValueError) as exc:
            self.add_chat('软件', '打开图片失败：' + str(exc))

    def fit_preview(self):
        if not self.pixmap.isNull():
            ratio=self.preview.devicePixelRatioF()
            scaled=self.pixmap.scaled(self.preview.size()*ratio,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(ratio); self.preview.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'preview'): self.fit_preview()

    def save_as(self):
        if not self.output: return
        if self.cache_busy: self.status.setText('请等待缓存清理结束后再保存。'); return
        path, _ = QFileDialog.getSaveFileName(self, '另存图片', 'image.png', 'PNG (*.png)')
        if path:
            try:
                target=self.cache_store.validate_export(path)
                if target != Path(self.output).resolve(): shutil.copy2(self.output,target)
                self.cache_store.record_save(target,'image',self.output); self.load_gallery()
                self.add_chat('软件','图片已另存，清理缓存时会保留：'+str(target))
            except (OSError,ValueError,KeyError) as exc: QMessageBox.warning(self, '保存失败', str(exc))

    def closeEvent(self, event):
        if self.current or self.workers or self.editor.pending or self.preparing:
            self.status.setText('后台操作尚未结束，请先取消任务并稍候，再关闭窗口。')
            self.log.append('请先取消任务并等待后台操作结束，再关闭窗口。'); event.ignore(); return
        self.clear_pending(); event.accept()


def create_application(args=None):
    app = QApplication(sys.argv if args is None else args)
    from .theme import apply_light_theme
    apply_light_theme(app)
    return app


def main():
    app = create_application()
    window = Window(); window.show()
    sys.exit(app.exec())


if __name__ == '__main__': main()
