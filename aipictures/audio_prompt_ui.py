"""One requirement box, explicit organization and an editable Chinese prompt dialog."""
import json
from datetime import datetime
from uuid import uuid4
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import QHBoxLayout,QPushButton,QDialog,QVBoxLayout,QLabel,QPlainTextEdit
from .audio_prompt import fingerprint


class AudioPromptController:
    def __init__(self,audio,layout):
        self.audio=audio;self.window=audio.window;self.draft=None;self.manual_negative='';self.manual_positive='';self.record=None
        row=QHBoxLayout();self.organize=QPushButton('生成专业提示词');self.organize.setObjectName('promptGenerate')
        self.organize.setToolTip('将一句话需求整理成配器、节奏、结构与混音要求；不开始作曲。')
        self.organize.clicked.connect(self.prepare);row.addWidget(self.organize)
        self.edit=QPushButton('查看／编辑提示词');self.edit.clicked.connect(self.open_dialog);row.addWidget(self.edit)
        layout.insertLayout(2,row)
        self.shortcut=QShortcut(QKeySequence('Ctrl+Return'),audio.prompt);self.shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);self.shortcut.activated.connect(self.prepare)
        audio.prompt.textChanged.connect(self.changed);audio.seconds.valueChanged.connect(self.changed)

    def context(self):return self.audio.prompt.toPlainText().strip(),self.audio.seconds.value()

    def state(self):return self.context(),json.dumps(self.draft,sort_keys=True,ensure_ascii=False),self.manual_negative,self.manual_positive

    def changed(self,*_):
        if self.draft and self.context()!=(self.draft['source_brief'],self.draft['seconds']):
            self.audio.note.setText('要求或时长已修改，提示词待更新。')

    def prepare(self):
        w=self.window;c=w.intent_controller;a=self.audio
        if w.preparing or w.current or w.pending:a.note.setText('请等待当前任务结束。');return
        brief,seconds=self.context()
        if not brief or len(brief)>8000:a.note.setText('请填写8000字以内的配乐要求。');return
        if not c.config:a.note.setText('本地提示词助手尚未配置，可先直接填写完整配乐要求。');return
        initial=self.state();folder=c.data/'intent'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]+'_audio_prompt')
        same_brief=not self.draft or self.draft['source_brief']==brief
        exclusions=self.manual_negative if same_brief else '';manual=self.manual_positive if same_brief else ''
        c.running=w.preparing=True;c.cancel_event.clear()
        self.organize.setEnabled(False)
        for button in c.prompt_actions:button.setEnabled(False)
        w.generate_button.setEnabled(False);w.task_display.start();w.progress.setRange(0,0);a.note.setText('正在整理配乐提示词…')
        def run(emit):
            from .motion_native_backend import release_shared
            from .audio_prompt import organize
            release_shared({'url':w.client.url if w.connected else None},cancel=c.cancel_event)
            return organize(c.config,brief,seconds,folder,c.cancel_event,emit,exclusions=exclusions,manual_prompt=manual)
        def finish(kind,data):
            if kind=='audio_stage':w.status.setText(data['message']);return
            if kind not in ('result','error','cancelled'):return
            unchanged=initial==self.state();c.running=w.preparing=False;self.organize.setEnabled(True)
            for button in c.prompt_actions:button.setEnabled(True)
            cancelled=c.cancel_event.is_set() or kind=='cancelled'
            w.task_display.finish('cancelled' if cancelled else 'completed' if kind=='result' else 'failed')
            w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' and not cancelled else 0);w.generation_type_changed()
            if kind=='result' and unchanged and not cancelled:
                self.draft=data;self.manual_positive=manual;self.manual_negative=exclusions;self.record=str(folder/'result.json');a.note.setText('专业配乐提示词已生成。点击“查看／编辑提示词”检查配器、节奏与结构，再生成音频。')
            else:a.note.setText('输入已修改，旧提示词未应用。' if kind=='result' and not cancelled else '提示词整理已取消，原输入保留。' if cancelled else '提示词整理失败：'+str(data))
            QTimer.singleShot(0,w.start_next)
        w.launch(run,finish)

    def snapshot(self):
        brief,seconds=self.context()
        if self.draft:
            if (brief,seconds)!=(self.draft['source_brief'],self.draft['seconds']):
                raise ValueError('配乐要求或时长已修改，请重新生成提示词，或在提示词窗口应用修改。')
            positive=self.draft['positive_prompt'];negative=self.draft['negative_prompt'];english=self.draft.get('english_caption')
            if self.draft.get('caption_fingerprint')!=fingerprint(positive,negative):english=None
        else:positive,negative,english=brief,'',None
        if not positive.strip() or len(positive)>8000 or len(negative)>4000:raise ValueError('配乐提示词为空或过长。')
        return dict(prompt=positive,negative=negative,source_brief=brief,caption_english=english,
            caption_fingerprint=fingerprint(positive,negative),prompt_record=self.record)

    def remember_caption(self,params,caption):
        if not self.draft or not caption:return
        if self.context()!=(params.get('source_brief'),params.get('seconds')):return
        if (self.draft['positive_prompt'],self.draft['negative_prompt'])!=(params.get('prompt'),params.get('negative','')):return
        self.draft['english_caption']=caption
        self.draft['caption_fingerprint']=fingerprint(self.draft['positive_prompt'],self.draft['negative_prompt'])

    def open_dialog(self):
        a=self.audio;d=QDialog(self.window);self.dialog=d;d.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        d.setWindowTitle('配乐提示词');d.resize(680,560);layout=QVBoxLayout(d)
        layout.addWidget(QLabel('配乐提示词'));positive=QPlainTextEdit();positive.setObjectName('audioPositive')
        positive.setPlainText(self.draft['positive_prompt'] if self.draft else a.prompt.toPlainText());layout.addWidget(positive,2)
        layout.addWidget(QLabel('避免内容'));negative=QPlainTextEdit();negative.setObjectName('audioAvoid')
        negative.setPlainText(self.draft['negative_prompt'] if self.draft else '');layout.addWidget(negative,1)
        note=QLabel('避免内容会与音乐要求一起提交。应用修改后，按当前所选时长生成。');note.setWordWrap(True);layout.addWidget(note)
        apply=QPushButton('应用修改');layout.addWidget(apply)
        def done():
            p=positive.toPlainText().strip();n=negative.toPlainText().strip()
            if not p or len(p)>8000 or len(n)>4000:note.setText('配乐提示词须为1–8000字，避免内容最多4000字。');return
            old=self.draft or {};same=(p,n)==(old.get('positive_prompt'),old.get('negative_prompt'))
            if p!=old.get('positive_prompt',''):self.manual_positive=p
            if n!=old.get('negative_prompt',''):self.manual_negative=n
            brief,seconds=self.context();self.draft=dict(positive_prompt=p,negative_prompt=n,source_brief=brief,seconds=seconds,
                english_caption=old.get('english_caption') if same else None,caption_fingerprint=fingerprint(p,n))
            a.note.setText('已应用提示词修改。');d.close()
        apply.clicked.connect(done);d.show();d.raise_();d.activateWindow()
