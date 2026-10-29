"""Qt rendering acceptance for explicit pixel options and nearest-neighbour preview."""
import json
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMainWindow

from aipictures.sprite_export import SpriteExportDialog,show_preview
from aipictures.sprite_assets import export_pixel_assets
from aipictures.storage import DATA
from sprite_pipeline import PipelineConfig
from PIL import Image,ImageDraw


def main():
    app=QApplication([]); window=QMainWindow(); window.show()
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp); job=root/'job'; job.mkdir()
        image=Image.new('RGBA',(32,40)); ImageDraw.Draw(image).rectangle((8,4,23,35),fill='red'); image.save(job/'frame.png')
        manifest={'status':'completed','frames':[{'image':'frame.png','native_matte':'frame.png'}],'fps':8,'seed':42,'action':'walk'}
        path=job/'sequence.json'; path.write_text(json.dumps(manifest),encoding='utf-8')
        dialog=SpriteExportDialog(window,manifest); dialog.show(); app.processEvents()
        assert not dialog.allow_scale.isChecked()
        assert dialog.anchor.text()==''
        assert dialog.configuration().seed==42
        dialog.grab().save(str(DATA/'sprite-export-options.png')); dialog.close()
        result=export_pixel_assets(path,root/'assets.zip',PipelineConfig(canvas_width=16,canvas_height=20,pixel_size=2,palette_size=4,seed=42))
        show_preview(window,root/'assets.zip',result['report']); app.processEvents()
        preview=window.sprite_preview
        view=preview.findChildren(__import__('aipictures.image_viewer',fromlist=['ImageView']).ImageView)[0]
        assert not view.smooth
        assert view.item.transformationMode()==Qt.TransformationMode.FastTransformation
        view.zoom(2); assert not view.smooth
        preview.grab().save(str(DATA/'sprite-export-preview.png')); preview.close()
        window.close()
    print('Pixel export Qt controls and nearest-neighbour preview passed.')


if __name__=='__main__': main()
