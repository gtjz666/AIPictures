"""Explicit prompt preparation, editable review, then a separate production action."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from PySide6.QtCore import QTimer,QSignalBlocker
from .storage import write_json


class GenerationIntent:
    def __init__(self,w,workbench):
        self.window=w;self.workbench=workbench;self.prepared=None;self.running=False;self.active_key=None;self.plans={};self.outputs={}
        workbench.prompt_output.textChanged.connect(self.output_changed)
        self.sync_mode()

    def key(self):
        w=self.window
        return self.workbench.category if self.workbench.category!='sprite' else w.generation_type.currentData()

    def sync_mode(self):
        key=self.key()
        if key==self.active_key:return
        output=self.workbench.prompt_output
        if self.active_key is not None:self.outputs[self.active_key]=output.toPlainText()
        self.active_key=key;self.prepared=self.plans.get(key)
        with QSignalBlocker(output):output.setPlainText(self.outputs.get(key,''))

    def output_changed(self):
        text=self.window.workbench.prompt_output.toPlainText().strip();source=self.snapshot()
        self.outputs[self.active_key]=text
        self.prepared=dict(signature=self.signature(source),source=source,positive=text,negative='',record=None,
            professionalized=False,manual=True,english=None)
        self.plans[self.active_key]=self.prepared

    def editor(self):
        w=self.window
        return w.audio_controller.prompt if w.workbench.category=='audio' else w.short_video.brief if w.workbench.category=='long_video' else w.positive

    def snapshot(self):
        w=self.window;category=w.workbench.category;motion=w.video_controller.motion
        kind='audio' if category=='audio' else 'video' if category=='long_video' else 'animation' if w.generation_type.currentData()=='walk' else 'image'
        refs=w.reference_chat.references() if kind!='audio' else {}
        return dict(kind=kind,requirement=self.editor().toPlainText().strip(),
            seconds=w.audio_controller.seconds.value() if kind=='audio' else w.video_controller.seconds.value() if kind!='image' else None,
            references=[dict(number=n,path=str(p),size=p.stat().st_size,mtime=p.stat().st_mtime_ns) for n,p in refs.items()],
            motion=str(motion.path) if kind in ('animation','video') and motion.path else None,
            motion_stamp=(motion.path.stat().st_size,motion.path.stat().st_mtime_ns) if kind in ('animation','video') and motion.path else None,
            motion_start=motion.start.value(),motion_repeat=motion.repeat.isChecked(),
            role='appearance',usage='',
            audio_kind=w.audio_controller.effective_kind() if kind=='audio' else None,
            continuation=str(getattr(w.short_video,'continuation_source','') or '') if kind=='video' else None)

    def signature(self,snapshot=None):
        return hashlib.sha256(json.dumps(snapshot or self.snapshot(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def current(self):
        self.sync_mode()
        output=self.window.workbench.prompt_output.toPlainText().strip()
        return self.prepared if self.prepared and self.prepared['signature']==self.signature() and self.prepared['positive']==output else None

    def prompts(self):
        value=self.current()
        if not value:
            if self.prepared:raise ValueError('需求或素材已修改，请重新生成提示词，或修改下方提示词后再生成。')
            return self.editor().toPlainText().strip(),''
        return value['positive'],value['negative']

    def record(self,params):
        value=self.current()
        if value:
            brief=value['source']['requirement'] or value['positive']
            params['source_brief']=brief;params['user_prompt']=brief;params['user_negative']='';params['requirement_contract']=value

    def validate(self,source,output=''):
        from .multi_reference import image_ids
        brief=source['requirement']
        if len(brief)>12000:raise ValueError('请将用户需求控制在12000字以内。')
        if source['kind']!='audio':
            missing=image_ids(brief+'\n'+output)-{row['number'] for row in source['references']}
            if missing:raise ValueError('尚未添加'+'、'.join('图'+str(i) for i in sorted(missing))+'。')

    def intercept(self):
        """Production never automatically professionalizes or reads reference images."""
        w=self.window;c=w.intent_controller
        if self.running or w.preparing:return True
        if w.current or w.pending:raise ValueError('请等待当前任务完成，再生成新的需求。')
        self.sync_mode();source=self.snapshot()
        output=w.workbench.prompt_output.toPlainText().strip()
        self.validate(source,output)
        if not output:raise ValueError('请先点击“生成提示词”，或在下方填写提示词。')
        value=self.current()
        if not value:raise ValueError('需求或素材已修改，请重新生成提示词，或修改下方提示词后再生成。')
        if source['kind']=='image' and value.get('manual') and c.config:
            from .prompt_language import has_chinese
            if has_chinese(output) and not value.get('english'):
                self._start(source,translate_only=True,submit=True);return True
        return False

    def prepare(self):
        try:
            w=self.window
            if self.running or w.preparing or w.current or w.pending:raise ValueError('请等待当前任务完成。')
            self.sync_mode();source=self.snapshot();self.validate(source)
            if not source['requirement']:raise ValueError('请填写用户需求。')
            if not w.intent_controller.config:raise ValueError('本地提示词助手尚未配置；也可以直接在下方填写提示词。')
            self._start(source)
        except (ValueError,OSError) as exc:w.status.setText(str(exc))

    def _start(self,source,*,translate_only=False,submit=False):
        w=self.window;c=w.intent_controller
        brief=source['requirement'];signature=self.signature(source);key=self.active_key
        initial_output=w.workbench.prompt_output.toPlainText().strip()
        folder=c.data/'intent'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]+'_requirement')
        refs={row['number']:Path(row['path']) for row in source['references']}
        config=dict(c.config)
        self.running=c.running=w.preparing=True;c.cancel_event.clear();w.generate_button.setEnabled(False)
        w.workbench.prepare_prompt.setEnabled(False)
        w.task_display.start();w.progress.setRange(0,0);w.status.setText('正在整理本次需求…')
        def run(emit):
            from .motion_native_backend import release_shared
            release_shared({'url':w.client.url if w.connected else None},cancel=c.cancel_event)
            if translate_only:
                from .prompt_language import translate
                return translate(config,initial_output,'',folder,c.cancel_event,emit)
            if source['kind']=='audio':
                if source['audio_kind']=='sfx':
                    from .sfx_prompt import organize
                    return organize(config,brief,source['seconds'],folder,c.cancel_event,emit)
                from .audio_prompt import organize
                return organize(config,brief,source['seconds'],folder,c.cancel_event,emit)
            if source['kind']=='image' and refs:
                from .reference_prompt import organize
            else:
                from .professional_prompt import organize
            return organize(config,brief,'',refs,Path(source['motion']) if source['motion'] else None,folder,c.cancel_event,emit,
                selected_kind='image' if source['kind']=='image' else 'animation',role=source['role'],reference_usage=source['usage'],output_seconds=source['seconds'] or 4.)
        def finish(kind,data):
            if kind in ('audio_stage','intent_stage'):w.status.setText(data['message']);return
            if kind not in ('result','error','cancelled'):return
            self.running=c.running=w.preparing=False
            w.workbench.prepare_prompt.setEnabled(bool(c.config))
            cancelled=c.cancel_event.is_set() or kind=='cancelled'
            unchanged=self.signature()==signature and self.active_key==key and w.workbench.prompt_output.toPlainText().strip()==initial_output
            accepted=kind=='result' and unchanged and not cancelled
            w.task_display.finish('completed' if accepted else 'cancelled' if cancelled else 'failed');w.generation_type_changed()
            write_json(folder/'application.json',dict(accepted=accepted,input_unchanged=unchanged,cancelled=cancelled,status=kind))
            if accepted:
                if translate_only:
                    positive,negative=initial_output,'';extra=dict(english=data,manual=True)
                elif source['kind']=='audio':
                    positive=data['positive_prompt']+('\n避免：'+data['negative_prompt'] if data['negative_prompt'] else '')
                    negative='';extra=dict(english=data['english_caption'])
                else:
                    plan=data['plan'];positive,negative=plan['positive_prompt'],plan['negative_prompt'];extra=dict(english=data.get('english',{}))
                self.prepared=dict(signature=signature,source=source,positive=positive,negative=negative,record=str(folder/'result.json'),professionalized=True,**extra)
                self.plans[key]=self.prepared;self.outputs[key]=positive
                with QSignalBlocker(w.workbench.prompt_output):w.workbench.prompt_output.setPlainText(positive)
                w.status.setText('提示词已生成，可在下方修改，再点击生成。')
                if submit:QTimer.singleShot(0,w.enqueue)
            else:w.status.setText('输入已修改，本次旧结果未应用。' if kind=='result' and not cancelled else '提示词生成已取消。' if cancelled else '提示词生成失败：'+str(data))
        w.launch(run,finish)
