"""Explicit content inspection of selected PNG source frames."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QTableWidget,QTableWidgetItem,QHeaderView


class FrameReview(QWidget):
    def __init__(self,panel):
        super().__init__();self.panel=panel;self.results={}
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['帧','时间 / 秒','帧内容'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self.preview_frame);layout.addWidget(self.table)

    def clear(self):
        self.results={};self.table.setRowCount(0)

    def add_result(self,result):
        row=result['frame_analysis'];self.results[row['index']]=row
        self.table.setRowCount(len(self.results))
        for i,item in enumerate(sorted(self.results.values(),key=lambda r:r['index'])):
            for j,value in enumerate((item['index']+1,f"{item['time']:.3f}",item['description'])):
                self.table.setItem(i,j,QTableWidgetItem(str(value)))
        self.table.resizeRowsToContents()

    def preview_frame(self,row,column):
        if self.panel.is_frames():self.panel.range_slider.setValue(int(self.table.item(row,0).text())-1)
