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
        window.animation_engine.addItem('MiniMax H3','h3')
        from .h3_backend import settings
        self.h3=settings(self.data)
        try:self.long_ready=bool(json.loads((self.data/'long-video-settings.json').read_text('utf-8')).get('validated'))
        except (OSError,ValueError):self.long_ready=False
        try:self.edit_ready=bool(json.loads((self.data/'video-edit-settings.json').read_text('utf-8')).get('validated'))
        except (OSError,ValueError):self.edit_ready=False
        from .motion_native_backend import settings as motion_settings
        self.motion_settings=motion_settings(self.data)
        window.animation_engine.setCurrentIndex(0)
        window.animation_engine.blockSignals(False)
        window.walk_form.insertRow(0,'动画模型',window.animation_engine)
        window.animation_engine.setEnabled(False)  # One supported engine, no silent legacy fallback.
        self.seconds=QDoubleSpinBox();self.seconds.setRange(2,8);self.seconds.setDecimals(3);self.seconds.setSingleStep(1);self.seconds.setValue(4)
        window.walk_form.insertRow(1,'片段时长（秒）',self.seconds)
        from .motion_reference_ui import MotionReferencePanel
        self.motion=MotionReferencePanel(window,self.seconds)
        self.seconds.valueChanged.connect(lambda *_:self.apply_ui())
        window.workspace_layout.insertWidget(window.workspace_layout.indexOf(window.intent_hint),self.motion)
        self.motion.changed.connect(self.motion_changed)
        self.motion.hide()
        window.animation_action.currentIndexChanged.connect(self.action_changed)
        self.action_changed()

    def free(self):return self.window.animation_engine.currentData()=='h3'

    def motion_changed(self):
        if self.motion.path:
            self.window.animation_action.setCurrentIndex(self.window.animation_action.findData('custom'))
        self.apply_ui()

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
        if hasattr(w,'short_video'):
            editing=w.short_video.active() and w.short_video.kind.currentData()=='long_video' and bool(self.motion.path)
            w.short_video.edit_hint.setVisible(editing)
            w.short_video.brief.setPlaceholderText('例如：将源视频人物替换为图1的人物和服装，图2只提供画风，保留原动作顺序、背景与镜头。' if editing else '描述本段游戏CG的画面、情节与镜头；完成后填写下一段要求即可接续。')
        if hasattr(w,'workbench') and w.workbench.category=='audio':
            w.generate_button.setText('生成音频');w.generate_button.setEnabled(bool(w.audio_controller.config) and not w.preparing);return
        self.sync_prompt_mode(walking and free)
        self.motion.setVisible(hasattr(w,'workbench') or walking and free)
        w.animation_action.setEnabled(not self.motion.path)
        if not walking and self.motion.preview_dialog:self.motion.preview_dialog.close()
        if hasattr(w,'attach_reference_button'):
            w.attach_reference_button.setText('＋ 角色 / 风格图' if walking else '＋ 参考图')
        w.animation_action_label.setText('动作模板' if free else '动作')
        w.update_lora_state()
        w.settings_buttons['image'].setVisible(not walking or not free)
        fixed=w.model_family.currentData() in ('auto','zimage','flux_klein','qwen_edit')
        for field in (w.steps,w.sampler,w.scheduler):w.sampling_form.setRowVisible(field,not walking and not fixed)
        w.sampling_form.setRowVisible(w.cfg,not walking and w.model_family.currentData()=='sdxl')
        w.walk_form.setRowVisible(w.animation_steps,False)
        for field in (w.motion_mode,w.research_motion_button,w.animation_style,w.style_link,
                      w.animation_detail,w.animation_sampler,w.animation_color,w.walk_count,w.walk_fps,w.motion_note):
            w.walk_form.setRowVisible(field,False)
        if w.walk_form.getWidgetPosition(self.seconds)[0]>=0:w.walk_form.setRowVisible(self.seconds,walking and free)
        w.research_bones_button.hide()
        w.custom_form.setRowVisible(w.custom_strategy,False)
        w.custom_settings.hide()
        w.custom_loop.hide();w.animation_style.setChecked(False)
        if not walking:self.player.stop()
        if walking and free:
            if w.api_controller.cloud:
                w.generate_button.setEnabled(False);w.intent_hint.setText('动画使用本地引擎；请在API设置中切回本地生成。');return
            available=self.motion_settings if self.motion.path else self.h3
            w.generate_button.setEnabled(not w.preparing and bool(available))
            w.custom_hint.setText('动作描述为准；生成完整动画后再选择拆帧，不需要调整骨骼。')
            w.positive.setPlaceholderText('描述想要的动作…')
            w.context_label.setText('动画创作');w.generate_button.setText('生成动画')
            if hasattr(w,'short_video') and w.short_video.active():w.generate_button.setText('生成短视频')
            if hasattr(w,'short_video') and w.short_video.kind.currentData()=='long_video':
                w.generate_button.setText('接续生成' if w.short_video.continuation_source else '生成本段');w.generate_button.setEnabled(bool(self.h3) and self.long_ready and not w.preparing)
            w.intent_hint.setText('正向提示词描述画面与动作 → 完整动画预览 → 自主选帧导出' if self.h3 else 'MiniMax H3 尚未安装并验证；请先完成独立引擎设置。')
            if self.motion.path:
                w.generate_button.setEnabled(not w.preparing and bool(self.motion_settings))
                w.intent_hint.setText('动作跟随参考动画或PNG帧；图片与文字指定角色和画风。' if self.motion_settings else '动作素材已就绪；专用参考引擎尚未完成本机验证，暂不能生成。移除动作参考可继续普通动画。')
            if hasattr(w,'short_video') and w.short_video.kind.currentData()=='long_video':
                w.generate_button.setText('生成编辑视频' if self.motion.path else '接续生成' if w.short_video.continuation_source else '生成本段')
                w.generate_button.setEnabled(not w.preparing and bool(self.h3) and (bool(self.motion_settings) and self.edit_ready and self.seconds.value()<=8 if self.motion.path else self.long_ready))
            w.creation_summary.setText('自由动画\nMiniMax H3\n先预览完整片段，再导出素材')
        w.animation_style.hide();w.style_link.hide()

    def intercept(self):
        w=self.window
        if w.generation_type.currentData()!='walk':return False
        if hasattr(w,'intent_controller') and not hasattr(w,'generation_intent'):w.intent_controller.validate_generation()
        if not self.free():raise ValueError('旧骨骼与 Wan 动画路线已停用，请选择 MiniMax H3。')
        if w.api_controller.cloud:return False
        if w.preparing:return True
        long=hasattr(w,'short_video') and w.short_video.kind.currentData()=='long_video'
        if long and not self.long_ready:raise ValueError('本机长视频还在完整验收，尚不能提交。')
        editing=bool(self.motion.path)
        if editing and long and not self.edit_ready:raise ValueError('参考视频编辑还在完整验收，尚不能提交。')
        if editing and long and not self.h3:raise ValueError('视频编辑的原生音轨组件尚未就绪，未启动生成。')
        if editing and self.seconds.value()>8:raise ValueError('本机参考套用单次最多8秒；当前已保留参考原时长，请选择8秒内的片段再生成。')
        engine='h3'
        if not self.motion.path and not self.h3:raise ValueError('MiniMax H3 尚未安装并验证，不能生成动画；不会切回已停用的 Wan。')
        if self.motion.path and not self.motion_settings:raise ValueError('专用动作参考引擎尚未完成本机验证，请先移除动作参考以使用普通动画。')
        description=''
        short=hasattr(w,'short_video') and w.short_video.active()
        reference=w.reference_path if w.animation_source.currentData()=='reference' else None
        prompt=w.positive.toPlainText().strip()
        if hasattr(w,'generation_intent'):prompt,_=w.generation_intent.prompts()
        if short and not prompt:prompt=w.short_video.brief.toPlainText().strip()
        if not prompt and self.motion.path and reference:prompt='按动作参考生成动画，保留角色参考图的主体、衣着、配色与画风。'
        if not prompt:raise ValueError('请在正向提示词中描述画面与动作。')
        if len(prompt)>16000 or len(description)>8000 or len(w.negative.toPlainText())>8000:
            raise ValueError('描述过长，请将画面提示词控制在16000字、动作及反向描述各8000字以内。')
        if w.animation_source.currentData()=='reference' and not reference and not short:raise ValueError('请添加参考图，或选择仅文字描述。')
        if not reference and not prompt:raise ValueError('无参考图时，请填写画面或角色描述。')
        script=w.short_video.snapshot() if short and not hasattr(w,'generation_intent') else None
        if short and hasattr(w,'generation_intent'):
            from .video_script import simple
            script=simple(prompt,self.seconds.value(),w.short_video.music.currentData(),'')
        elif short and w.short_video.script is None:
            from .video_script import prompt as script_prompt
            prompt=script_prompt(script)
        available_refs=w.reference_chat.references()
        if not editing and len(available_refs)>1:raise ValueError('没有参考动画时，当前视频引擎只支持一张起始参考图；请保留一张，或先在单张模式合成需要的画面。')
        refs=available_refs if editing else {}
        if editing:
            from .multi_reference import bind_text,image_ids
            negative=w.generation_intent.prompts()[1] if hasattr(w,'generation_intent') else w.negative.toPlainText()
            bind_text(prompt,refs);bind_text(negative,refs)
            mentioned=image_ids(prompt+'\n'+negative)
            if len(refs)>1 and not mentioned:raise ValueError('请用图1、图2等编号说明各图提供人物、画风或其他用途。')
            if mentioned:refs={n:p for n,p in refs.items() if n in mentioned}
            if not self.motion.repeat.isChecked() and self.motion.start.value()+self.seconds.value()>self.motion.meta['duration']+.05:
                raise ValueError('源视频不足本次时长；请选择更长视频，或明确开启循环。不会自动用长时间定格补齐。')
        timeline=w.workbench.timeline.effective_rows() if hasattr(w,'workbench') and not short and not getattr(w.workbench,'reference_skinning',False) else []
        if self.motion.path and hasattr(w,'workbench') and not short and not getattr(w.workbench,'reference_skinning',False):
            prompt,timeline=w.workbench.timeline.generation_input()
            if not prompt:prompt='按动作参考生成动画，保留文字和参考图指定的目标外观。'
        intent=getattr(w,'intent_controller',None)
        reference_role=intent.role.currentData() if intent and not hasattr(w,'generation_intent') else 'appearance'
        reference_usage=intent.role_note.text().strip() if intent and reference_role=='custom' else ''
        if self.motion.path and reference and reference_role=='custom' and not reference_usage:
            raise ValueError('请填写参考图的自定义用法。')
        seed=int(w.seed.text());seed=secrets.randbelow(2**53) if seed==-1 else seed
        if not 0<=seed<2**64:raise ValueError('种子范围不正确。')
        folder=self.new_folder()
        if reference:
            frozen=folder/('reference'+Path(reference).suffix);shutil.copyfile(reference,frozen);reference=str(frozen)
        params={'mode':'video','engine':engine,'backend':'standalone',
            'prompt':prompt,'negative':w.generation_intent.prompts()[1] if hasattr(w,'generation_intent') else w.negative.toPlainText(),'action_description':description,'prompt_layout':'unified',
            'seed_mode':w.seed_mode.currentData(),'defer_exports':True,
            'reference':reference,'seed':seed,'seconds':self.seconds.value(),'steps':w.animation_steps.value(),
            'checkpoint':w.model.currentText(),'url':w.client.url if w.connected else None,'lora':''}
        params['user_prompt']=w.positive.toPlainText()
        params['source_brief']=w.generation_intent.editor().toPlainText() if hasattr(w,'generation_intent') else w.short_video.brief.toPlainText() if short else w.intent_controller.input.toPlainText()
        params['h3_settings']=self.h3.copy();params['motion_timeline']=timeline
        if short:
            from .video_script import write_script
            music_file=None if hasattr(w,'generation_intent') else w.short_video.music_file
            if music_file:
                target=folder/('music_input'+Path(music_file).suffix.lower());shutil.copyfile(music_file,target);music_file=str(target.resolve())
            params.update(creation_kind='long_video' if long else 'short_video',audio_mode='h3_native',short_script=script,music_style=w.short_video.music.currentData(),music_file=music_file)
            if hasattr(w,'generation_intent'):
                params.update(audio_mode='none',music_file=None);script['shots']=[dict(row,sound='无声CG') for row in script['shots']]
            write_script(folder,script)
            if long and not editing:
                from .workflow_library import digest
                previous=w.short_video.continuation_source
                params.update(manual_segments=True,continue_from=str(previous) if previous else None,
                    continue_manifest_sha256=digest(previous) if previous else None)
        if editing:
            from .workflow_library import digest
            from .video_edit import FORMAT
            frozen_refs=[]
            for order,(number,path) in enumerate(refs.items(),1):
                target=folder/'references'/f'{number}{path.suffix.lower()}';target.parent.mkdir(exist_ok=True);shutil.copyfile(path,target)
                frozen_refs.append(dict(number=number,model_input=order,path=str(target.resolve()),sha256=digest(target)))
            params.update(creation_kind='long_video_edit' if long else 'sprite_reference_edit',video_edit_refs=frozen_refs,motion_prompt_format=FORMAT)
        params['motion_timeline_clock']=w.workbench.timeline.clock if hasattr(w,'workbench') else 'output'
        if self.motion.path:
            params['motion_native_settings']=self.motion_settings.copy()
            params['motion_prompt_policy']='reference_first_manual_v2'
            params['reference_role']=reference_role
            params['reference_usage']=reference_usage
            params.update(motion_reference=str(self.motion.path),motion_start=self.motion.start.value(),
                          motion_allow_tail_hold=not editing,
                          motion_max_side=self.motion.detail.currentData(),
                          motion_repeat=self.motion.repeat.isChecked(),
                          motion_source=self.motion.meta.copy(),user_prompt=w.positive.toPlainText())
            w.preparing=True;w.prepare_cancel.clear();w.importing_folder=folder
            write_json(folder/'job.json',{'kind':'video','status':'preparing','params':params})
            from .workflow_library import digest
            def freeze(_):
                from .frame_motion_input import freeze as freeze_input
                source=Path(params['motion_reference']);target=freeze_input(source,folder/'motion_inputs',w.prepare_cancel)
                if digest(target)!=params['motion_source']['sha256']:raise ValueError('动作参考已被修改，请重新导入。')
                return str(target.resolve())
            def ready(kind,data):
                if kind not in ('result','error','cancelled'):return
                w.preparing=False;w.importing_folder=None
                if kind=='result':params['motion_reference']=data;self.enqueue(params,folder)
                else:
                    write_json(folder/'job.json',{'kind':'video','status':'failed' if kind=='error' else 'cancelled','params':params,'error':str(data)})
                    w.add_chat('软件','动作参考准备未完成：'+str(data))
                self.apply_ui();QTimer.singleShot(0,w.start_next)
            w.launch(freeze,ready)
            return True
        self.enqueue(params,folder)
        return True

    def new_folder(self):
        folder=self.data/'videos'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]);folder.mkdir(parents=True)
        return folder

    def enqueue(self,params,folder):
        if hasattr(self.window,'generation_intent'):self.window.generation_intent.record(params)
        if hasattr(self.window,'intent_controller') and not params.get('resume_chain'):self.window.intent_controller.record(folder,params)
        w=self.window;write_json(folder/'job.json',{'schema_version':1,'kind':'video','status':'queued','params':params})
        from .task_display import task_name
        item=QListWidgetItem(task_name(params)+' · 等待');w.queue_list.addItem(item)
        from .seed_controls import show_seed
        show_seed(w,params['seed'])
        w.pending.append((None,params,folder,item));w.add_chat('你',params['prompt'])
        w.add_chat('软件','已加入完整动画生成；生成结束后由你选择是否拆帧。',job=str(folder));w.start_next()

    def start(self,params,folder,item):
        from .video_generation import generate
        w=self.window;cancel=threading.Event()
        client=ComfyClient(params['url']) if params.get('url') and not params.get('motion_reference') else None
        w.current={'folder':folder,'params':params,'cancel':cancel,'client':client}
        from .task_display import task_name
        w.connect_button.setEnabled(False);item.setText(task_name(params)+' · 制作中')
        w.task_display.start();w.progress.setRange(0,0)
        write_json(folder/'job.json',{'schema_version':1,'kind':'video','status':'running','params':params})
        def event(kind,data):
            if kind=='chain_progress':
                w.progress.setRange(0,100);w.progress.setValue(round(data['fraction']*95))
                w.status.setText(data['message'])
            elif kind=='workflow_ready':
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
                w.progress.setRange(0,100);w.progress.setValue(max(w.progress.value(),round(80*fraction)))
                w.status.setText('制作完整动画 · 模型采样中…')
            elif kind in ('result','error','cancelled'):
                status={'result':'completed','error':'failed','cancelled':'cancelled'}[kind]
                write_json(folder/'job.json',{'schema_version':1,'kind':'video','status':status,'params':params,'error':None if kind=='result' else str(data)})
                w.current=None;w.task_display.finish(status);w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' else 0)
                w.connect_button.setEnabled(True)
                item.setText(task_name(params)+' · '+{'result':'完成','error':'失败','cancelled':'取消'}[kind])
                if kind=='result':
                    try:self.player.load(data['manifest'])
                    except (OSError,ValueError,KeyError) as exc:w.add_chat('软件','动画已生成，但预览读取失败：'+str(exc),job=str(folder))
                    w.load_gallery()
                    w.add_chat('软件','完整动画已保存并循环播放。点击“选帧与导出”勾选需要的帧。',job=str(folder))
                else:
                    w.add_chat('软件','完整动画'+('已取消：' if kind=='cancelled' else '失败：')+str(data),job=str(folder))
                    w.load_gallery()
                QTimer.singleShot(0,w.start_next)
        w.launch(lambda emit:generate(client,folder,params,cancel,emit),event)

    def refresh_history(self):
        w=self.window;w.assets_dialog.videos.clear()
        for folder in w.cache_store.entries('video'):
            path=folder/'video.json'
            try:data=json.loads(path.read_text('utf-8'))
            except (OSError,ValueError):continue
            title=data.get('params',{}).get('source_brief','').strip() or data.get('params',{}).get('prompt','').strip() or data.get('params',{}).get('action_description','').strip() or data.get('title','完整动画')
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
        try:
            path=Path(item.data(Qt.ItemDataRole.UserRole));data=json.loads(path.read_text('utf-8'))
            if data['status']!='completed' and ((path.parent/'chain.json').is_file() or (path.parent/'native-chain.json').is_file()):
                self.resume_chain(path,data);return
            if hasattr(self.window,'workbench'):
                long=data.get('params',{}).get('creation_kind') in ('short_video','long_video','long_video_edit') or data.get('duration_seconds',0)>8
                self.window.workbench.select_category('long_video' if long else 'sprite')
                if not long:self.window.workbench.sprite_mode.setCurrentIndex(1)
            self.player.load(path);self.window.assets_dialog.close()
        except Exception as exc:self.window.add_chat('软件',str(exc))

    def resume_chain(self,path,data):
        from PySide6.QtWidgets import QMessageBox
        w=self.window
        kind=data.get('params',{}).get('creation_kind')
        if kind=='long_video_edit' and data['params'].get('seconds',0)>8:raise ValueError('长片参考替换未通过连续性验收，暂不继续。已有输出仍可播放和导出。')
        allowed=((path.parent/'native-chain.json').is_file() and self.long_ready) or (kind=='long_video_edit' and self.edit_ready)
        if data.get('params',{}).get('seconds',0)>8 and not allowed:raise ValueError('此长视频路线尚未验证，不能继续。已有成片仍可播放和导出。')
        if w.current or w.pending or w.preparing:raise ValueError('请先结束当前任务再继续长动画。')
        chain_path=path.parent/('native-chain.json' if (path.parent/'native-chain.json').is_file() else 'chain.json')
        chain=json.loads(chain_path.read_text('utf-8'))
        completed=sum(r.get('status')=='completed' or 'result' in r for r in chain['parts'])
        if QMessageBox.question(w,'继续长动画',f'已完成{completed}/{len(chain["plan"])}段。保留完成部分，继续未完成的片段？')!=QMessageBox.StandardButton.Yes:return
        params=dict(data['params'],resume_chain=True)
        w.assets_dialog.close();self.enqueue(params,path.parent)
