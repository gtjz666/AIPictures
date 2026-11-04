"""Editable target actions: source clock for motion guides, output clock otherwise."""
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView
from .prompt_timeline import remove_owned_timeline,remove_generated_summary


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
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.heading=QLabel('动作说明 · 输出时间 / 秒');layout.addWidget(self.heading)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['开始','结束','动作'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setWordWrap(True);self.table.setMinimumHeight(200)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.itemChanged.connect(self.edited);layout.addWidget(self.table,1)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error);self.hide()
        window.video_controller.seconds.valueChanged.connect(self.rescale)

    def rows(self):
        rows=[]
        for i in range(self.table.rowCount()):
            values=[self.table.item(i,j).text() if self.table.item(i,j) else '' for j in range(3)]
            rows.append(dict(start=values[0],end=values[1],description=values[2]))
        motion=self.window.video_controller.motion
        limit=motion.meta['duration'] if self.clock=='source' and motion.meta else self.window.video_controller.seconds.value()
        return validate_rows(rows,limit)

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
        self.clock='source' if motion.path else 'output'
        self.heading.setText('动作说明 · 参考时间 / 秒' if motion.path else '动作说明 · 输出时间 / 秒')
        repeating=motion.path and motion.repeat.isChecked()
        start=motion.start.value() if motion.path and not repeating else 0.
        end=(motion.meta['duration'] if repeating else min(start+self.seconds,motion.meta['duration'])) if motion.path else max(r['end'] for r in rows)
        span=end-start
        if span<=0:return
        # Source descriptions have already been retargeted by the planner.
        mapped=[]
        for r in rows:
            a=max(start,r['start']);b=min(end,r['end'])
            if b>a:mapped.append(dict(start=a if motion.path else a/span*self.seconds,
                end=b if motion.path else b/span*self.seconds,description=r['description']))
        observed=result.get('reference_timeline',[])
        if mapped and motion.path and observed and mapped[-1]['end']>=observed[-1]['start']-.001:
            # The source's final frame remains displayed until its recorded end PTS.
            mapped[-1]['end']=end
        self.fill(mapped);self.setVisible(bool(mapped));self.edited()

    def edited(self,*_):
        try:rows=self.rows()
        except ValueError as exc:self.error.setText(str(exc));self.error.show();return
        self.error.clear();self.error.hide()
        prompt=remove_owned_timeline(self.window.positive.toPlainText())
        self.suffix=('\n\n以下为可编辑动作时间线，以此处时序为准：\n'+
            ('时间为参考素材秒数；按选定起点播放，启用循环时按此顺序重复。\n' if self.clock=='source' else '')+timeline_text(rows)) if rows else ''
        updated=prompt+self.suffix
        if updated!=self.window.positive.toPlainText():self.window.positive.setPlainText(updated)

    def clear_plan(self):
        if self.suffix:
            prompt=self.window.positive.toPlainText()
            self.window.positive.setPlainText(remove_owned_timeline(prompt))
        self.suffix='';self.clock='output';self.table.setRowCount(0);self.error.clear();self.hide()

    def rescale(self,seconds):
        old=self.seconds;self.seconds=seconds
        if not self.table.rowCount() or old<=0 or self.clock=='source':return
        try:rows=validate_rows([dict(start=self.table.item(i,0).text(),end=self.table.item(i,1).text(),description=self.table.item(i,2).text())
                               for i in range(self.table.rowCount())],old)
        except ValueError:return
        self.fill([dict(r,start=r['start']/old*seconds,end=r['end']/old*seconds) for r in rows]);self.edited()
