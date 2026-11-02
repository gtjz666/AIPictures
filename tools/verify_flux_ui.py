"""One real Qt reference edit and user save; no cloud calls or other jobs cancelled."""
import argparse
import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from PIL import Image

from aipictures.app import Window, create_application
from aipictures.engine import ComfyClient
from aipictures.image_family import restore
from aipictures.result_cache import ResultCache
from aipictures.storage import DATA, write_json
from aipictures.workflow_library import digest


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.output.resolve();reference=args.reference.resolve()
    if root.exists():raise ValueError('目标已有记录，不重复生成。')
    if not reference.is_file():raise ValueError('参考图不存在。')
    client=ComfyClient();queue=client.request('/queue')
    if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('共享后端有任务，暂不开始验收。')
    info=client.discover();before=digest(reference)
    root.mkdir(parents=True);shutil.copy2(DATA/'flux-klein-settings.json',root/'flux-klein-settings.json')
    app=create_application([])
    with patch('aipictures.app.DATA',root),patch('aipictures.storage.DATA',root),\
         patch.object(Window,'auto_connect_engine'),patch.object(Window,'restore_chat'),patch.object(Window,'refresh_stats'):
        w=Window();w.timer.stop();w.cache_store=ResultCache(root)
        w.client=client;w.info=info;w.connected=True
        if w.api_controller.cloud or w.api_controller.settings.smart:
            raise ValueError('验收必须为本地直接生图，不调用额外分析API。')
        restore(w);w.set_reference(str(reference))
        assert w.model_family.currentData()=='flux_klein' and w.preview_role=='reference'
        w.width.setValue(768);w.height.setValue(1024)
        w.seed_mode.setCurrentIndex(w.seed_mode.findData('fixed'));w.seed.setText('20261103')
        prompt='将参考图中的同一位角色改为正面全身站立，面向镜头，双手自然下垂，两脚分开。将白色无袖衬衫改为天蓝色无袖衬衫，保留黑色领结。保持紫色盘发、绿色眼睛、黑色短裤、黑色长袜、黑色皮鞋和原有二维动漫画风。浅灰纯色背景，头部和双脚完整入镜，只画一个人物。'
        w.positive.setPlainText(prompt);w.negative.setPlainText('多余人物，多余肢体，水印，模糊')
        w.api_controller.apply_mode();w.show();QTest.qWait(20)
        assert w.generate_button.isEnabled()
        QTest.mouseClick(w.generate_button,Qt.MouseButton.LeftButton)
        started=time.monotonic();last=''
        while w.preparing or w.current or w.pending or w.workers:
            app.processEvents();QTest.qWait(20)
            if time.monotonic()-started>1800:
                w.cancel_current();raise TimeoutError('界面验收等待超过30分钟，已请求取消自己的任务；原记录保留。')
            status=w.status.text()
            if status!=last:print(status,flush=True);last=status
        if not w.output or not Path(w.output).is_file():
            raise ValueError('界面未得到图片：'+w.chat.toPlainText()[-2000:])
        assert w.preview_role=='result' and w.actual_seed.text()=='20261103'
        folder=Path(w.output).parent;job=json.loads((folder/'job.json').read_text('utf-8'))
        assert job['status']=='completed' and job['params']['model_family']=='flux_klein'
        assert job['params']['user_prompt']==prompt and not job['params']['edge_smoothing']
        saved=root/'saved_reference_edit.png'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(saved),'PNG')):w.save_as()
        with Image.open(saved) as output,Image.open(w.output) as original:
            assert output.tobytes()==original.tobytes() and output.size==(768,1024)
        assert digest(reference)==before
        w.grab().save(str(root/'image_ui.png'))
        w.open_settings('image');app.processEvents();w.settings_dialogs['image'].grab().save(str(root/'image_settings.png'))
        w.settings_dialogs['image'].hide()
        write_json(root/'acceptance.json',{'status':'passed','actual_qt':True,'actual_inference':True,
            'model_family':'flux_klein','reference_sha256':before,'original_unchanged':True,
            'job':str(folder),'image':str(w.output),'saved':str(saved),'saved_pixels_identical':True,
            'seed':20261103,'elapsed_seconds':round(time.monotonic()-started,2),
            'translation':False,'analysis_model':False,'cloud_calls':False})
        w.close();app.processEvents()
    print('REAL_FLUX_QT_ACCEPTANCE_PASS',flush=True)


if __name__=='__main__':main()
