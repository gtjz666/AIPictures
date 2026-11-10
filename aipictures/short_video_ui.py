"""Requirements -> explicit storyboard -> reviewed prompts; no automatic rerolls."""
import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QPushButton,QComboBox,
    QFileDialog,QDialog,QTableWidget,QTableWidgetItem,QLineEdit,QHeaderView)
from . import video_script


class ShortVideoPanel(QWidget):
    def __init__(self,window,kind):
        super().__init__();self.window=window;self.kind=kind;self.script=None;self.music_file=None
        self.script_brief=None;self.generated_negative=None;self.manual_negative=''
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        layout.addWidget(QLabel('视频要求'))
        self.brief=QPlainTextEdit();self.brief.setMaximumHeight(100)
        self.brief.setPlaceholderText('描述画面、情节、镜头与声音，例如：清晨湖面的小船缓慢前行，镜头轻推，配舒缓旋律。')
        layout.addWidget(self.brief)
        row=QHBoxLayout();self.music=QComboBox()
        for key,title in video_script.STYLES.items():self.music.addItem('H3配乐 · '+title,key)
        self.music.activated.connect(self.reset_music)
        row.addWidget(self.music,1);self.import_music=QPushButton('导入配乐…');self.import_music.clicked.connect(self.choose_music);row.addWidget(self.import_music)
        layout.addLayout(row)
        self.audio_note=QLabel('由H3同步生成画面、原声与配乐，也可导入自己的配乐。');self.audio_note.setWordWrap(True);layout.addWidget(self.audio_note)
        row=QHBoxLayout();self.organize=QPushButton('生成脚本与提示词');self.organize.setObjectName('promptGenerate');self.organize.clicked.connect(self.prepare)
        self.edit=QPushButton('查看／修改脚本');self.edit.clicked.connect(self.open_script)
        row.addWidget(self.organize);row.addWidget(self.edit);layout.addLayout(row)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note);layout.addStretch(1)
        self.edit_hint=QLabel('参考视频编辑 · 试用（2–8秒）\n用图1、图2等编号说明人物、服装和画风的用途。画风和细小动作仍可能偏离参考；长片续接有场景跳变，暂不开放。')
        self.edit_hint.setWordWrap(True);layout.insertWidget(layout.count()-1,self.edit_hint);self.edit_hint.hide()
        from PySide6.QtGui import QShortcut,QKeySequence
        self.send_shortcut=QShortcut(QKeySequence('Ctrl+Return'),self.brief);self.send_shortcut.activated.connect(self.prepare)

    def active(self):return self.kind.currentData() in ('short_video','long_video') and self.window.generation_type.currentData()=='walk'

    def reset_music(self):
        self.music_file=None;self.audio_note.setText('由H3同步生成原声与配乐；导出可分离音频和画面。')
        if self.script:
            current=self.window.positive.toPlainText().strip()
            automatic=current==video_script.prompt(self.script).strip()
            self.script=dict(self.script,music_style=self.music.currentData())
            if automatic:self.window.positive.setPlainText(video_script.prompt(self.script))

    def choose_music(self):
        path,_=QFileDialog.getOpenFileName(self,'选择配乐','','音频 (*.wav *.mp3 *.flac *.m4a *.ogg)')
        if not path:return
        try:
            if Path(path).stat().st_size>200*1024**2:raise ValueError('配乐文件不能超过200MB。')
            from .video_audio import read_audio
            read_audio(path,.1);self.music_file=path
            self.audio_note.setText('已导入配乐：'+Path(path).name+'；重新选择自动配乐类型可恢复自动制作。')
        except Exception as e:self.note.setText(str(e))

    def fingerprint(self):
        w=self.window
        refs=tuple((n,str(p),p.stat().st_size if p.is_file() else None,p.stat().st_mtime_ns if p.is_file() else None) for n,p in w.reference_chat.references().items())
        return (self.brief.toPlainText(),w.video_controller.seconds.value(),self.music.currentData(),self.music_file,str(w.reference_path),self.active(),
                refs,str(w.video_controller.motion.path),w.positive.toPlainText(),w.negative.toPlainText())

    def prepare(self):
        w=self.window;c=w.intent_controller
        if w.preparing or w.current or w.pending:self.note.setText('请等待当前任务结束。');return
        editing=self.kind.currentData()=='long_video' and bool(w.video_controller.motion.path)
        if w.reference_chat.extra and not editing:self.note.setText('多张参考图目前用于单张图片或参考视频编辑，请先添加源视频。');return
        brief=self.brief.toPlainText().strip() or w.positive.toPlainText().strip()
        if not brief:self.note.setText('请先描述视频要求。');return
        if len(brief)>16000:self.note.setText('视频要求请控制在16000字以内。');return
        if not c.config and not editing:self.note.setText('本地创作助手未配置，可直接填写要求生成单镜头视频。');return
        negative=w.negative.toPlainText().strip()
        if negative==self.generated_negative:negative=self.manual_negative
        seconds=w.video_controller.seconds.value();style=self.music.currentData();reference=w.reference_path
        initial=self.fingerprint();folder=c.data/'intent'/(datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid4().hex[:8]+'_script')
        references=w.reference_chat.references()
        c.running=w.preparing=True;c.cancel_event.clear();self.organize.setEnabled(False)
        for button in c.prompt_actions:button.setEnabled(False)
        w.generate_button.setEnabled(False);w.task_display.start();w.progress.setRange(0,0);self.note.setText('正在整理视频脚本…')
        def run(emit):
            if editing:
                from .video_edit import organize
                return organize(c.config,brief,seconds,style,references,folder,c.cancel_event,emit,exclusions=negative)
            from .motion_native_backend import release_shared
            release_shared({'url':w.client.url if w.connected else None},cancel=c.cancel_event)
            return video_script.organize(c.config,brief,seconds,style,reference,folder,c.cancel_event,emit,exclusions=negative)
        def finish(kind,data):
            if kind=='intent_stage':w.status.setText(data['message']);return
            if kind not in ('result','error','cancelled'):return
            c.running=w.preparing=False;self.organize.setEnabled(True)
            for button in c.prompt_actions:button.setEnabled(True)
            w.task_display.finish('completed' if kind=='result' else 'cancelled' if c.cancel_event.is_set() else 'failed')
            w.generation_type_changed()
            if kind=='result' and initial==self.fingerprint() and not c.cancel_event.is_set():
                if negative and negative not in data['negative_prompt']:data=dict(data,negative_prompt=data['negative_prompt']+'\n'+negative)
                self.manual_negative=negative
                self.apply(data);self.note.setText('脚本与提示词已更新，可查看修改后生成。')
            else:self.note.setText('要求已修改，旧脚本未应用。' if kind=='result' else '脚本未完成：'+str(data))
        w.launch(run,finish)

    def apply(self,script,replace_negative=True):
        self.script=script;self.script_brief=self.brief.toPlainText();self.window.positive.setPlainText(video_script.prompt(script))
        if replace_negative:
            self.generated_negative=script.get('negative_prompt','主体结构异常，非预期闪烁')
            self.window.negative.setPlainText(self.generated_negative)

    def snapshot(self):
        w=self.window;seconds=w.video_controller.seconds.value()
        if self.script and self.script_brief is not None and self.script_brief!=self.brief.toPlainText() and w.positive.toPlainText().strip()==video_script.prompt(self.script).strip():
            raise ValueError('视频要求已修改，请重新生成脚本，或直接修改提示词后再生成。')
        current=self.script or video_script.simple(self.brief.toPlainText().strip() or w.positive.toPlainText().strip(),seconds,self.music.currentData(),w.negative.toPlainText())
        current=dict(current,music_style=self.music.currentData());video_script.validate(current,seconds)
        return json.loads(json.dumps(current))

    def open_script(self):
        # Invalid timing blocks submission, but must remain editable for repair.
        try:script=json.loads(json.dumps(self.script)) if self.script else self.snapshot()
        except ValueError as e:self.note.setText(str(e));return
        d=QDialog(self.window);d.setWindowTitle('视频脚本');d.resize(920,560);layout=QVBoxLayout(d)
        title=QLineEdit(script['overview']);layout.addWidget(title)
        table=QTableWidget(len(script['shots']),5);table.setHorizontalHeaderLabels(['起点 / 秒','终点 / 秒','画面与动作','镜头','声音'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i,row in enumerate(script['shots']):
            for j,key in enumerate(('start','end','visual','camera','sound')):table.setItem(i,j,QTableWidgetItem(str(row[key])))
        layout.addWidget(table,1);note=QLabel(f'镜头须从0秒连续覆盖本次片长：{self.window.video_controller.seconds.value():g}秒。');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();add=QPushButton('添加镜头');add.clicked.connect(lambda:table.insertRow(table.rowCount()));row.addWidget(add)
        remove=QPushButton('删除所选');remove.clicked.connect(lambda:table.removeRow(table.currentRow()));row.addWidget(remove)
        apply=QPushButton('应用脚本与提示词');row.addWidget(apply);layout.addLayout(row)
        def done():
            try:
                shots=[]
                for i in range(table.rowCount()):
                    values=[table.item(i,j).text().strip() if table.item(i,j) else '' for j in range(5)]
                    shots.append(dict(start=float(values[0]),end=float(values[1]),visual=values[2],camera=values[3],sound=values[4]))
                result=dict(script,overview=title.text(),shots=shots,duration_seconds=self.window.video_controller.seconds.value())
                video_script.validate(result,self.window.video_controller.seconds.value());self.apply(result,replace_negative=False);d.accept()
            except (ValueError,TypeError) as e:note.setText(str(e))
        apply.clicked.connect(done);d.exec()
