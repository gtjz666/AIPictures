"""Explicit pixel asset options and nearest-neighbour sheet preview."""
import json
import zipfile
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel,
    QSpinBox, QComboBox, QLineEdit, QPushButton, QCheckBox, QDialogButtonBox, QFileDialog, QMessageBox)

from sprite_pipeline import PipelineConfig


class SpriteExportDialog(QDialog):
    def __init__(self, parent, manifest):
        super().__init__(parent)
        self.manifest = manifest
        self.setWindowTitle('导出像素精灵素材'); self.resize(530, 470)
        layout = QVBoxLayout(self)
        note = QLabel('独立处理每帧，不混合前后帧。优先使用缩放、校色前的透明帧。\n像素捕捉 → 锚点归一化 → 共享调色板 → 拼图 → 验收。')
        note.setWordWrap(True); layout.addWidget(note)
        form = QFormLayout(); layout.addLayout(form)
        self.width = QSpinBox(); self.width.setRange(1, 16384); self.width.setValue(96)
        self.height = QSpinBox(); self.height.setRange(1, 16384); self.height.setValue(128)
        canvas = QHBoxLayout(); canvas.addWidget(self.width); canvas.addWidget(QLabel('×')); canvas.addWidget(self.height)
        form.addRow('单帧画布（像素）', canvas)
        for control in (self.width,self.height): control.setToolTip('像素捕捉后的真实单帧尺寸；不足处补透明边，默认不缩放。')
        self.grid = QComboBox(); self.grid.addItem('自动识别（失败回退 1）', 'auto')
        for size in (1, 2, 3, 4, 6, 8, 12, 16): self.grid.addItem(f'{size} × {size} → 1 像素', size)
        self.grid.setCurrentIndex(self.grid.findData(8)); self.grid.setEditable(False)
        self.grid.setToolTip('整段共用一个像素格。8 会把 480×640 帧捕捉为 60×80；这不是模型自动补画。')
        form.addRow('源图像素格', self.grid)
        self.palette = QSpinBox(); self.palette.setRange(1, 256); self.palette.setValue(24); form.addRow('调色板颜色数', self.palette)
        self.palette.setToolTip('整段共享色板，非透明 RGB 色数上限；不会理解衣服或皮肤区域。')
        self.anchor_mode = QComboBox()
        for title, mode in [('脚底居中（走路/待机）', 'bottom-center'), ('轮廓居中', 'bbox-center'), ('保留原始位移（跳跃）', 'manual')]: self.anchor_mode.addItem(title, mode)
        if manifest.get('action') == 'jump': self.anchor_mode.setCurrentIndex(2)
        form.addRow('锚点对齐', self.anchor_mode)
        self.anchor_mode.setToolTip('走路可按脚底贴底；跳跃选保留原始位移，避免消除高度。')
        self.offset_x = QSpinBox(); self.offset_y = QSpinBox()
        for control in (self.offset_x, self.offset_y): control.setRange(-16384, 16384)
        offset = QHBoxLayout(); offset.addWidget(self.offset_x); offset.addWidget(self.offset_y)
        form.addRow('手动偏移 dx / dy', offset)
        def manual_changed():
            for control in (self.offset_x,self.offset_y): control.setEnabled(self.anchor_mode.currentData()=='manual')
        self.anchor_mode.currentIndexChanged.connect(manual_changed); manual_changed()
        self.anchor = QLineEdit(); self.anchor.setPlaceholderText('可选；留空则从整段共同提取颜色')
        choose = QPushButton('选择…'); choose.clicked.connect(self.choose_anchor)
        anchor_row = QHBoxLayout(); anchor_row.addWidget(self.anchor, 1); anchor_row.addWidget(choose); form.addRow('调色板锚点图', anchor_row)
        self.threshold = QSpinBox(); self.threshold.setRange(1, 255); self.threshold.setValue(128); form.addRow('透明阈值', self.threshold)
        self.threshold.setToolTip('Alpha 达到阈值变为不透明，其余变为全透明；不保留半透明灰边。')
        self.padding = QSpinBox(); self.padding.setRange(0, 128); self.padding.setValue(1); form.addRow('拼图留白', self.padding)
        self.padding.setToolTip('精灵图外围与格间的透明像素数，不向相邻格扩散颜色。')
        self.columns = QSpinBox(); self.columns.setRange(0, 128); self.columns.setSpecialValueText('自动'); form.addRow('列数', self.columns)
        self.allow_scale = QCheckBox('明确允许缩小超出画布的主体（最近邻）'); self.allow_scale.setChecked(False); form.addRow(self.allow_scale)
        form.addRow(QLabel(f'生成 seed：{manifest.get("seed", "未记录")}；仅记录，不重新生成。'))
        warning = QLabel('调色板对齐不能修复多余肢体、错误花纹或动作。跳跃请保留位移；脚底贴底会消除跳跃高度。')
        warning.setWordWrap(True); layout.addWidget(warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('选择位置并导出…')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def choose_anchor(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择调色板基准图', '', '图片 (*.png *.jpg *.webp)')
        if path: self.anchor.setText(path)

    def configuration(self):
        return PipelineConfig(canvas_width=self.width.value(), canvas_height=self.height.value(),
            anchor_mode=self.anchor_mode.currentData(), manual_offset=(self.offset_x.value(), self.offset_y.value()),
            pixel_size=self.grid.currentData(), palette_size=self.palette.value(), alpha_threshold=self.threshold.value(),
            anchor=self.anchor.text().strip() or None, seed=self.manifest.get('seed'), fps=self.manifest['fps'],
            padding=self.padding.value(), columns=self.columns.value() or None, allow_scale=self.allow_scale.isChecked()).validate()


def start_export(player):
    window = player.window
    if not player.manifest or window.cache_busy: return
    try:
        manifest_path = Path(player.manifest)
        manifest = json.loads(manifest_path.read_text('utf-8'))
        dialog = SpriteExportDialog(window, manifest)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        config = dialog.configuration()
        path, _ = QFileDialog.getSaveFileName(window, '保存像素素材包', 'pixel-sprites.zip', 'ZIP (*.zip)')
        if not path: return
        target = window.cache_store.validate_export(path)
    except (OSError, ValueError, KeyError) as exc:
        QMessageBox.warning(window, '像素导出配置', str(exc)); return
    from .sprite_assets import export_pixel_assets
    window.cache_busy = True; window.assets_dialog.set_cache_busy(True)
    player.pixel_export.setEnabled(False)
    window.status.setText('正在捕捉像素与拼图…')
    def done(kind, data):
        if kind == 'sprite_progress':
            stage, current, total = data
            titles = {'snap':'像素捕捉', 'normalize':'锚点归一化', 'palette':'调色板对齐', 'assemble':'拼图'}
            window.status.setText(f'{titles.get(stage, stage)} {current}/{total}')
            return
        if kind not in ('result', 'error'): return
        window.cache_busy = False; window.assets_dialog.set_cache_busy(False); player.pixel_export.setEnabled(True)
        if kind == 'error':
            window.status.setText('像素导出失败'); QMessageBox.warning(window, '像素导出失败', str(data)); return
        window.cache_store.record_save(target, 'pixel_sprite', manifest_path); window.load_gallery()
        window.status.setText('像素素材已保存，结构验收通过')
        window.add_chat('软件', f'已保存 {data["frame_count"]} 帧像素素材、精灵图、metadata 和验收报告：{target}')
        show_preview(window, target, data['report'])
    window.launch(lambda emit: export_pixel_assets(manifest_path, target, config,
        lambda stage, current, total: emit('sprite_progress', (stage, current, total))), done)


def show_preview(window, target, report):
    from .image_viewer import ImageView
    dialog = QDialog(window); dialog.setWindowTitle('像素精灵图 · 最近邻预览'); dialog.resize(1000, 760)
    layout = QVBoxLayout(dialog); view = ImageView(); view.set_smooth(False)
    with zipfile.ZipFile(target) as archive:
        pixmap = QPixmap(); pixmap.loadFromData(archive.read('sprite_sheet.png'))
    view.load(pixmap); layout.addWidget(view, 1)
    label = QLabel(f'{pixmap.width()}×{pixmap.height()} · 滚轮缩放 / 拖动 · 已保存 ZIP\n' + '\n'.join(report['warnings'][:3]))
    label.setWordWrap(True); layout.addWidget(label)
    close = QPushButton('关闭'); close.clicked.connect(dialog.close); layout.addWidget(close)
    window.sprite_preview = dialog; dialog.show()
