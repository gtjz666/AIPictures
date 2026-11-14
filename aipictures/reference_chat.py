"""Numbered reference gallery and explicit conversation, independent of results."""
import html
import json
import secrets
import shutil
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps
from PySide6.QtWidgets import QFileDialog, QTextBrowser

from . import flux_klein, multi_reference
from .engine import Cancelled
from .reference_input import opaque_reference
from .workflow import ImageRequest
from .workflow_library import digest


class ReferenceChat:
    def __init__(self, window):
        self.window = window
        self.data = window.api_controller.data
        self.extra = {}
        self.messages = []
        self.view = QTextBrowser(window); self.view.hide()
        self.view.setOpenExternalLinks(False)

    def references(self):
        refs = {1: Path(self.window.reference_path)} if self.window.reference_path else {}
        refs.update(self.extra)
        return dict(sorted(refs.items()))

    def active(self):
        return (bool(self.extra) or bool(self.structural_binding())) and self.window.generation_type.currentData() != 'walk'

    def structural_binding(self,strict=False):
        w=self.window
        if w.generation_type.currentData()=='walk':return None
        from .image_family import effective_family
        if effective_family(w)=='h3_image':return None
        from .structure_control import resolve
        choice=w.workbench.structure_choice.currentData() if hasattr(w,'workbench') and hasattr(w.workbench,'structure_choice') else 'auto'
        try:return resolve(w.positive.toPlainText(),self.references(),choice)
        except ValueError:
            if strict:raise
            return None

    def append(self, role, text):
        self.messages.append(dict(role=role, text=text)); self.messages = self.messages[-20:]
        self.view.append('<p><b>'+html.escape(role)+'</b> '+html.escape(text).replace('\n', '<br>')+'</p>')
        if len(self.messages) == 20:
            self.view.setHtml(''.join('<p><b>'+html.escape(m['role'])+'</b> '+html.escape(m['text']).replace('\n','<br>')+'</p>' for m in self.messages))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def choose(self, number):
        path, _ = QFileDialog.getOpenFileName(self.window, f'添加图{number}', '', 'Images (*.png *.jpg *.jpeg *.webp *.bmp)')
        if path:self.import_images([Path(path)], number=number)

    @staticmethod
    def validate(path):
        path = Path(path)
        if path.stat().st_size > 30*1024**2: raise ValueError('参考图不能超过30MB。')
        with Image.open(path) as image:
            if image.width*image.height > 40_000_000 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('这里请添加静态参考图；GIF或视频请放到参考动画区域。')
            image.verify()

    def import_images(self, paths, *, number=None):
        w = self.window
        try:
            if w.preparing:raise ValueError('请等待素材准备或识别结束后更换参考图。')
            refs = self.references()
            limit=self.limit()
            if number is not None and number not in range(1,limit+1):raise ValueError(f'当前引擎参考图编号须为1–{limit}。')
            slots = [number] if number else [i for i in range(1,limit+1) if i not in refs]
            if not paths or len(paths) > len(slots):raise ValueError(f'当前引擎最多添加{limit}张参考图；可拖到已有图片上替换。')
            for path in paths:self.validate(path)
            for slot, source in zip(slots, paths):
                if slot == 1:w.set_reference(str(source))
                else:
                    target = self.data/'references'/(uuid4().hex+Path(source).suffix.lower())
                    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
                    self.extra[slot] = target
            w.intent_controller.source_changed()
            w.generation_type_changed(); w.workbench.refresh_reference()
        except (OSError, ValueError) as exc:
            self.append('软件', str(exc)); w.intent_controller.notify(str(exc)); w.status.setText(str(exc))

    def limit(self):
        from .h3_image import settings
        w=self.window
        return 16 if (w.model_family.currentData()=='h3_image' or w.model_family.currentData()=='auto' and settings(self.data)) and w.generation_type.currentData()!='walk' and not w.api_controller.cloud else 4

    def remove(self, number):
        if self.window.preparing:return
        if number == 1:self.window.clear_reference()
        else:self.extra.pop(number, None)
        self.window.intent_controller.source_changed()
        self.window.generation_type_changed(); self.window.workbench.refresh_reference()

    def snapshot(self, uploads=None):
        w = self.window; refs = self.references()
        if w.generation_type.currentData() == 'walk':raise ValueError('多图组合当前用于单张图片；动画仍使用一张角色图和动作素材。')
        if w.api_controller.cloud:raise ValueError('多图参考当前使用本地图片生成，请先切回本地模式。')
        if w.model_family.currentData() not in ('auto', 'flux_klein'):
            raise ValueError('多图参考请选择“自动”或“FLUX”。')
        if w.custom_graph is not None:raise ValueError('多图参考请把后台预设恢复为自动选择。')
        if not flux_klein.enabled(w.info['object_info'], self.data):raise ValueError('请连接已配置的图片引擎。')
        visible, visible_negative = w.positive.toPlainText(), w.negative.toPlainText()
        from .prompt_language import texts
        positive, negative = texts(w)
        if not positive.strip():raise ValueError('请先描述各张图的用途并生成提示词，或直接填写提示词。')
        c=w.intent_controller
        if c.current_record and c.applied_context==c.fingerprint(prompts=False) and visible.strip()==c.generated_positive:
            plan_file=c.current_record/'result.json'
            if plan_file.is_file():
                order=json.loads(plan_file.read_text('utf-8')).get('plan',{}).get('render_order',list(refs))
                if len(order)==len(refs) and set(order)==set(refs):refs={n:refs[n] for n in order}
        seed = int(w.seed.text())
        if seed == -1:seed = secrets.randbelow(2**53)
        req = ImageRequest(flux_klein.UNET, positive, negative, w.width.value(), w.height.value(), 4, 1., seed, 'euler', 'flux2')
        binding=self.structural_binding(strict=True);structure_config=None
        names=uploads or {n:f'__image_{n}__' for n in refs}
        if binding:
            from .structure_control import settings,build
            structure_config=settings(self.data);graph,mapping=build(req,w.info['object_info'],names,binding,structure_config)
        else:graph,mapping=multi_reference.build(req,w.info['object_info'],names)
        params = dict(asdict(req), mode='chat', model_family='flux_klein', user_prompt=visible,
            user_negative=visible_negative, prompt_language='chinese_display_english_request',
            template='多图参考', image_route=w.model_family.currentData(), bindings=mapping,
            denoise=1., reference_policy='numbered_references_v1', reference_strength=None,
            output_background=w.output_background.currentData(), intent={'unmatched':''}, negative_unmatched='',
            lora_style=None, quality_mode='off', edge_smoothing=False,
            negative_policy='positive_text_constraints_cfg1',
            references=[dict(number=n, source=str(p), sha256=digest(p), model_input=i+1) for i,(n,p) in enumerate(refs.items())])
        if binding:
            params.update(structure_binding=binding,structure_settings=structure_config,reference_policy='trained_depth_structure_v1')
            params['subject_only']=bool(binding['structure']!=binding['identity'] and w.workbench.subject_only.isChecked())
            for row in params['references']:
                row.pop('model_input',None);row['model_inputs']=([1] if row['number']==binding['structure'] else [])+([2] if row['number']==binding['identity'] else [])
        return graph, params

    def intercept(self):
        if not self.active():return False
        w = self.window
        if w.preparing:return True
        if not w.connected:raise ValueError('请先连接本地图片引擎。')
        graph, params = self.snapshot()
        from .prompt_binding import check_models
        check_models(graph, w.info['object_info'])
        if params['output_background'] == 'transparent':
            from .background import model_file
            if not model_file().is_file():raise ValueError('透明输出需要本地去背景模型。')
        refs = [(r['number'], Path(r['source']), r['sha256']) for r in params['references']]
        client = w.client; staging = self.data/'references'/uuid4().hex
        signature=w.generation_intent.signature() if hasattr(w,'generation_intent') else None
        prompt_contract=w.generation_intent.current() if hasattr(w,'generation_intent') else None
        prompt_contract=json.loads(json.dumps(prompt_contract))
        w.preparing = True; w.prepare_cancel.clear(); w.generate_button.setEnabled(False)
        show_task = w.current is None
        if show_task:w.task_display.start(); w.progress.setRange(0, 0)
        w.status.setText('正在准备多张参考图…')
        def run(emit):
            staging.mkdir(parents=True, exist_ok=False)
            binding=params.get('structure_binding')
            subject=None
            if params.get('subject_only'):
                from .reference_subject import prepare,settings
                identity=next(p for n,p,sha in refs if n==binding['identity'])
                subject=prepare(identity,self.data,settings(self.data),w.prepare_cancel,emit)
                params['subject_preparation']=subject
            if binding:
                from .structure_control import extract
                source=next(p for n,p,sha in refs if n==binding['structure'])
                geometry=extract(params['structure_settings'],source,staging/'geometry',params['width'],params['height'],w.prepare_cancel,emit)
                if w.prepare_cancel.is_set():raise Cancelled('结构准备已取消。')
                graph['image_1']['inputs']['image']=client.upload_image(Path(geometry['depth']))
                params['structure_evidence']=geometry
            for number, source, sha in refs:
                if w.prepare_cancel.is_set():raise Cancelled('参考图上传已取消。')
                if digest(source) != sha:raise ValueError('参考图发生变化，未提交生成。')
                if binding and number!=binding['identity']:continue
                with Image.open(subject['prepared'] if subject else source) as im:rgb = opaque_reference(ImageOps.exif_transpose(im).convert('RGBA'))
                path = staging/f'image_{number}.png'; rgb.save(path)
                name = client.upload_image(path)
                graph['image_2' if binding else f'image_{number}']['inputs']['image'] = name
            return graph
        def finish(kind, data):
            if kind=='intent_stage':w.status.setText(data['message']);return
            if kind not in ('result','error','cancelled'):return
            unchanged=(signature is None or signature==w.generation_intent.signature() and prompt_contract==w.generation_intent.current())
            if kind=='result' and not unchanged:kind='error';data='需求、提示词或结构来源已修改，请确认后重新生成。'
            w.preparing = False
            if show_task:w.task_display.finish('completed' if kind=='result' else 'failed' if kind=='error' else 'cancelled')
            w.generation_type_changed()
            if kind != 'result' or w.prepare_cancel.is_set():
                message='参考图上传已取消。' if w.prepare_cancel.is_set() else '未提交生成：'+str(data)
                self.append('软件',message);w.intent_controller.notify(message); w.status.setText('多图准备未完成')
            else:
                folder = w.queue_graph(graph, params)
                from .storage import write_json
                write_json(folder/'reference-inputs.json', dict(references=params['references'], policy=params['reference_policy']))
                if params.get('structure_binding'):
                    write_json(folder/'structure-control.json',dict(binding=params['structure_binding'],evidence=params['structure_evidence'],subject_preparation=params.get('subject_preparation'),model_inputs=params['bindings']['model_inputs']))
                w.last_chat_graph = json.loads(json.dumps(graph)); w.editor_needs_sync = True
            w.start_next()
        w.launch(run, finish)
        return True
