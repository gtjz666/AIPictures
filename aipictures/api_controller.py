"""API settings and serial queue integration; no provider credentials in job files."""
import json
import shutil
import threading
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QPushButton, QListWidgetItem

from .api_config import ApiSettings
from .api_generation import no_secret, reference_png
from .api_transport import redact
from .engine import ComfyClient, is_engine_unavailable
from .storage import write_json
from .task_display import task_name


class ApiController:
    def __init__(self, window, data: Path):
        self.window, self.data = window, Path(data)
        self.load_error = ''
        try:
            self.settings = ApiSettings(data)
        except (ValueError,TypeError,AttributeError,OSError):
            self.settings = ApiSettings(data,load=False)
            self.load_error = 'API 设置无法读取，暂用本地模式；原文件保留，请重新设置。'
        self.dialog = None
        self.runtime = {}

    @property
    def cloud(self) -> bool:
        return self.settings.backend=='api'

    def install_controls(self, layout) -> None:
        self.button = QPushButton('API 与智能生图…')
        self.button.setToolTip('配置自己的服务商、Key 和模型；云端生图或可选提示词整理。')
        self.button.clicked.connect(self.open_settings)
        layout.addWidget(self.button)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setObjectName('muted')
        layout.addWidget(self.summary)

    def open_settings(self) -> None:
        from .api_dialog import ApiDialog
        if self.dialog is None:
            self.dialog = ApiDialog(self)
        self.dialog.reload()
        if self.load_error:
            self.dialog.status.setText(self.load_error)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def apply_mode(self) -> None:
        w = self.window
        if not hasattr(w,'generate_button'):
            return
        cloud = self.cloud
        self.summary.setText(('云端图片 API · 单张图片\n动画请切回本地 ComfyUI' if cloud else '本地 ComfyUI')+
            ('\n单图先整理提示词（额外调用）' if self.settings.smart else '')+
            ('\n'+self.load_error if self.load_error else ''))
        w.generate_button.setEnabled(not w.preparing and (cloud or w.connected))
        if cloud:
            for name in ('model','width','height','steps','cfg','seed','sampler','scheduler','lora',
                         'lora_category','strength','denoise','reference_strength','quality_mode','workflow_selector'):
                getattr(w,name).setEnabled(False)
            w.style_status.setText('云端模型直接理解描述与参考图；本地 LoRA、CFG 和采样参数不参与。尺寸在 API 设置中选择。')
            w.creation_summary.setText('云端单张图片\n'+self.settings.endpoints['image'].model+'\n尺寸与画质：API 设置')
            w.reference_note.setText('参考图随本次请求发送；保真是提示词约束，不能保证细节完全一致。')
            w.intent_hint.setText('云端单张创作 · 保留中文描述，不套用本地有限词表。')
        else:
            for name in ('seed','cfg','width','height','steps','sampler','scheduler','quality_mode'):
                getattr(w,name).setEnabled(True)
            w.generation_type_changed()

    def intercept(self) -> bool:
        w = self.window
        if not self.cloud and (not self.settings.smart or w.generation_type.currentData()=='walk'):
            return False
        if w.preparing:
            return True
        if w.generation_type.currentData()=='walk':
            raise ValueError('本次 API 接入支持单张图片；动画请在“API 与智能生图”切回本地 ComfyUI。')
        self.enqueue()
        return True

    def enqueue(self) -> None:
        w = self.window
        planner = self.settings.auth('planner') if self.settings.smart else None
        image = self.settings.auth('image') if self.cloud else None
        secrets = tuple(auth.key for auth in (planner,image) if auth)
        prompt, negative = w.positive.toPlainText(), w.negative.toPlainText()
        if len(prompt)>16000 or len(negative)>8000:
            raise ValueError('描述过长，请将正向提示词控制在 16000 字符、反向词在 8000 字符以内。')
        if not prompt.strip() and not w.reference_path:
            raise ValueError('请填写画面描述，或主动选择参考图。')
        no_secret(prompt+'\n'+negative,*secrets)
        reference = Path(w.reference_path) if w.reference_path else None
        if reference:
            reference_png(reference)  # Validate before a paid planning/generation request.
        graph, client = {}, None
        params = {'user_prompt':prompt,'user_negative':negative,
            'output_background':w.output_background.currentData(),
            'reference_policy':w.reference_policy.currentData()}
        if image:
            if reference and image.endpoint.protocol=='openai' and not image.endpoint.edits:
                raise ValueError('所选 API 尚未启用参考图编辑；请确认平台支持并在 API 设置中勾选。')
            params.update(image_model=image.endpoint.model,provider_url=image.endpoint.base_url,
                          protocol=image.endpoint.protocol)
        else:
            if not w.connected:
                raise ValueError('本地智能生图需要先连接 ComfyUI；也可改选云端图片 API。')
            graph, params = w.graph_snapshot('__api_reference__' if reference else '')
            if not reference and params['bindings']['reference']:
                raise ValueError('此工作流需要参考图，请添加图片或恢复自动工作流。')
            from .prompt_binding import check_models
            from .image_quality import check_quality_models
            check_models(graph,w.info['object_info'])
            check_quality_models(w.info['object_info'],params['quality_mode'])
            client = ComfyClient(w.client.url)
        if params['output_background']=='transparent':
            from .background import model_file
            if not model_file().is_file():
                raise ValueError('透明输出需要现有去背景模型；请先安装或选择完整画面。')
        params.update(mode='smart_image',backend='api' if image else 'local',smart=bool(planner),
            planner_model=planner.endpoint.model if planner else None,automatic_post_retries=0)
        no_secret(json.dumps(params,ensure_ascii=False),*secrets)
        # Snapshot the reference, so changing the UI or original file never changes a queued job.
        folder = self.data/'jobs'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8])
        folder.mkdir(parents=True)
        frozen = None
        if reference:
            frozen = folder/('reference'+reference.suffix.lower())
            shutil.copyfile(reference,frozen)
        params['reference'] = str(frozen) if frozen else None
        write_json(folder/'workflow.json',graph)
        write_json(folder/'job.json',{'schema_version':1,'kind':'image','status':'created','params':params})
        self.runtime[str(folder)] = (planner,image,frozen,client)
        item = QListWidgetItem(task_name(params)+' · 等待')
        item.setToolTip(str(folder)); w.queue_list.addItem(item)
        w.pending.append((graph,params,folder,item))
        w.add_chat('你',prompt.strip() or '使用参考图创作',str(frozen) if frozen else None)
        w.add_chat('软件','已加入队列 · '+task_name(params),job=str(folder))
        w.start_next()

    def start(self, graph, params, folder, item) -> None:
        from .smart_generation import generate
        w = self.window
        planner,image,reference,client = self.runtime.pop(str(folder))
        secrets = tuple(auth.key for auth in (planner,image) if auth)
        cancel = threading.Event()
        ticket = {'folder':folder,'params':params,'cancel':cancel,'api_job':True,'client':client}
        w.current = ticket
        w.task_display.start(); w.progress.setRange(0,0)
        w.status.setText('准备智能生图…'); item.setText(task_name(params)+' · 执行中')
        w.connect_button.setEnabled(False); w.update_job('running')
        def event(kind, data):
            if w.current is not ticket:
                return
            if kind=='art_plan':
                w.add_chat('软件','本次方案：'+data,job=str(folder))
            elif kind=='workflow_ready':
                params.update(data['params'])
                w.last_chat_graph = data['graph']; w.editor_needs_sync = True
                w.sync_editor_if_needed(); w.update_job('running')
            elif kind=='queued':
                ticket['prompt_id'] = data['prompt_id']; w.update_job('queued')
            elif kind=='progress':
                w.progress.setRange(0,100)
                w.progress.setValue(round(80*data['value']/max(1,data['max'])))
            elif kind in ('api_stage','postprocess','monitor_waiting','executing'):
                message = data.get('message') if isinstance(data,dict) else None
                w.status.setText(message or ('正在透明处理…' if kind=='postprocess' else '模型正在处理…'))
            elif kind in ('result','error','cancelled'):
                status = {'result':'completed','error':'failed','cancelled':'cancelled'}[kind]
                if kind=='result':
                    write_json(folder/'result.json',data)
                    w.show_image(data['images'][0]); w.load_gallery()
                    w.add_chat('软件','生成完成，已保存实际方案和图片。',data['images'][0],str(folder))
                else:
                    data = redact(str(data),*secrets)
                    w.add_chat('软件',('已取消：' if kind=='cancelled' else '生成失败：')+data,job=str(folder))
                    w.log.append(data)
                    if client and kind=='error' and is_engine_unavailable(data):
                        w.disconnect_engine('本地引擎连接中断，请重新连接。')
                w.update_job(status,None if kind=='result' else data)
                write_json(folder/'api-outcome.json',{'status':status,'automatic_post_retries':0,
                    'error':None if kind=='result' else data,
                    'note':'取消/超时不代表云端停止或退款，请核对服务商记录。'})
                w.task_display.finish(status)
                item.setText(task_name(params)+' · '+{'result':'完成','error':'失败','cancelled':'取消'}[kind])
                w.status.setText({'result':'生成完成，已保存','error':'生成失败，详见消息记录','cancelled':'任务已取消'}[kind])
                w.progress.setRange(0,100); w.progress.setValue(100 if kind=='result' else 0)
                w.current = None; w.connect_button.setEnabled(True)
                self.apply_mode(); QTimer.singleShot(0,w.start_next)
        # Redact before Worker emits exceptions; no provider text or credentials reaches Qt logs.
        def action(emit):
            try:
                return generate(folder,graph.copy(),params.copy(),planner,image,reference,client,cancel,emit)
            except Exception as exc:
                from .engine import Cancelled
                error = Cancelled if isinstance(exc,Cancelled) else RuntimeError
                raise error(redact(str(exc),*secrets)) from None
        w.launch(action,event)

    def cancel(self) -> bool:
        ticket = self.window.current
        if not ticket or not ticket.get('api_job'):
            return False
        ticket['cancel'].set()
        self.window.status.setText('已请求取消；云端可能仍在处理并计费，不会重复提交。')
        client = ticket['client']
        if client:
            self.window.launch(lambda _:[client.cancel(pid) for pid in client.active_prompts()],lambda *_:None)
        return True
