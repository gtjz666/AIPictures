"""One visible requirement, one frozen professionalization before generation."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from PySide6.QtCore import QTimer
from .storage import write_json


class GenerationIntent:
    def __init__(self,w):self.window=w;self.prepared=None;self.running=False

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

    def current(self):return self.prepared if self.prepared and self.prepared['signature']==self.signature() else None

    def prompts(self):
        value=self.current()
        if not value:return self.editor().toPlainText().strip(),''
        return value['positive'],value['negative']

    def record(self,params):
        value=self.current()
        if value:
            params['source_brief']=value['source']['requirement'];params['user_prompt']=value['source']['requirement'];params['user_negative']='';params['requirement_contract']=value

    def intercept(self):
        w=self.window;c=w.intent_controller
        if self.running or w.preparing:return True
        if w.current or w.pending:raise ValueError('请等待当前任务完成，再生成新的需求。')
        if self.current():return False
        source=self.snapshot();brief=source['requirement']
        if not brief:raise ValueError('请填写用户需求。')
        if len(brief)>12000:raise ValueError('请将用户需求控制在12000字以内。')
        if source['kind']!='audio':
            from .multi_reference import image_ids
            missing=image_ids(brief)-{row['number'] for row in source['references']}
            if missing:raise ValueError('尚未添加'+'、'.join('图'+str(i) for i in sorted(missing))+'。')
        signature=self.signature(source)
        if not c.config:
            self.prepared=dict(signature=signature,source=source,positive=brief,negative='',record=None,professionalized=False)
            return False
        folder=c.data/'intent'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]+'_requirement')
        refs={row['number']:Path(row['path']) for row in source['references']}
        config=dict(c.config)
        self.running=c.running=w.preparing=True;c.cancel_event.clear();w.generate_button.setEnabled(False)
        w.task_display.start();w.progress.setRange(0,0);w.status.setText('正在整理本次需求…')
        def run(emit):
            from .motion_native_backend import release_shared
            release_shared({'url':w.client.url if w.connected else None},cancel=c.cancel_event)
            if source['kind']=='audio':
                if source['audio_kind']=='sfx':
                    from .sfx_prompt import organize
                    return organize(config,brief,source['seconds'],folder,c.cancel_event,emit)
                from .audio_prompt import organize
                return organize(config,brief,source['seconds'],folder,c.cancel_event,emit)
            from .professional_prompt import organize
            return organize(config,brief,'',refs,Path(source['motion']) if source['motion'] else None,folder,c.cancel_event,emit,
                selected_kind='image' if source['kind']=='image' else 'animation',role=source['role'],reference_usage=source['usage'],output_seconds=source['seconds'] or 4.)
        def finish(kind,data):
            if kind in ('audio_stage','intent_stage'):w.status.setText(data['message']);return
            if kind not in ('result','error','cancelled'):return
            self.running=c.running=w.preparing=False
            cancelled=c.cancel_event.is_set() or kind=='cancelled';unchanged=self.signature()==signature
            accepted=kind=='result' and unchanged and not cancelled
            w.task_display.finish('completed' if accepted else 'cancelled' if cancelled else 'failed');w.generation_type_changed()
            write_json(folder/'application.json',dict(accepted=accepted,input_unchanged=unchanged,cancelled=cancelled,status=kind))
            if accepted:
                if source['kind']=='audio':
                    positive,negative=data['positive_prompt'],data['negative_prompt'];extra=dict(english=data['english_caption'],caption_fingerprint=data['caption_fingerprint'])
                else:
                    plan=data['plan'];positive,negative=plan['positive_prompt'],plan['negative_prompt'];extra=dict(english=data.get('english',{}))
                self.prepared=dict(signature=signature,source=source,positive=positive,negative=negative,record=str(folder/'result.json'),professionalized=True,**extra)
                w.status.setText('需求已整理，正在提交生成…');QTimer.singleShot(0,w.enqueue)
            else:w.status.setText('输入已修改，本次旧结果未提交。' if kind=='result' and not cancelled else '需求整理已取消。' if cancelled else '需求整理失败：'+str(data))
        w.launch(run,finish);return True
