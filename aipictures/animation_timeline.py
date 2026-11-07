"""Optional user-authored actions on the output clock; no inferred motion rows."""
import math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView)
from .prompt_timeline import MANUAL_TITLE,remove_owned_timeline


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
        super().__init__();self.window=window;self.suffix='';self.clock='output'
        self.seconds=window.video_controller.seconds.value()
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        heading=QHBoxLayout();self.heading=QLabel('自定义动作 · 成片时间 / 秒');heading.addWidget(self.heading,1)
        self.add=QPushButton('＋ 时段');self.add.clicked.connect(self.add_row);heading.addWidget(self.add)
        self.remove=QPushButton('删除所选');self.remove.clicked.connect(self.delete_selected);heading.addWidget(self.remove)
        layout.addLayout(heading)
        note=QLabel('可选：填写时间和动作，自动同步到提示词；留空时直接跟随参考动画。')
        note.setObjectName('muted');note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['开始 / 秒','结束 / 秒','动作要求'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(True);self.table.setMinimumHeight(200)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.itemChanged.connect(self.edited);layout.addWidget(self.table,1)
        self.remove.setEnabled(False)
        self.table.itemSelectionChanged.connect(lambda:self.remove.setEnabled(bool(self.table.selectedIndexes())))
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error);self.error.hide()
        self.fill([])
        window.video_controller.seconds.valueChanged.connect(self.rescale)

    def raw_rows(self):
        return [[self.table.item(i,j).text().strip() if self.table.item(i,j) else '' for j in range(3)]
                for i in range(self.table.rowCount())]

    def rows(self):
        rows=[]
        for i,values in enumerate(self.raw_rows()):
            if not any(values):continue
            if not all(values):raise ValueError(f'请填写第{i+1}行的开始、结束和动作，或删除该行。')
            rows.append(dict(start=values[0],end=values[1],description=values[2]))
        return validate_rows(rows,self.seconds)

    def effective_rows(self):
        # A manually replaced/removed prompt wins over this editor's old rows.
        if self.suffix and self.suffix not in self.window.positive.toPlainText():return []
        return self.rows()

    def generation_input(self):
        return self.window.positive.toPlainText().strip(),self.effective_rows()

    def fill(self,rows):
        self.table.blockSignals(True);self.table.setRowCount(len(rows)+1)
        for i,row in enumerate(rows):
            for j,value in enumerate((f"{row['start']:.3f}",f"{row['end']:.3f}",row['description'])):
                self.table.setItem(i,j,QTableWidgetItem(value))
        for j in range(3):self.table.setItem(len(rows),j,QTableWidgetItem(''))
        self.table.resizeRowsToContents();self.table.blockSignals(False)

    def add_row(self):
        if any(self.raw_rows()[-1]):
            self.table.blockSignals(True);self.table.insertRow(self.table.rowCount());self.table.blockSignals(False)
        index=self.table.rowCount()-1
        if not self.table.item(index,0):
            self.table.blockSignals(True);self.table.setItem(index,0,QTableWidgetItem(''));self.table.blockSignals(False)
        self.table.setCurrentCell(index,0);self.table.editItem(self.table.item(index,0))

    def delete_selected(self):
        selected=sorted({i.row() for i in self.table.selectedIndexes()},reverse=True)
        if not selected:return
        self.window.intent_controller.animation_mode()
        self.table.blockSignals(True)
        for i in selected:self.table.removeRow(i)
        if not self.table.rowCount():self.table.setRowCount(1)
        self.table.blockSignals(False);self.edited()

    def sync_prompt(self,rows=None):
        """Restore custom actions after explicit appearance prompt generation."""
        if rows is None:rows=self.rows()
        text=self.window.positive.toPlainText()
        if self.suffix and self.suffix in text:text=text.replace(self.suffix,'',1).strip()
        elif rows:text=remove_owned_timeline(text)
        else:text=text.strip()
        self.suffix=('\n\n'+MANUAL_TITLE+'\n'+timeline_text(rows)) if rows else ''
        updated=text+self.suffix
        if updated!=self.window.positive.toPlainText():self.window.positive.setPlainText(updated)

    def edited(self,item=None):
        if item is not None and any(any(values) for values in self.raw_rows()):
            # Editing the animation workspace explicitly selects animation mode.
            self.window.intent_controller.animation_mode()
        try:rows=self.rows()
        except ValueError as exc:self.error.setText(str(exc));self.error.show();return
        self.error.clear();self.error.hide();self.sync_prompt(rows)
        if self.raw_rows() and all(self.raw_rows()[-1]):
            self.table.blockSignals(True);self.table.insertRow(self.table.rowCount());self.table.blockSignals(False)
        self.table.resizeRowsToContents()

    def clear_plan(self):
        if self.suffix and self.suffix in self.window.positive.toPlainText():
            self.window.positive.setPlainText(self.window.positive.toPlainText().replace(self.suffix,'',1).strip())
        self.suffix='';self.fill([]);self.error.clear();self.error.hide()

    def rescale(self,seconds):
        # User-entered seconds are absolute output times, never stretched to fit.
        self.seconds=seconds
        if self.suffix and self.suffix not in self.window.positive.toPlainText():return
        self.edited()
