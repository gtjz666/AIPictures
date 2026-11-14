"""Native H3 image jobs in the same serial desktop queue."""
import secrets
import json
import shutil
import threading
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QListWidgetItem
from . import h3_image as h3
from .storage import new_job,write_json
from .workflow_library import digest


class H3ImageController:
    def __init__(self,window):self.window=window

    def restore_choice(self):
        w=self.window
        try:
            saved=json.loads((w.api_controller.data/'image-family.json').read_text('utf-8'))
            if saved.get('family')=='h3_image' and not w.api_controller.cloud and h3.settings(w.api_controller.data):
                w.model_family.setCurrentIndex(w.model_family.findData('h3_image'))
        except (ValueError,OSError):pass

    def active(self):
        w=self.window
        from .image_family import effective_family
        return not w.api_controller.cloud and w.generation_type.currentData()!='walk' and effective_family(w)=='h3_image'

    def intercept(self):
        if not self.active():return False
        w=self.window;c=h3.settings(w.api_controller.data)
        if not c:raise ValueError('H3图片引擎尚未安装并验证；不会改用其他模型。')
        if w.custom_graph is not None:raise ValueError('H3图片使用独立工作流，请将后台预设恢复为自动选择。')
        from .prompt_language import texts
        positive,negative=texts(w)
        if negative.strip():raise ValueError('H3图片没有独立反向条件，请将排除要求写入下方提示词。')
        refs=w.reference_chat.references();seed=int(w.seed.text())
        if seed==-1:seed=secrets.randbelow(2**53)
        width,height=w.width.value(),w.height.value();h3.validate(width,height,seed,refs)
        prompt=h3.instruction(positive,refs)
        params=dict(mode='h3_image',backend='standalone',model_family='h3_image',template='MiniMax H3 Image',positive=prompt,negative='',
            seed=seed,width=width,height=height,steps=6,cfg=1.,sampler='euler',scheduler='simple',denoise=1.,
            protocol=h3.PROTOCOL,h3_image_settings=c,url=w.client.url if w.connected else None,
            display_prompt=w.generation_intent.prompts()[0],user_prompt=w.positive.toPlainText(),references={},
            output_background=w.output_background.currentData(),reference_policy='native_picture_conditions',prompt_expander=False)
        if hasattr(w,'generation_intent'):w.generation_intent.record(params)
        # Snapshot graph and files before queueing, so later GUI edits cannot change
        # a running job. The exact three executed graphs are saved by the runtime.
        graph=h3.encode_graph(c,prompt,width,height,[f'reference_{i}.png' for i in range(1,len(refs)+1)])
        folder=new_job(graph,params)
        for i,(n,path) in enumerate(refs.items(),1):
            sha=digest(path);target=folder/'references'/f'{n}{path.suffix.lower()}';target.parent.mkdir(exist_ok=True)
            shutil.copyfile(path,target)
            if digest(target)!=sha:raise ValueError('参考图复制校验失败，未入队。')
            params['references'][n]=dict(path=str(target),source=str(path),sha256=sha,model_input=i)
        write_json(folder/'job.json',dict(schema_version=1,kind='image',status='created',params=params),durable=True)
        item=QListWidgetItem('H3图片 · 等待');item.setToolTip(str(folder));w.queue_list.addItem(item)
        w.pending.append((graph,params,folder,item));w.start_next();return True

    def cancel(self):
        w=self.window
        if not w.current or w.current['params'].get('mode')!='h3_image':return False
        w.current['cancel'].set();w.status.setText('正在停止本次H3图片进程…');return True

    def start(self,params,folder,item):
        w=self.window;cancel=threading.Event()
        w.current=dict(folder=folder,params=params,cancel=cancel,client=None)
        w.connect_button.setEnabled(False);item.setText('H3图片 · 制作中');w.task_display.start();w.progress.setRange(0,0)
        def save(status,error=None):write_json(folder/'job.json',dict(schema_version=1,kind='image',status=status,params=params,error=error),durable=True)
        save('running')
        def event(kind,data):
            if kind=='h3_image_process':
                if w.current:w.current.update(process_pid=data['pid'],owned_job=data['owner'])
            elif kind=='h3_image_stage':w.status.setText(data['message']);w.progress.setRange(0,0)
            elif kind=='progress':
                w.progress.setRange(0,100);w.progress.setValue(round(100*data['value']/max(1,data['max'])))
            elif kind in ('result','error','cancelled'):
                status={'result':'completed','error':'failed','cancelled':'cancelled'}[kind]
                save(status,None if kind=='result' else str(data));w.current=None;w.task_display.finish(status)
                w.progress.setRange(0,100);w.progress.setValue(100 if kind=='result' else 0);w.connect_button.setEnabled(True)
                item.setText('H3图片 · '+{'result':'完成','error':'失败','cancelled':'取消'}[kind])
                if kind=='result':w.show_image(data['images'][0]);w.status.setText('H3图片生成完成。')
                else:w.status.setText('H3图片'+('已取消：' if kind=='cancelled' else '失败：')+str(data))
                w.load_gallery();w.generation_type_changed();QTimer.singleShot(0,w.start_next)
        from .h3_image_runtime import generate
        w.launch(lambda emit:generate(folder,params,cancel,emit),event)
