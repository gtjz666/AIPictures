import json
import secrets
import shutil
import sys
import threading
import html
from uuid import uuid4
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QPixmap, QImageReader
from PySide6.QtWidgets import QApplication, QMainWindow, QSpinBox, QListWidgetItem, QFileDialog, QMessageBox,QDialog
from .engine import ComfyClient, Cancelled, is_engine_unavailable
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
from .animation_actions import ACTIONS
from .task_display import task_name
from .background_worker import Worker


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AlI')
        self.resize(1440, 940)
        self.workers = []
        self._closing = False
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
        self.connecting = False
        self.engine_starting = False
        self.character_profile = None
        self.character_loading = False
        self.reference_modes={'image':'redraw','walk':'preserve'}
        self.reference_mode='image'
        self.cache_store=ResultCache(DATA); self.cache_busy=False
        from .api_controller import ApiController
        self.api_controller = ApiController(self, DATA)
        from .studio_layout import build_studio
        build_studio(self)
        self.h3_image_controller.restore_choice()
        config = DATA / 'settings.json'
        if config.exists():
            try: self.url.setText(json.loads(config.read_text('utf-8'))['url'])
            except (ValueError, KeyError): pass
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_stats); self.timer.start(5000)
        self.stats_busy = False
        self.load_gallery()
        self.restore_chat()
        self.api_controller.apply_mode()
        from .gpu_watch_ui import attach
        attach(self)
        QTimer.singleShot(200, self.auto_connect_engine)

    def auto_connect_engine(self):
        if not self.api_controller.cloud:
            self.connect_engine()

    @staticmethod
    def spin(minimum, maximum, value, step=1):
        w = QSpinBox(); w.setRange(minimum, maximum); w.setValue(value); w.setSingleStep(step); return w

    def launch(self, action, callback):
        if self._closing:return
        worker = Worker(action); self.workers.append(worker)
        worker.event.connect(lambda kind,data:callback(kind,data) if not self._closing else None)
        worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.finished.connect(worker.deleteLater); worker.start()

    def refresh_loras(self):
        self.lora.clear();self.lora.addItem('不使用 LoRA','');self.update_lora_state()

    def lora_changed(self):
        self.update_lora_state()

    def update_lora_state(self):
        for name in ('lora','lora_category','strength','lora_details'):
            control=getattr(self,name,None)
            if control is not None:control.hide();control.setEnabled(False)
        if hasattr(self,'style_status'):self.style_status.setText('画风与细节由提示词和参考图控制')

    def disconnect_engine(self, message):
        self.connected=False
        self.editor.set_ready(False)
        self.editor.connection_label.setText('引擎已断开 · 重新连接后生成与工作流共用同一服务')
        self.generate_button.setEnabled(False); self.workflow_selector.setEnabled(False)
        self.connect_button.setEnabled(True)
        self.gpu.setText('引擎未连接 · 可启动本地引擎后重试')
        self.status.setText(message)
        self.status.setToolTip(message)
        for _,params,folder,item in self.pending:
            if params.get('backend')!='api': item.setText(task_name(params)+' · 等待重新连接')
        self.api_controller.apply_mode()

    def start_engine(self):
        if self.current or self.preparing or self.connecting or self.engine_starting:
            self.status.setText('请等待当前后台操作结束，再启动或重连。'); return
        self.engine_starting=True
        self.start_engine_button.setEnabled(False); self.reconnect_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        from .engine_service import start_local_engine
        def done(kind,data):
            if kind=='starting': self.status.setText(data); return
            self.engine_starting=False
            self.start_engine_button.setEnabled(True); self.reconnect_button.setEnabled(True)
            self.connect_button.setEnabled(True)
            if kind=='error':
                self.disconnect_engine(str(data)); self.log.append(str(data)); return
            if kind=='result':
                self.url.setText(data)
                self.connect_engine()
        url=self.url.text().strip()
        self.launch(lambda emit:start_local_engine(url,emit),done)

    def connect_engine(self):
        if self.current or self.preparing or self.connecting or self.engine_starting:
            self.log.append('请等待任务结束后更换连接。'); return
        if self.pending and getattr(self,'client',None) and self.url.text().rstrip('/')!=self.client.url:
            self.status.setText('队列尚有任务，请先清空队列再更换地址。'); return
        self.connected = False; self.generate_button.setEnabled(False); self.connect_button.setEnabled(False); self.workflow_selector.setEnabled(False)
        try: requested = ComfyClient(self.url.text()).url
        except Exception as exc:
            self.disconnect_engine(str(exc)); self.log.append(str(exc)); return
        self.connecting=True
        self.status.setText('正在检测 ComfyUI 和模型…')
        def done(kind, data):
            self.connecting=False
            self.connect_button.setEnabled(True)
            if kind == 'error':
                self.disconnect_engine('引擎未连接：请点击“启动 / 重连”。'); self.log.append(data); return
            if kind != 'result': return
            client,data=data
            self.client = client; self.info = data; self.connected = True
            self.url.setText(client.url)
            self.editor.set_node_info(data['object_info'])
            profile = load_profile()
            required_pose = profile['pose_requires'] if profile else 'controlnet-openpose-sdxl-1.0-xinsir.safetensors'
            pose_weights = data['object_info'].get('ControlNetLoader', {}).get('input', {}).get('required', {}).get('control_net_name', [[]])[0]
            self.character_route.setItemText(1, '骨骼约束 · 已识别' if required_pose in pose_weights else '骨骼约束 · 缺权重')
            previous_model=self.model.currentText(); previous_sampler=self.sampler.currentText() or 'dpmpp_2m'
            previous_scheduler=self.scheduler.currentText() or 'karras'
            self.model.clear(); self.model.addItems(data['checkpoints'])
            if self.model.findText(previous_model)>=0: self.model.setCurrentText(previous_model)
            elif not previous_model:
                preferred=next((name for name in data['checkpoints'] if 'Juggernaut-XL_v9_' in name),None)
                if preferred: self.model.setCurrentText(preferred)
            self.refresh_loras()
            self.sampler.clear(); self.sampler.addItems(data['samplers'])
            self.scheduler.clear(); self.scheduler.addItems(data['schedulers'])
            if self.sampler.findText(previous_sampler)>=0: self.sampler.setCurrentText(previous_sampler)
            if self.scheduler.findText(previous_scheduler)>=0: self.scheduler.setCurrentText(previous_scheduler)
            self.generate_button.setEnabled(True)
            from .image_family import restore
            restore(self)
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
                            self.activate_template(preset['graph'], preset['title'], preset.get('entry_id'),preserve_prompts=True)
                except (OSError, ValueError, KeyError) as exc: self.log.append('未恢复上次工作流：' + str(exc))
            self.status.setText(f'已连接 {client.url} · 生成与工作流共用此引擎')
            self.status.setToolTip(self.status.text())
            write_json(DATA / 'settings.json', {'url': client.url}); self.refresh_stats()
            self.editor.connect_url(client.url,load=self.tabs.currentIndex()==1)
            self.api_controller.apply_mode()
            QTimer.singleShot(0,self.start_next)
        def discover(_):
            from .backend_connection import shared_backend_url
            # Never move previously queued tasks to a different server.
            target=requested if self.pending else shared_backend_url(requested)
            client=ComfyClient(target)
            return client,client.discover()
        self.launch(discover, done)

    def refresh_stats(self):
        if self.api_controller.cloud: return
        if not self.connected or self.stats_busy or self.current or self.preparing: return
        self.stats_busy = True
        def done(kind, data):
            self.stats_busy = False
            if kind=='error' and is_engine_unavailable(data):
                self.disconnect_engine('本地引擎已断开：请点击“启动 / 重连”。'); self.log.append(data); return
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

    def activate_template(self, graph, title, entry_id=None,preserve_prompts=False):
        if any(n.get('class_type')=='CheckpointLoaderSimple' for n in graph.values()):
            raise ValueError('SDXL普通生成已退役。原工作流文件保留，可在高级编辑器查看；主界面请选择自动工作流。')
        mapping = bindings(graph)
        from .image_family import use_reference_route
        use_reference_route(self,imported=True)
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
        if not preserve_prompts:
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
        if hasattr(self,'workbench'):
            self.workbench.open_settings(key);return
        for name,dialog in self.settings_dialogs.items():
            if name!=key: dialog.hide()
        self.settings_dialogs[key].show_near(self.settings_buttons[key])

    def update_sidebar_summary(self):
        if hasattr(self,'video_controller') and self.generation_type.currentData()=='walk' and self.video_controller.free():
            self.video_controller.apply_ui();return
        if self.api_controller.cloud:
            self.api_controller.apply_mode(); return
        walking=self.generation_type.currentData()=='walk'
        text=(ACTIONS[self.animation_action.currentData()][0]+'动画序列帧' if walking else '单张图片')+'\n'
        if walking:
            free=self.animation_action.currentData()=='custom' and self.custom_strategy.currentData()=='free'
            text+=('AI 自由动作（实验性）' if free else {'wan':'AI 自由动画','animate':'完整骨骼 · '+('自动适配' if self.motion_mode.currentData()=='auto' or self.animation_style.isChecked() else '手动调整'),'rig':'旧版人体骨骼'}[self.animation_engine.currentData()])+'\n'
            text+=f'{self.walk_count.currentData()} 帧 · {self.walk_fps.value()} FPS\n'
            if self.animation_engine.currentData()=='animate' and not free:
                text+=self.animation_detail.currentText()+'\n'
        background='透明主体' if walking or self.output_background.currentData()=='transparent' else '完整画面'
        text+=f'{self.width.value()} × {self.height.value()} · '+background
        self.creation_summary.setText(text)

    def open_skeleton(self):
        self.status.setText('旧骨骼编辑已停用；请用提示词生成完整动画。')

    def open_motion_editor(self):
        self.status.setText('旧骨骼编辑已停用；请用提示词生成完整动画。')

    def character_selection_changed(self, _index=None):
        if self.character_loading: return
        if self.character_profile: self.apply_character()

    def generation_type_changed(self, _index=None):
        walking = self.generation_type.currentData() == 'walk'
        mode='walk' if walking else 'image'
        if mode!=self.reference_mode:
            if mode=='walk':self.single_canvas=(self.width.value(),self.height.value())
            elif hasattr(self,'single_canvas'):
                self.width.setValue(self.single_canvas[0]);self.height.setValue(self.single_canvas[1])
            self.reference_modes[self.reference_mode]=self.reference_policy.currentData()
            self.reference_mode=mode
            self.reference_policy.blockSignals(True)
            self.reference_policy.setCurrentIndex(self.reference_policy.findData(self.reference_modes[mode]))
            self.reference_policy.blockSignals(False)
        self.output_background.setEnabled(not walking)
        self.reference_strength.setEnabled(not walking and bool(self.reference_path) and self.custom_graph is None)
        show_reference_weight=not walking and bool(self.reference_path) and self.model_family.currentData()=='sdxl' and not self.api_controller.cloud
        self.reference_strength.setVisible(show_reference_weight);self.reference_strength_label.setVisible(show_reference_weight)
        show_cfg=not walking and self.model_family.currentData()=='sdxl' and not self.api_controller.cloud
        self.cfg.setVisible(show_cfg);self.cfg_label.setVisible(show_cfg)
        self.walk_settings.setVisible(walking)
        self.animation_action.setVisible(walking)
        self.animation_action_label.setVisible(walking)
        self.translate_prompt.setVisible(not walking and not self.api_controller.cloud)
        action_title=ACTIONS[self.animation_action.currentData()][0]
        custom=self.animation_action.currentData()=='custom'
        free=custom and self.custom_strategy.currentData()=='free'
        self.custom_settings.setVisible(walking and custom)
        self.custom_loop.setVisible(walking and custom and free)
        self.update_custom_hint()
        self.animation_style.setEnabled(walking and self.animation_source.currentData()=='reference')
        self.generate_button.setText('生成动画' if walking else '生成')
        self.positive.setPlaceholderText('描述角色外观和需要保留的细节；动作在上方选择' if walking else
            '描述人物、物件或场景，以及视角、姿势与画风')
        for control in (self.width,self.height,self.denoise,self.cfg,self.lora,self.strength):
            control.setEnabled(not walking)
        if not walking and self.custom_graph is not None:
            self.lora.setEnabled(False); self.strength.setEnabled(False)
        if walking:
            self.width.setValue(768); self.height.setValue(1024)
        self.animation_steps.setEnabled(walking and self.animation_engine.currentData() in ('wan','animate'))
        self.animation_detail.setEnabled(walking and self.animation_engine.currentData()=='animate' and not free)
        self.animation_sampler.setEnabled(walking and self.animation_engine.currentData()=='animate' and not free)
        self.animation_color.setEnabled(walking and self.animation_engine.currentData()=='animate' and not free)
        temporal=walking and self.animation_engine.currentData() in ('wan','animate')
        self.motion_mode.setEnabled(walking and self.animation_engine.currentData()=='animate' and not free and not self.animation_style.isChecked())
        self.model.setEnabled(not temporal or self.animation_source.currentData()=='text' or self.animation_style.isChecked())
        self.steps.setEnabled(not temporal)
        self.sampler.setEnabled(not walking); self.scheduler.setEnabled(not walking)
        self.workflow_selector.setEnabled(not walking and self.connected and not self.preparing)
        self.reference_policy_changed()
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
        self.context_label.setText(action_title+'动画' if walking else
                                   '图片创作' if self.active_title=='自动选择' else self.active_title)
        self.update_intent_hint()
        self.update_sidebar_summary()

        if self.api_controller.cloud: self.api_controller.apply_mode()
        else:
            from .image_family import apply_ui
            apply_ui(self)
        if hasattr(self,'video_controller'):self.video_controller.apply_ui()
        if not walking and hasattr(self,'generation_intent'):self.generate_button.setText('生成图片')

    def preserving_reference(self):
        walking=self.generation_type.currentData()=='walk'
        if not walking and self.model_family.currentData()!='sdxl':return False
        if walking and self.animation_style.isChecked() and self.animation_source.currentData()=='reference':return False
        weighted=walking or self.custom_graph is not None or self.reference_strength.value()>0
        return weighted and bool(self.reference_path) and (not walking or (self.animation_engine.currentData() in ('wan','animate') and self.animation_source.currentData()=='reference')) and self.reference_policy.currentData()=='preserve'

    def update_custom_hint(self):
        if hasattr(self,'video_controller') and self.video_controller.free():
            self.custom_hint.setText('动作描述为准；先生成完整动画，再按需拆帧，不需要调整骨骼。');return
        if self.custom_strategy.currentData()=='free':
            self.custom_hint.setText('原文直接进入 AI 动作模型，不使用静态骨骼；复杂接触、动作完成度和循环仍需检查。');return
        try:
            from .motion_language import parse_plan
            plan=parse_plan(self.custom_description.toPlainText())
            self.custom_hint.setText('识别顺序：'+' → '.join(s['title'] for s in plan['segments'])+'。秒数控制各段占比；最终时长由帧数 / FPS 决定。')
        except ValueError as exc:self.custom_hint.setText(str(exc))

    def reference_policy_changed(self,_index=None):
        from .reference_fidelity import effective_denoise
        preserving=self.preserving_reference()
        walking=self.generation_type.currentData()=='walk'
        legacy=walking and self.animation_engine.currentData()=='rig'
        self.reference_policy.setEnabled(not walking)
        self.reference_policy.setVisible(bool(self.reference_path) and not walking)
        self.reference_policy_label.setVisible(bool(self.reference_path) and not walking)
        self.denoise.setMaximum(.25 if preserving else 1.)
        if preserving: self.denoise.setValue(effective_denoise(self.denoise.value(),True))
        self.denoise.setEnabled(not walking)
        self.quality_mode.setEnabled(not preserving)
        if walking and self.animation_engine.currentData()=='animate':
            self.quality_mode.setEnabled(False)
            self.quality_mode.setToolTip('完整动作当前保留源图纹理，不套用生成式高清修复。单张图片可另行高清处理。')
        self.reference_note.setText(('外观以参考图为准；不叠加 LoRA 或高清重画。'+
            ('仅生成所选动作，细节仍可能变化。' if walking else '重绘最高 0.25；大幅改姿势请切换允许重绘。')) if preserving else
            ('旧版骨骼使用网格变形；参考保真策略用于单图与 AI 连续动画。' if legacy else
             ('允许按描述改变外观，可手动使用风格 LoRA 和高清修复。' if self.reference_path and (not walking or self.animation_source.currentData()=='reference') else
              '添加参考图后生效；当前按文字描述生成。')))
        if walking and self.animation_source.currentData()=='reference' and self.animation_style.isChecked():
            self.reference_note.setText('先按所选 LoRA 重绘风格基准，再生成动作。发型、配色和服装细节也可能改变；此模式使用自动骨骼。')
        self.update_lora_state()
        self.update_intent_hint()

    def update_intent_hint(self):
        if hasattr(self,'video_controller') and self.generation_type.currentData()=='walk' and self.video_controller.free():
            self.intent_hint.setText('画面与动作统一填写正向提示词；完整动画循环预览，自主选帧导出。');return
        if self.api_controller.cloud:
            self.api_controller.apply_mode(); return
        walking = self.generation_type.currentData() == 'walk'
        if walking:
            from .action_intent import has_pose_conflict
            if has_pose_conflict(self.positive.toPlainText(),self.animation_action.currentData()):
                self.intent_hint.setText('描述包含其他姿态，当前仍按上方动作预设生成；要按文字改变动作，请选“自定义动作 → AI 自由动作”。')
                return
        if not walking:
            self.intent_hint.setText('单张通用创作 · 视角、主体与背景由你的描述决定。'+
                ('当前是原图小幅修改；更换视角请切换“按描述创作”。' if self.preserving_reference() else ''))
            return
        intent = walk_intent(self.positive.toPlainText()) if walking else parse_intent(self.positive.toPlainText())
        if walking and self.animation_engine.currentData()=='animate': intent.action=self.animation_action.currentData()
        labels = {'walk':'行走','reach':'向前伸手','stand':'站立','run':'奔跑','jump':'横版跳跃','idle':'待机','squat':'下蹲','attack':'基础攻击','custom':'自定义动作'}
        title = labels.get(intent.action,'未指定动作')
        text = ('已选择动画 · ' if walking else '动作识别 · ') + title
        if walking and self.animation_engine.currentData() in ('wan','animate') and (not intent.direction_explicit or self.preserving_reference()):
            text += ' · 朝向沿用参考图'
        elif not walking and not intent.direction_explicit and not self.character_profile:
            text += ' · 朝向未指定'
        else: text += ' · 朝' + ('左' if intent.direction == 'left' else '右')
        if walking and self.animation_engine.currentData()=='animate':
            text+=(' · AI 自由动作（实验性）' if self.animation_action.currentData()=='custom' and self.custom_strategy.currentData()=='free' else
                   ' · 完整骨骼周期 · '+('自动适配，无需手调' if self.motion_mode.currentData()=='auto' or self.animation_style.isChecked() else '使用手动调整'))
        elif intent.action in ('run','jump'): text += '\n连续动作请在动画类型中选择。'
        elif intent.action == 'walk' and not walking: text += '\n当前只生成单张；连续动作请选人物行走动画帧。'
        if walking and self.animation_engine.currentData() in ('wan','animate'):
            text += ' · 外观以参考图为准，文字仅补充步速' if self.preserving_reference() else ' · 中文描述直接送入动画工作流'
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
            self.activate_template(graph, title,preserve_prompts=True)
            self.character_profile = profile
            self.set_reference(profile['reference'])
            self.width.setValue(768); self.height.setValue(1024)
            self.denoise.setValue(.3 if mode == 'baseline' else 1.)
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
        from .image_family import use_reference_route
        use_reference_route(self)
        self.animation_source.setCurrentIndex(0)
        if not self.character_loading and self.character_profile and digest(target)!=self.character_profile['source_sha256']:
            self.reset_graph()
            self.character_summary.setText('使用新导入的参考图；单张图片可生成任意主体或场景。')
        elif self.character_loading:
            self.reference_character=bool(self.character_profile and self.character_profile.get('adaptive'))
        size = reader.size()
        if size.width() > 0 and size.height() > 0:
            scale = min(1, 1024 / max(size.width(), size.height()))
            grid=16 if self.model_family.currentData() in ('auto','flux_klein','qwen_edit','zimage') else 8
            self.width.setValue(max(256 if grid==16 else 64, round(size.width() * scale / grid) * grid))
            self.height.setValue(max(256 if grid==16 else 64, round(size.height() * scale / grid) * grid))
            from .image_family import effective_family
            if effective_family(self)=='h3_image':
                from .h3_image import canvas
                width,height=canvas(size.width(),size.height());self.width.setValue(width);self.height.setValue(height)
        self.reference_label.setText('已添加参考图：' + source.name + ' · 后续发送会使用此图，可随时移除。')
        self.show_image(str(target),role='reference')
        if hasattr(self,'intent_controller'):self.intent_controller.source_changed()
        if not self.character_loading: self.generation_type_changed()
        if hasattr(self,'workbench'):self.workbench.refresh_reference()

    def use_current_as_reference(self):
        if self.output:
            try: self.set_reference(self.output)
            except Exception as exc: self.add_chat('软件', '读取参考图失败：' + str(exc))

    def clear_reference(self):
        self.reference_path = None
        if self.model_family.currentData()=='qwen_edit':
            self.model_family.setCurrentIndex(self.model_family.findData('auto'))
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
        if hasattr(self,'workbench'):
            self.workbench.refresh_reference()
            if self.pixmap.isNull():self.preview.setText('拖入参考素材')

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
        if self.h3_image_controller.active():raise ValueError('H3图片在独立引擎分三阶段运行；生成后可从任务目录查看实际工作流。')
        if hasattr(self,'reference_chat') and self.reference_chat.active():
            return self.reference_chat.snapshot()
        from .image_family import effective_family
        family=effective_family(self,bool(reference_name))
        if family=='flux_klein':
            from .image_family import flux_snapshot
            return flux_snapshot(self,reference_name)
        if family=='qwen_edit':
            from .image_family import reference_snapshot
            return reference_snapshot(self,reference_name)
        if family=='zimage':
            from .image_family import snapshot
            return snapshot(self,reference_name)
        raise ValueError('请选择自动、Z-Image或FLUX；SDXL普通生成已退役。')

    def load_draft_in_editor(self):
        if self.h3_image_controller.active():
            self.status.setText('H3图片使用独立引擎；生成后的编码、采样、解码工作流保存在本次记录。');return
        if hasattr(self,'reference_chat') and self.reference_chat.active():
            self.add_chat('软件','多图参考请生成后从记录查看本次完整工作流。');return
        if self.preparing:
            self.status.setText('请等待当前参考图准备完成。'); return
        try:
            reference=self.reference_path
            graph,params=self.graph_snapshot('__draft_reference__' if reference else '')
            if not reference:
                self.editor.load_graph(graph);return
            # Show the same route as submission, with a real reference upload.
            self.preparing=True;self.prepare_cancel.clear();self.generate_button.setEnabled(False)
            self.status.setText('正在准备工作流参考图…')
            client=self.client
            def prepare(_):
                from PIL import Image,ImageOps
                from .reference_input import opaque_reference
                with Image.open(reference) as source:
                    if params['model_family']=='zimage':
                        from .zimage import prepare_reference
                        rgb=prepare_reference(source,params['width'],params['height'])
                    else:rgb=opaque_reference(ImageOps.exif_transpose(source).convert('RGBA'))
                path=DATA/'references'/(uuid4().hex+'_draft_rgb.png');path.parent.mkdir(parents=True,exist_ok=True)
                rgb.save(path)
                if self.prepare_cancel.is_set():raise Cancelled('工作流准备已取消')
                uploaded=client.upload_image(path)
                if self.prepare_cancel.is_set():raise Cancelled('工作流准备已取消')
                return uploaded
            def done(kind,data):
                if kind not in ('result','error','cancelled'):return
                self.preparing=False;self.generation_type_changed()
                if kind=='result' and not self.prepare_cancel.is_set():
                    for node in params['bindings']['reference']:graph[node]['inputs']['image']=data
                    self.editor.load_graph(graph)
                    self.status.setText('已加载当前参考工作流')
                elif kind=='error':self.editor.report_error({'error':str(data)})
            self.launch(prepare,done)
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
            if hasattr(self,'generation_intent') and self.generation_intent.intercept():return
            if hasattr(self,'audio_controller') and self.workbench.category=='audio':self.audio_controller.enqueue();return
            if hasattr(self,'reference_chat'):
                if self.generation_type.currentData()=='walk' and self.reference_chat.extra and not self.video_controller.motion.path:
                    raise ValueError('多图参考组合用于单张图片。动画目前支持一张角色图与动作素材，请先移除图2–图4。')
                if self.intent_controller.running:return
            from .prompt_language import ensure_for_generation
            if not hasattr(self,'generation_intent'):self.intent_controller.validate_generation()
            if ensure_for_generation(self):return
            if self.h3_image_controller.intercept():return
            if hasattr(self,'reference_chat') and self.reference_chat.intercept():return
            if self.intent_controller.intercept():return
            if self.video_controller.intercept():return
            if self.api_controller.intercept(): return
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
            if params['output_background']=='transparent' and not model_file().is_file():
                raise ValueError('透明输出需要本地去背景模型，请先运行 setup.bat 安装。')
            check_models(graph, self.info['object_info'])
            params['reference'] = str(reference) if reference else None
            fallback = '按角色基准生成' if self.character_profile else '使用这张参考图生成'
            self.add_chat('你', params['user_prompt'].strip() or fallback, str(reference) if reference else None)
            if params['intent']['unmatched'] and params['reference_policy']!='preserve':
                self.add_chat('软件','这些中文已保留原文；当前 SDXL 词表未完整翻译：'+params['intent']['unmatched'])
            if params['negative_unmatched']:
                self.add_chat('软件','部分反向中文没有词表映射，已保留原文：'+params['negative_unmatched'])
            if params.get('pose_fallback'):
                self.add_chat('软件','可选姿态模型当前不可用，本次按参考图重绘。')
            if reference:
                self.preparing = True; self.prepare_cancel.clear()
                show_preparation=self.current is None
                if show_preparation:self.task_display.start();self.progress.setRange(0,0)
                self.status.setText('正在准备并上传参考图…')
                self.generate_button.setEnabled(False); self.connect_button.setEnabled(False); self.workflow_selector.setEnabled(False)
                client = self.client
                def uploaded(kind, data):
                    if kind=='reference_stage': self.status.setText(data['message']); return
                    if kind not in ('result','error','cancelled'): return
                    if show_preparation:self.task_display.finish('cancelled' if self.prepare_cancel.is_set() else 'failed' if kind=='error' else 'completed')
                    self.preparing = False
                    self.generate_button.setEnabled(self.connected); self.connect_button.setEnabled(self.current is None)
                    self.workflow_selector.setEnabled(self.generation_type.currentData()!='walk')
                    if self.prepare_cancel.is_set():
                        self.status.setText('生成准备已取消'); self.add_chat('软件', '本次生成准备已取消。'); return
                    if kind == 'error':
                        if is_engine_unavailable(data): self.disconnect_engine(str(data))
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
                    from .reference_input import opaque_reference
                    from PIL import Image,ImageOps
                    result={}
                    if params.get('adaptive_action'):
                        from .reference_analysis import prepare_reference,action_rig,PoseNotApplicable
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
                        from .generation_reference import prepare_generation_reference
                        preparation=prepare_generation_reference(reference,staging/'reference_rgb.png',analysis)
                        paint_pose(rig).save(str(staging/'pose.png'))
                        if params['adaptive_action']=='stand':
                            shutil.copy2(staging/'reference_rgb.png',staging/'guide.png')
                        else:
                            guide,_,_=AdaptiveCutout(analysis).render(rig); guide.save(staging/'guide.png')
                        result.update(reference=client.upload_image(staging/'reference_rgb.png'),pose=client.upload_image(staging/'pose.png'),
                                      guide=client.upload_image(staging/'guide.png'),analysis=dict(analysis,generation_reference=preparation))
                    else:
                        selected=params.get('prepared_reference') or reference
                        with Image.open(selected) as image:
                            image=ImageOps.exif_transpose(image).convert('RGBA')
                            if params.get('model_family')=='zimage':
                                from .zimage import prepare_reference
                                opaque=prepare_reference(image,params['width'],params['height'])
                            else:opaque=opaque_reference(image)
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
        if hasattr(self,'generation_intent'):self.generation_intent.record(params)
        if not self.connected: raise ValueError('请先连接 ComfyUI')
        from .lora_policy import plain_workflow
        graph = plain_workflow(graph,trained_structure=params.get('reference_policy')=='trained_depth_structure_v1')
        if not graph: raise ValueError('工作流没有可运行节点')
        missing = {n['class_type'] for n in graph.values()} - set(self.info['nodes'])
        if missing: raise ValueError('缺少节点：' + ', '.join(sorted(missing)))
        folder = new_job(graph, params)
        if hasattr(self,'intent_controller'):self.intent_controller.record(folder,params)
        write_json(folder/'job.json', {'schema_version':1, 'kind':'image', 'status':'created', 'params':params})
        if editor_workflow is not None: write_json(folder / 'editor_workflow.json', editor_workflow)
        item = QListWidgetItem(task_name(params) + ' · 等待'); item.setToolTip(str(folder)); self.queue_list.addItem(item)
        self.pending.append((graph, params, folder, item))
        self.start_next()
        return folder

    def start_next(self):
        if self.current or self.preparing or not self.pending: return
        index = next((i for i,job in enumerate(self.pending) if self.connected or
            (job[1].get('mode')=='smart_image' and job[1].get('backend')=='api') or
            (job[1].get('mode') in ('video','audio','h3_image') and job[1].get('backend')=='standalone')),None)
        if index is None: return
        graph, params, folder, item = self.pending.pop(index)
        from .seed_controls import show_seed
        show_seed(self,params.get('seed'))
        if params.get('mode')=='h3_image':self.h3_image_controller.start(params,folder,item);return
        if params.get('mode')=='audio':self.audio_controller.start(params,folder,item);return
        if params.get('mode')=='video':
            self.video_controller.start(params,folder,item);return
        if params.get('mode')=='smart_image':
            self.api_controller.start(graph,params,folder,item); return
        if params.get('mode') == 'walk':
            self.start_walk(params,folder,item); return
        item.setText(task_name(params) + ' · 执行中')
        cancel = threading.Event()
        self.current = {'folder': folder, 'cancel': cancel, 'params': params}
        self.task_display.start()
        self.connect_button.setEnabled(False); self.progress.setRange(0, 0)
        self.status.setText('排队 / 加载模型…'); self.update_job('running')
        def event(kind, data):
            if kind == 'queued':
                self.current['prompt_id'] = data['prompt_id']; self.update_job('queued')
            elif kind == 'progress':
                self.progress.setRange(0,100); self.progress.setValue(round(75*data['value']/max(1,data['max'])))
                self.status.setText(f'生成进度 {data["value"]} / {data["max"]}')
            elif kind == 'executing':
                self.status.setText('正在执行节点 ' + str(data.get('node') or '结果保存'))
            elif kind == 'monitor_waiting':
                self.status.setText('本地引擎繁忙，继续等待当前任务…')
            elif kind == 'postprocess':
                self.progress.setRange(0,100); self.progress.setValue(max(self.progress.value(),85))
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
                self.task_display.finish({'result':'completed','error':'failed','cancelled':'cancelled'}[kind])
                self.log.append(f'{folder.name} · {kind}' + (f'：{data}' if kind != 'result' else ' · 已自动保存'))
                item.setText(task_name(params) + ' · ' + {'result':'完成','error':'失败','cancelled':'取消'}[kind])
                self.status.setText({'result':'生成完成，已保存','error':'任务失败，详见日志','cancelled':'任务已取消'}[kind])
                if kind=='error' and is_engine_unavailable(data): self.disconnect_engine(str(data))
                self.progress.setRange(0, 100); self.progress.setValue(100 if kind == 'result' else 0)
                self.current = None; self.connect_button.setEnabled(True); QTimer.singleShot(0, self.start_next)
        def generate(emit):
            from .general_image import finish_output
            from .engine_service import release_idle_models
            result=self.client.generate(graph,folder,emit,cancel)
            result['inference_cache_release']=release_idle_models(self.client)
            emit('postprocess',{'index':0,'count':len(result['images'])})
            return finish_output(result,folder,emit,cancel,params.get('output_background')=='transparent',params.get('edge_smoothing',True))
        self.launch(generate, event)

    def enqueue_walk(self):
        raise ValueError('旧骨骼与 Wan 路线已停用；请使用 MiniMax H3。')

    def start_walk(self, params, folder, item):
        write_json(folder/'job.json',{'schema_version':1,'kind':'animation','status':'failed','params':params,
            'error':'旧骨骼与 Wan 任务已停用，请用 MiniMax H3 重新创建。'})
        item.setText('旧动画任务 · 已停用')
        self.add_chat('软件','旧骨骼与 Wan 任务已停用，历史成品仍可预览和导出。')
        QTimer.singleShot(0,self.start_next)

    def update_job(self, status, error=None):
        if self.current:
            write_json(self.current['folder'] / 'job.json', {'schema_version': 1, 'kind': 'image',
                'status': status, 'params': self.current['params'], 'prompt_id': self.current.get('prompt_id'), 'error': error,
                'duration_seconds':round(self.task_display.seconds(),2)})

    def cancel_current(self):
        if hasattr(self,'h3_image_controller') and self.h3_image_controller.cancel():return
        if self.intent_controller.cancel():return
        if self.api_controller.cancel(): return
        ticket=self.current
        if ticket:ticket['cancel'].set()
        elif self.preparing:self.prepare_cancel.set()
        else:return
        self.status.setText('正在发送取消请求；后台结束当前计算后停止，可直接关闭窗口。')
        self.progress.setRange(0,0)
        client=ticket.get('client',getattr(self,'client',None)) if ticket else getattr(self,'client',None)
        if client:
            def request(_):
                ids=client.active_prompts()
                if ticket and ticket.get('prompt_id') and ticket['prompt_id'] not in ids:ids.append(ticket['prompt_id'])
                for pid in ids:client.cancel(pid)
                return ids
            def done(kind,data):
                if self.current is ticket and (ticket is not None or self.preparing):
                    self.status.setText('取消请求已发送，等待后台确认停止；可直接关闭窗口。' if kind=='result' else '已记录取消请求，后台暂时未响应；可直接关闭窗口。')
            self.launch(request,done)

    def clear_pending(self):
        for _, params, folder, item in self.pending:
            self.api_controller.runtime.pop(str(folder),None)
            write_json(folder / 'job.json', {'schema_version': 1, 'kind': {'walk':'walk','video':'video','audio':'audio'}.get(params.get('mode'),'image'), 'status': 'cancelled', 'params': params})
            item.setText(task_name(params) + ' · 已清除')
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
        if hasattr(self,'video_controller'):self.video_controller.refresh_history()
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
        listing=self.gallery if kind=='image' else self.assets_dialog.videos if kind=='video' else self.audio_controller.history if kind=='audio' else self.assets_dialog.animations
        folders=self.cache_store.entries(kind) if all_cached else [item.data(Qt.ItemDataRole.UserRole+1) for item in listing.selectedItems()]
        if not folders:
            self.assets_dialog.cache_status.setText('暂无可清理缓存。' if all_cached else '请先选中要清除的记录。'); return
        protected=[entry[2] for entry in self.pending]
        protected.extend(Path(entry[1]['continue_from']).parent for entry in self.pending if entry[1].get('continue_from'))
        if self.current: protected.append(self.current['folder'])
        if self.current and self.current.get('params',{}).get('continue_from'):protected.append(Path(self.current['params']['continue_from']).parent)
        if getattr(self,'importing_folder',None): protected.append(self.importing_folder)
        if getattr(self,'importing_source',None):protected.append(Path(self.importing_source).parent)
        picker=getattr(self,'frame_selection_dialog',None)
        from shiboken6 import isValid
        if picker and isValid(picker) and picker.isVisible():protected.append(getattr(picker,'source_manifest',picker.manifest).parent)
        elif picker:self.frame_selection_dialog=None
        player=getattr(getattr(self,'video_controller',None),'player',None)
        if player and player.manifest and within_any(player.manifest,folders):player.stop()
        audio=getattr(self,'audio_controller',None)
        if audio and within_any(audio.manifest,folders):audio.stop()
        self.cache_busy=True; self.assets_dialog.set_cache_busy(True)
        self.assets_dialog.cache_status.setText('正在清理本地缓存…')
        # Pause a cached sequence before the worker removes its frame files.
        if self.animation_player.manifest and within_any(self.animation_player.manifest,folders):
            if self.animation_player.timer.isActive(): self.animation_player.toggle()
        def done(event,data):
            if event not in ('result','error'): return
            self.cache_busy=False; self.assets_dialog.set_cache_busy(False)
            if event=='error':
                self.assets_dialog.cache_status.setText('清理失败：'+str(data))
                QMessageBox.warning(self.assets_dialog,'清理失败',str(data));return
            removed=data['deleted']
            if self.image_viewer and within_any(self.image_viewer.source_path,removed): self.image_viewer.close()
            if player and within_any(player.manifest,removed):player.reset()
            if hasattr(self,'short_video') and within_any(self.short_video.continuation_source,removed):self.short_video.start_new()
            if audio and within_any(audio.manifest,removed):
                audio.manifest=None;audio.wave.values=None;audio.wave.update();audio.title.setText('独立音频')
                for control in (audio.play,audio.slider,audio.export):control.setEnabled(False)
            if within_any(self.output,removed) or within_any(self.preview_path,removed) or within_any(self.animation_player.manifest,removed):
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
            if audio:audio.load_history()
            text=f'已清除 {len(removed)} 个任务缓存；跳过 {len(data["skipped"])} 个正在运行或排队的任务。已另存文件保留。'
            if data['errors']:
                text+=f' {len(data["errors"])} 项清理失败，详见日志。'; self.log.append('\n'.join(data['errors']))
                QMessageBox.warning(self.assets_dialog,'部分缓存未能清除','\n'.join(data['errors']))
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
        from .seed_controls import from_folder
        from_folder(self,Path(path).parent)
        self.assets_dialog.close()

    def show_image(self, path, allow_zoom=True,role='result'):
        if role=='reference' and hasattr(self,'workbench'):
            self.workbench.show_reference();return
        if role=='result':
            from .seed_controls import from_folder
            from_folder(self,Path(path).parent)
        if hasattr(self,'video_controller'):self.video_controller.player.stop()
        self.animation_player.stop()
        self.sequence_preview.clear_sequence()
        self.pixmap = QPixmap(path); self.output = path if role=='result' else None
        self.preview_path=path; self.preview_role=role
        self.image_save.setEnabled(role=='result');self.image_reuse.setEnabled(role=='result')
        self.preview.set_clickable(allow_zoom and not self.pixmap.isNull() and Path(path).suffix.lower() != '.gif')
        self.caption.setText('参考图 · '+(self.reference_display_name or Path(path).name) if role=='reference' else
            '生成图片 · 点击查看原图' if allow_zoom else '动作帧预览')
        self.fit_preview()

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
        if hasattr(self,'workbench'):self.workbench.refresh_asset_selection()
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
        if hasattr(self,'audio_controller'):self.audio_controller.stop()
        self.video_controller.motion.cancel_preview()
        self.video_controller.player.stop()
        if hasattr(self,'workbench'):
            self.workbench.reference_player.stop()
            try:self.workbench.save_layout()
            except OSError:pass
            self.workbench.settings.hide()
        self.intent_controller.cancel()
        self._closing=True;self.timer.stop();self.prepare_cancel.set()
        if self.current:self.current['cancel'].set()
        client=getattr(self,'client',None)
        if self.current and 'client' in self.current:client=self.current['client']
        if self.current and self.current.get('owned_job'):self.current['owned_job'].close()
        active=client.active_prompts() if client and hasattr(client,'active_prompts') else []
        ids=list(active) if isinstance(active,(list,tuple,set)) else []
        if self.current and self.current.get('prompt_id') and self.current['prompt_id'] not in ids:ids.append(self.current['prompt_id'])
        if self.current and self.current.get('folder'):
            try:
                write_json(Path(self.current['folder'])/'window-closed.json',{
                    'cancel_requested':True,'prompt_ids':ids,'url':getattr(client,'url',None),
                    'note':('窗口已关闭，已取消本地 API 等待；云端可能仍在处理并计费。' if self.current.get('api_job') and not client else
                            '窗口已关闭，后台取消由独立的小进程继续发送；原始结果保留。')})
            except OSError:pass
        if ids and client:
            import subprocess
            command=[sys.executable,'-m','aipictures.cancel_tasks','--url',client.url,
                     '--report',str(DATA/'last-close-cancellation.json')]
            for pid in ids:command+=['--prompt-id',pid]
            try:
                subprocess.Popen(command,cwd=str(Path(__file__).resolve().parent.parent),
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            except OSError:pass
        for worker in self.workers:worker.detach()
        try:self.clear_pending()
        except OSError:self.pending.clear()
        for dialog in self.findChildren(QDialog):dialog.close()
        event.accept()


def create_application(args=None):
    app = QApplication(sys.argv if args is None else args)
    app.setApplicationName('AlI');app.setApplicationDisplayName('AlI')
    from .theme import apply_light_theme
    apply_light_theme(app)
    return app


def main():
    app = create_application()
    window = Window(); window.show()
    code=app.exec()
    # Some native segmentation libraries keep their own thread pools alive at
    # interpreter shutdown. The user's close ends this GUI process; cancellation
    # of the separate ComfyUI server is handled by cancel_tasks, without killing it.
    if window._closing and any(worker.isRunning() for worker in window.workers):
        import os
        os._exit(code)
    sys.exit(code)


if __name__ == '__main__': main()
