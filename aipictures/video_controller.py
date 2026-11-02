"""Two-stage animation UX and queue, without requiring manual skeletal editing."""
import json
import secrets
import shutil
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QListWidgetItem,QFileDialog,QDoubleSpinBox

from .storage import write_json
from .engine import ComfyClient


class VideoController:
    def __init__(self,window):
        self.window=window;self.data=window.api_controller.data;self.action_drafts={};self.last_action=None
        self.prompt_mode=False;self.image_prompt='';self.animation_prompt=None;self.inserted_template=''
        from .video_preview import VideoPreview
        self.player=VideoPreview(window)
        window.workspace_layout.insertWidget(window.workspace_layout.indexOf(window.animation_player)+1,self.player)
        window.animation_engine.blockSignals(True);window.animation_engine.clear()
        window.animation_engine.addItem('Wan2.2 · 自由动画','video_wan')
        window.animation_engine.addItem('MiniMax H3 · 独立引擎','h3')
        window.animation_engine.addItem('骨骼动作 · 研究工具','animate')
        from .h3_backend import settings
        self.h3=settings(self.data);window.animation_engine.model().item(1).setEnabled(bool(self.h3))
        window.animation_engine.setCurrentIndex(1 if self.h3 else 0)
        window.animation_engine.blockSignals(False)
        window.walk_form.insertRow(0,'动画模型',window.animation_engine)
        self.seconds=QDoubleSpinBox();self.seconds.setRange(2,8);self.seconds.setSingleStep(1);self.seconds.setValue(4)
        window.walk_form.insertRow(1,'片段时长（秒）',self.seconds)
        window.animation_action.currentIndexChanged.connect(self.action_changed)
        self.action_changed()

    def free(self):return self.window.animation_engine.currentData() in ('video_wan','h3')

    def action_changed(self,*_):
        w=self.window
        from .animation_actions import ACTIONS
        if self.last_action is not None:self.action_drafts[self.last_action]=w.custom_description.toPlainText()
        action=w.animation_action.currentData()
        text=self.action_drafts.get(action,'' if action=='custom' else ACTIONS[action][1])
        # Each template has its own draft; switching actions never silently keeps a different move.
        text=text.replace('整体跳跃轨迹由游戏引擎驱动，不烘焙进PNG。','')
        w.custom_description.setPlainText(text);self.last_action=action
        if self.prompt_mode:
            content=w.positive.toPlainText()
            if self.inserted_template and self.inserted_template in content:content=content.replace(self.inserted_template,'',1).strip()
            new='' if action=='custom' else ACTIONS[action][1].replace('整体跳跃轨迹由游戏引擎驱动，不烘焙进PNG。','')
            if new and new not in content:content=(content+'\n\n'+new).strip()
            self.inserted_template=new;w.positive.setPlainText(content)

    def sync_prompt_mode(self,active):
        if active==self.prompt_mode:return
        w=self.window
        if active:
            self.image_prompt=w.positive.toPlainText()
            if self.animation_prompt is None:
                from .animation_actions import ACTIONS
                action=w.animation_action.currentData()
                self.inserted_template='' if action=='custom' else ACTIONS[action][1].replace('整体跳跃轨迹由游戏引擎驱动，不烘焙进PNG。','')
                self.animation_prompt='\n\n'.join(t for t in (self.image_prompt,self.inserted_template) if t)
            w.positive.setPlainText(self.animation_prompt)
        else:
            self.animation_prompt=w.positive.toPlainText();w.positive.setPlainText(self.image_prompt)
        self.prompt_mode=active

    def apply_ui(self):
        w=self.window;walking=w.generation_type.currentData()=='walk';free=self.free()
        self.sync_prompt_mode(walking and free)
        w.animation_action_label.setText('动作模板' if free else '动作')
        w.update_lora_state()
        w.settings_buttons['image'].setVisible(not walking or not free)
        for field in (w.steps,w.sampler,w.scheduler):w.sampling_form.setRowVisible(field,not walking)
        w.sampling_form.setRowVisible(w.cfg,not walking and w.model_family.currentData()=='sdxl')
        w.animation_steps.setEnabled(walking and w.animation_engine.currentData() in ('video_wan','animate'))
        w.walk_form.setRowVisible(w.animation_steps,walking and w.animation_engine.currentData()!='h3')
        for field in (w.motion_mode,w.research_motion_button,w.animation_style,w.style_link,
                      w.animation_detail,w.animation_sampler,w.animation_color,w.walk_count,w.walk_fps,w.motion_note):
            w.walk_form.setRowVisible(field,walking and not free)
        w.walk_form.setRowVisible(self.seconds,walking and free)
        w.research_bones_button.setVisible(walking and not free)
        w.custom_form.setRowVisible(w.custom_strategy,False)
        w.custom_settings.setVisible(walking and not free and w.animation_action.currentData()=='custom')
        w.custom_loop.hide();w.animation_style.setChecked(False)
        if not walking:self.player.stop()
        if walking and free:
            if w.api_controller.cloud:
                w.generate_button.setEnabled(False);w.intent_hint.setText('动画使用本地引擎；请在API设置中切回本地生成。');return
            w.generate_button.setEnabled(not w.preparing and (bool(self.h3) if w.animation_engine.currentData()=='h3' else w.connected))
            w.custom_hint.setText('动作描述为准；生成完整动画后再选择拆帧，不需要调整骨骼。')
            w.positive.setPlaceholderText('一起描述角色、场景和动作，例如：蓝发角色面向右侧原地跑步，双腿交替迈步，保持参考图配色。')
            w.context_label.setText('动画创作');w.generate_button.setText('生成完整动画')
            w.intent_hint.setText('正向提示词统一描述画面与动作 → 完整动画预览 → 自主选帧导出')
            w.creation_summary.setText('自由动画\n'+('MiniMax H3' if w.animation_engine.currentData()=='h3' else 'Wan2.2')+'\n先预览完整片段，再导出素材')
        elif walking:
            w.custom_strategy.setCurrentIndex(w.custom_strategy.findData('skeleton'))
        w.animation_style.hide();w.style_link.hide()

    def intercept(self):
        w=self.window
        if w.generation_type.currentData()!='walk' or not self.free():return False
        if w.api_controller.cloud:return False
        if w.preparing:return True
        engine='h3' if w.animation_engine.currentData()=='h3' else 'wan'
        if engine=='wan' and not w.connected:raise ValueError('请先连接本地 ComfyUI。')
        description=''
        reference=w.reference_path if w.animation_source.currentData()=='reference' else None
        prompt=w.positive.toPlainText().strip()
        if not prompt:raise ValueError('请在正向提示词中描述画面与动作。')
        if len(prompt)>16000 or len(description)>8000 or len(w.negative.toPlainText())>8000:
            raise ValueError('描述过长，请将画面提示词控制在16000字、动作及反向描述各8000字以内。')
        if w.animation_source.currentData()=='reference' and not reference:raise ValueError('请添加参考图，或选择仅文字描述。')
        if not reference and not prompt:raise ValueError('无参考图时，请填写画面或角色描述。')
        seed=int(w.seed.text());seed=secrets.randbelow(2**53) if seed==-1 else seed
        if not 0<=seed<2**64:raise ValueError('种子范围不正确。')
        folder=self.new_folder()
        if reference:
            frozen=folder/('reference'+Path(reference).suffix);shutil.copyfile(reference,frozen);reference=str(frozen)
        params={'mode':'video','engine':engine,'backend':'standalone' if engine=='h3' else 'local',
            'prompt':prompt,'negative':w.negative.toPlainText(),'action_description':description,'prompt_layout':'unified',
            'seed_mode':w.seed_mode.currentData(),
            'reference':reference,'seed':seed,'seconds':self.seconds.value(),'steps':w.animation_steps.value(),
            'checkpoint':w.model.currentText(),'url':w.client.url if w.connected else None,'lora':''}
        if engine=='h3':
            if not self.h3:raise ValueError('H3 独立环境尚未完成验证。')
            params['h3_settings']=self.h3.copy()
        self.enqueue(params,folder)
        return True

    def new_folder(self):
        folder=self.data/'videos'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]);folder.mkdir(parents=True)
        return folder

    def enqueue(self,params,folder):
        w=self.window;write_json(folder/'job.json',{'schema_version':1,'kind':'video','status':'queued','params':params})
        item=QListWidgetItem('完整动画 · 等待');w.queue_list.addItem(item)
        from .seed_controls import show_seed
        show_seed(w,params['seed'])
        w.pending.append((None,params,folder,item));w.add_chat('你',params['prompt'])
        w.add_chat('软件','已加入完整动画生成；生成结束后由你选择是否拆帧。',job=str(folder));w.start_next()

    def start(self,params,folder,item):
        from .video_generation import generate
        w=self.window;cancel=threading.Event()
        client=ComfyClient(params['url']) if params.get('url') else None
        w.current={'folder':folder,'params':params,'cancel':cancel,'client':client}
        w.connect_button.setEnabled(False);item.setText('完整动画 · 制作中')
        w.task_display.start();w.progress.setRange(0,0)
        write_json(folder/'job.json',{'schema_version':1,'kind':'video','status':'running','params':params})
        def event(kind,data):
            if kind=='workflow_ready':
                w.last_chat_graph=data['graph'];w.editor_needs_sync=True;w.sync_editor_if_needed()
            elif kind=='executing':w.current['sampling_node']=str(data.get('node') or '')
            elif kind in ('video_stage','reference_stage','condition_stage','monitor_waiting','cancel_pending'):
                w.status.setText(data.get('message','正在制作完整动画…'))
            elif kind=='h3_process':w.current.update(process_pid=data['pid'],owned_job=data.get('owner'))
            elif kind=='queued':w.current['prompt_id']=data['prompt_id']
            elif kind=='decode_event':
                if data['event']=='queued':w.current['prompt_id']=data['data']['prompt_id']
                w.status.setText('采样已保存，正在解码完整动画…')
            elif kind=='video_decode_progress':
                w.progress.setRange(0,100);w.progress.setValue(round(80+15*data['done']/max(1,data['total'])))
            elif kind=='progress':
                fraction=data['value']/max(1,data['max'])
                if params['engine']=='wan':
                    node=(w.last_chat_graph or {}).get(str(data.get('node') or w.current.get('sampling_node','')),{})
                    if node.get('class_type')=='KSamplerAdvanced':
                        inputs=node['inputs'];fraction=(inputs['start_at_step']+(min(inputs['steps'],inputs['end_at_step'])-inputs['start_at_step'])*fraction)/inputs['steps']
                w.progress.setRange(0,100);w.progress.setValue(max(w.progress.value(),round(80*fraction)))
                w.status.setText('制作完整动画 · 模型采样中…')
            elif kind in ('result','error','cancelled'):
                status={'result':'completed','error':'failed','cancelled':'cancelled'}[kind]
                write_json(folder/'job.json',{'schema_version':1,'kind':'video','status':status,'params':params,'error':None if kind=='result' else str(data)})
                w.current=None;w.task_display.finish(status);w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' else 0)
                w.connect_button.setEnabled(True)
                item.setText('完整动画 · '+{'result':'完成','error':'失败','cancelled':'取消'}[kind])
                if kind=='result':
                    try:self.player.load(data['manifest'])
                    except (OSError,ValueError,KeyError) as exc:w.add_chat('软件','动画已生成，但预览读取失败：'+str(exc),job=str(folder))
                    w.load_gallery()
                    w.add_chat('软件','完整动画已保存并循环播放。点击“选帧与导出”勾选需要的帧。',job=str(folder))
                else:w.add_chat('软件','完整动画'+('已取消：' if kind=='cancelled' else '失败：')+str(data),job=str(folder))
                QTimer.singleShot(0,w.start_next)
        w.launch(lambda emit:generate(client,folder,params,cancel,emit),event)

    def refresh_history(self):
        w=self.window;w.assets_dialog.videos.clear()
        for folder in w.cache_store.entries('video'):
            path=folder/'video.json'
            try:data=json.loads(path.read_text('utf-8'))
            except (OSError,ValueError):continue
            title=data.get('params',{}).get('prompt','').strip() or data.get('params',{}).get('action_description','').strip() or data.get('title','完整动画')
            title=title[:24]+('…' if len(title)>24 else '')
            status={'completed':'完成','failed':'失败','cancelled':'已取消','preparing':'处理中'}.get(data['status'],data['status'])
            item=QListWidgetItem(title+' · '+status)
            item.setData(Qt.ItemDataRole.UserRole,str(path));item.setData(Qt.ItemDataRole.UserRole+1,str(folder))
            w.assets_dialog.videos.addItem(item)

    def import_file(self):
        w=self.window
        if w.current or w.preparing:
            w.status.setText('请等当前制作结束后再导入动画。');return
        path,_=QFileDialog.getOpenFileName(w,'导入完整动画预览','','动画 (*.mp4 *.mkv *.mov *.webm *.avi *.gif)')
        if not path:return
        source=Path(path)
        try:
            if source.stat().st_size>2*1024**3:raise ValueError('请选择不超过2GB的动作片段。')
        except (OSError,ValueError) as exc:w.add_chat('软件','无法导入动画：'+str(exc));return
        folder=self.new_folder();w.preparing=True;w.importing_folder=folder;w.prepare_cancel.clear()
        w.task_display.start();w.progress.setRange(0,0)
        def prepare(emit):
            from .video_io import preview_frames
            from .workflow_library import digest
            target=folder/('source'+source.suffix.lower());shutil.copyfile(source,target)
            write_json(folder/'video.json',{'kind':'video','status':'preparing','frames':[]})
            frames,fps=preview_frames(target,folder/'preview_frames',w.prepare_cancel,emit)
            manifest={'schema_version':1,'kind':'video','status':'completed','title':'导入完整动画',
                'source_video':str(target.resolve()),'source_sha256':digest(target),'fps':fps,
                'frame_count':len(frames),'duration_seconds':len(frames)/fps,'sprites_created':False,
                'frames':[{'image':str(p.relative_to(folder))} for p in frames]}
            write_json(folder/'video.json',manifest)
            return {'manifest':str(folder/'video.json')}
        def event(kind,data):
            if kind=='video_stage':w.status.setText(data['message'])
            elif kind in ('result','error','cancelled'):
                w.preparing=False;w.importing_folder=None;w.task_display.finish('completed' if kind=='result' else 'failed')
                w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' else 0)
                if kind=='result':self.player.load(data['manifest']);w.load_gallery()
                else:
                    write_json(folder/'video.json',{'kind':'video','status':'failed' if kind=='error' else 'cancelled','frames':[],'error':str(data)})
                    w.add_chat('软件','导入动画未完成：'+str(data),job=str(folder))
                QTimer.singleShot(0,w.start_next)
        w.launch(prepare,event)

    def open_history(self,item):
        try:self.player.load(item.data(Qt.ItemDataRole.UserRole));self.window.assets_dialog.close()
        except Exception as exc:self.window.add_chat('软件',str(exc))
