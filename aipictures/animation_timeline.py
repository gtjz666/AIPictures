"""Editable target actions on the output clock; source evidence keeps its own PTS."""
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView
from .prompt_timeline import remove_owned_timeline,remove_generated_summary
from .motion_timing import clip_rows,source_to_output


def validate_rows(rows: list[dict], seconds: float) -> list[dict]:
    clean=[];previous=0.
    for i,row in enumerate(rows):
        try:
            start,end=float(row['start']),float(row['end']);text=row['description'].strip()
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            raise ValueError(f'动作说明第{i+1}行需要有效时间和文字。') from exc
        if not all(math.isfinite(v) for v in (start,end)) or not 0<=start<end<=seconds+.002 or start<previous-.002:
            raise ValueError(f'动作说明第{i+1}行时间应顺序排列、不重叠，并在0–{seconds:g}秒内。')
        if not text or len(text)>1200:raise ValueError(f'请填写第{i+1}行动作，限1200字。')
        clean.append(dict(start=start,end=end,description=text));previous=end
    return clean


def timeline_text(rows: list[dict]) -> str:
    return '\n'.join(f"{r['start']:.3f}–{r['end']:.3f}秒：{' '.join(r['description'].split())}" for r in rows)


class ActionTimeline(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.suffix='';self.clock='output';self.seconds=window.video_controller.seconds.value()
        self.source_rows=[];self.selection=None;self.review_intervals=[]
        self.output_edits=None;self.edit_seconds=0.
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.heading=QLabel('动作说明 · 输出时间 / 秒');layout.addWidget(self.heading)
        self.review_note=QLabel();self.review_note.setWordWrap(True);layout.addWidget(self.review_note);self.review_note.hide()
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['开始','结束','动作'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setWordWrap(True);self.table.setMinimumHeight(200)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.itemChanged.connect(self.edited);layout.addWidget(self.table,1)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error);self.hide()
        window.video_controller.seconds.valueChanged.connect(self.rescale)
        window.video_controller.motion.start.valueChanged.connect(self.selection_changed)
        window.video_controller.motion.repeat.toggled.connect(self.selection_changed)

    def current_selection(self):
        motion=self.window.video_controller.motion
        return (str(motion.path),motion.start.value(),motion.repeat.isChecked())

    def rows(self):
        rows=[]
        for i in range(self.table.rowCount()):
            values=[self.table.item(i,j).text() if self.table.item(i,j) else '' for j in range(3)]
            rows.append(dict(start=values[0],end=values[1],description=values[2]))
        if self.selection is not None and self.current_selection()!=self.selection:
            raise ValueError('参考起点或循环方式已更改，请重新分析动作；已有修改保留。')
        return validate_rows(rows,self.window.video_controller.seconds.value())

    def effective_rows(self):
        # Manual prompt edits have priority. A removed/replaced timeline footer
        # must not survive invisibly in per-segment generation parameters.
        if self.suffix and self.suffix not in self.window.positive.toPlainText():return []
        return self.rows()

    def fill(self,rows):
        self.table.blockSignals(True);self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate((f"{row['start']:.3f}",f"{row['end']:.3f}",row['description'])):
                self.table.setItem(i,j,QTableWidgetItem(value))
        self.table.resizeRowsToContents();self.table.blockSignals(False)

    def load_plan(self,result):
        self.clear_plan();rows=result['plan']['timeline']
        if not rows or result['plan']['kind']!='animation':return
        current=self.window.positive.toPlainText()
        if current.strip()==result['plan'].get('positive_prompt','').strip():
            self.window.positive.setPlainText(remove_generated_summary(current,rows))
        self.seconds=self.window.video_controller.seconds.value()
        motion=self.window.video_controller.motion
        self.clock='output';self.heading.setText('动作说明 · 输出时间 / 秒')
        if motion.path:
            self.source_rows=[dict(r) for r in rows];self.selection=self.current_selection()
            observed=result.get('reference_timeline',[])
            if observed and self.source_rows[-1]['end']>=observed[-1]['start']-.001:
                # Include the final held frame through the recorded source end.
                self.source_rows[-1]['end']=motion.meta['duration']
            self.source_rows=validate_rows(self.source_rows,motion.meta['duration'])
            self.source_seconds=motion.meta['duration']
            mapped=self.project(self.seconds)
        else:
            span=max(r['end'] for r in rows)
            if span<=0:return
            mapped=[dict(r,start=r['start']/span*self.seconds,end=r['end']/span*self.seconds) for r in rows]
        self.fill(mapped);self.setVisible(bool(mapped));self.edited()
        self.review_intervals=result.get('motion_review_intervals',[]);self.highlight_reviews(mapped)

    def project(self,seconds):
        return source_to_output(self.source_rows,self.source_seconds,seconds,
                                start=self.selection[1],repeat=self.selection[2])

    def highlight_reviews(self,mapped):
        reviews=self.review_intervals
        self.review_note.clear();self.review_note.hide()
        if self.selection is not None and reviews:
            reviews=source_to_output([dict(r,description='待核对') for r in reviews],self.source_seconds,self.seconds,
                                     start=self.selection[1],repeat=self.selection[2],hold_tail=False)
        if reviews:
            from PySide6.QtGui import QColor
            self.review_note.setText(f'{len(reviews)}处细小动作待核对；采样间的轨迹不代表逐帧真值。');self.review_note.show()
            for i,row in enumerate(mapped):
                if any(row['start']<r['end'] and row['end']>r['start'] for r in reviews):
                    for j in range(3):self.table.item(i,j).setBackground(QColor('#fff4d6'))

    def edited(self,item=None):
        try:rows=self.rows()
        except ValueError as exc:self.error.setText(str(exc));self.error.show();return
        self.error.clear();self.error.hide()
        if item is not None and self.source_rows:
            # Preserve manual output-time edits when shortening then extending.
            future=clip_rows(self.output_edits or [],self.seconds,self.edit_seconds)
            self.output_edits=rows+future;self.edit_seconds=max(self.edit_seconds,self.seconds)
        prompt=remove_owned_timeline(self.window.positive.toPlainText())
        self.suffix=('\n\n以下为可编辑动作时间线，以此处时序为准：\n'+
            timeline_text(rows)) if rows else ''
        updated=prompt+self.suffix
        if updated!=self.window.positive.toPlainText():self.window.positive.setPlainText(updated)

    def clear_plan(self):
        self.review_note.clear();self.review_note.hide()
        if self.suffix:
            prompt=self.window.positive.toPlainText()
            self.window.positive.setPlainText(remove_owned_timeline(prompt))
        self.suffix='';self.clock='output';self.source_rows=[];self.selection=None;self.review_intervals=[]
        self.output_edits=None;self.edit_seconds=0.
        self.table.blockSignals(True);self.table.setRowCount(0);self.table.blockSignals(False)
        self.error.clear();self.hide()

    def selection_changed(self,*_):
        if self.table.rowCount():self.edited()

    def rescale(self,seconds):
        old=self.seconds;self.seconds=seconds
        if not self.table.rowCount() or old<=0:return
        # A replaced prompt is authoritative; changing duration cannot reinsert
        # the editor's old hidden footer.
        if self.suffix and self.suffix not in self.window.positive.toPlainText():return
        try:rows=validate_rows([dict(start=self.table.item(i,0).text(),end=self.table.item(i,1).text(),description=self.table.item(i,2).text())
                               for i in range(self.table.rowCount())],old)
        except ValueError:self.edited();return
        if self.source_rows:
            mapped=self.project(seconds)
            if self.output_edits is not None:
                mapped=clip_rows(self.output_edits,0.,seconds)+clip_rows(mapped,self.edit_seconds,seconds)
            self.fill(mapped);self.highlight_reviews(mapped);self.edited();return
        self.fill([dict(r,start=r['start']/old*seconds,end=r['end']/old*seconds) for r in rows]);self.edited()
