"""One authoritative manual prompt per mode; snapshot only, never run an assistant."""
import hashlib
import json


class GenerationIntent:
    def __init__(self,w,workbench):
        self.window=w;self.workbench=workbench;self.running=False
        self.active_key=None;self.active_editor=None;self.inputs={}
        self.sync_mode()

    def key(self):
        return self.workbench.category if self.workbench.category!='sprite' else self.window.generation_type.currentData()

    def editor(self):
        w=self.window
        return w.audio_controller.prompt if self.workbench.category=='audio' else w.short_video.brief if self.workbench.category=='long_video' else w.positive

    def sync_mode(self):
        key=self.key();editor=self.editor()
        if key==self.active_key:return
        if self.active_editor is not None:self.inputs[self.active_key]=self.active_editor.toPlainText()
        if key in self.inputs:editor.setPlainText(self.inputs[key])
        elif editor is self.active_editor:editor.clear()
        self.active_key=key;self.active_editor=editor

    def snapshot(self):
        w=self.window;category=w.workbench.category;motion=w.video_controller.motion
        kind='audio' if category=='audio' else 'video' if category=='long_video' else 'animation' if w.generation_type.currentData()=='walk' else 'image'
        refs=w.reference_chat.references() if kind!='audio' else {}
        from .image_family import effective_family
        family=effective_family(w) if kind=='image' else None
        from .structure_control import resolve
        choice=w.workbench.structure_choice.currentData()
        error=''
        try:structural=resolve(self.editor().toPlainText().strip(),refs,choice) if kind=='image' and family!='h3_image' else None
        except ValueError as exc:structural=None;error=str(exc)
        return dict(kind=kind,image_family=family,requirement=self.editor().toPlainText().strip(),
            structure_binding=structural,structure_choice=choice if kind=='image' and family!='h3_image' else None,structure_error=error,
            subject_only=bool(structural and structural['structure']!=structural['identity'] and w.workbench.subject_only.isChecked()),
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
        self.sync_mode();source=self.snapshot();text=source['requirement']
        if not text:return None
        return dict(signature=self.signature(source),source=source,positive=text,negative='',record=None,
            professionalized=False,manual=True,english=None,prompt_policy='manual_verbatim_v1')

    def prompts(self):
        self.sync_mode();return self.editor().toPlainText().strip(),''

    def record(self,params):
        if 'requirement_contract' in params:return
        value=self.current()
        if value:
            text=value['positive']
            params.update(source_brief=text,user_prompt=text,user_negative='',requirement_contract=value,prompt_policy='manual_verbatim_v1')

    def validate(self,source,output=''):
        from .multi_reference import image_ids
        brief=source['requirement']
        if source.get('structure_error'):raise ValueError(source['structure_error'])
        if not brief:raise ValueError('请填写提示词，说明内容、风格及参考图用途。')
        if len(brief)>(8000 if source['kind']=='audio' else 16000):raise ValueError('提示词过长，请缩短后生成。')
        if source['kind']!='audio':
            missing=image_ids(brief)-{row['number'] for row in source['references']}
            if missing:raise ValueError('尚未添加'+'、'.join('图'+str(i) for i in sorted(missing))+'。')

    def intercept(self):
        w=self.window
        if w.preparing:return True
        if w.current or w.pending:raise ValueError('请等待当前任务完成，再生成新的内容。')
        self.sync_mode();self.validate(self.snapshot());return False

    def prepare(self):
        # Compatibility for retired shortcuts; never starts text/vision inference.
        self.window.status.setText('请直接填写提示词，再点击生成。')
