"""User-owned API endpoints and keys, kept separate from local model settings."""
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .api_config import AuthEndpoint, Endpoint
from .api_transport import list_models, redact


class ApiDialog(QDialog):
    def __init__(self, controller):
        super().__init__(controller.window)
        self.controller = controller
        self.setWindowTitle('API 与智能生图')
        self.resize(610, 740)
        self.fields = {}
        self.check_cancel = None
        layout = QVBoxLayout(self)
        heading = QLabel('选择云端图片模型，或让大模型辅助本地生成')
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.backend = QComboBox()
        self.backend.addItem('本地 ComfyUI 生图', 'local')
        self.backend.addItem('云端图片 API 生图（不需要本地大模型）', 'api')
        layout.addWidget(self.backend)
        self.smart = QCheckBox('先用理解模型整理提示词（可选，增加一次 API 调用）')
        layout.addWidget(self.smart)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        for role, title in (('image','云端生图'),('planner','智能理解 · 可选')):
            page = QWidget()
            form = QFormLayout(page)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            presets = QComboBox()
            for label, data in ([('自定义兼容图片服务',None),('OpenAI 官方图片接口','openai'),('Google Gemini 原生图片接口','gemini')]
                                if role=='image' else [('自定义兼容聊天服务',None),('DeepSeek','deepseek'),('OpenAI','openai')]):
                presets.addItem(label, data)
            form.addRow('地址预设', presets)
            protocol = QComboBox()
            protocol.addItem('OpenAI Images 兼容协议' if role=='image' else 'OpenAI Chat Completions 兼容协议','openai')
            if role=='image':
                protocol.addItem('Gemini 原生图片协议','gemini')
            form.addRow('接口协议', protocol)
            url = QLineEdit()
            url.setPlaceholderText('https://你的服务地址/v1')
            form.addRow('API 基础地址', url)
            key = QLineEdit()
            key.setEchoMode(QLineEdit.EchoMode.Password)
            key.setPlaceholderText('在本机输入购买的 API Key，不要发到聊天中')
            form.addRow('API Key', key)
            remember = QCheckBox('在本机加密记住（取消勾选则仅本次会话使用）')
            form.addRow(remember)
            model = QComboBox()
            model.setEditable(True)
            model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            model.setMinimumContentsLength(14)
            model.lineEdit().setPlaceholderText('手动填写模型 ID，或读取列表后主动选择')
            form.addRow('模型名称', model)
            fetch = QPushButton('读取模型列表 / 检查连接（不生图）')
            form.addRow(fetch)
            timeout = QSpinBox()
            timeout.setRange(15, 1800)
            timeout.setSuffix(' 秒')
            form.addRow('最长网络等待', timeout)
            controls = dict(url=url,key=key,remember=remember,model=model,timeout=timeout,protocol=protocol)
            if role=='planner':
                json_mode = QCheckBox('使用 JSON 响应模式（服务商须支持）')
                vision = QCheckBox('向理解模型发送参考图（仅支持视觉的模型）')
                form.addRow(json_mode)
                form.addRow(vision)
                controls.update(json_mode=json_mode,vision=vision)
            else:
                edits = QCheckBox('平台支持参考图编辑接口（Images Edits）')
                form.addRow(edits)
                size = QComboBox()
                size.addItems(['1024x1024','1536x1024','1024x1536','auto'])
                form.addRow('兼容接口尺寸', size)
                quality = QComboBox()
                for label, value in [('平台默认',''),('自动','auto'),('低','low'),('中','medium'),('高','high')]:
                    quality.addItem(label,value)
                form.addRow('兼容接口画质', quality)
                aspect = QComboBox()
                aspect.addItems(['1:1','2:3','3:2','3:4','4:3','9:16','16:9'])
                form.addRow('Gemini 比例', aspect)
                resolution = QComboBox()
                resolution.addItems(['1K','2K','4K'])
                form.addRow('Gemini 分辨率', resolution)
                controls.update(edits=edits,image_size=size,quality=quality,aspect_ratio=aspect,resolution=resolution)
            self.fields[role] = controls
            presets.activated.connect(lambda _index, r=role, p=presets:self.preset(r,p.currentData()))
            url.textEdited.connect(lambda _text,r=role:self.address_changed(r))
            fetch.clicked.connect(lambda _checked=False,r=role,b=fetch:self.fetch_models(r,b))
            protocol.currentIndexChanged.connect(lambda _index,r=role:self.protocol_changed(r))
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            tabs.addTab(scroll,title)
        note = QLabel('云端生图使用支持图片输出的模型；DeepSeek 等聊天 Key 可用于理解需求。'
            '当前 API 版本支持单张图，动画仍使用本地完整骨骼。\n'
            '文字和所选参考图会发往这里填写的服务，按平台计费。普通图片 API 不接入本地 LoRA、CFG 或采样器；'
            '不支持独立反向词时，会将反向内容作为文字约束。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        save = QPushButton('保存并使用')
        save.clicked.connect(self.save)
        close = QPushButton('关闭')
        close.clicked.connect(self.close)
        buttons.addWidget(save)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.reload()

    def reload(self):
        settings = self.controller.settings
        self.backend.setCurrentIndex(self.backend.findData(settings.backend))
        self.smart.setChecked(settings.smart)
        for role, values in self.fields.items():
            endpoint = settings.endpoints[role]
            values['url'].setText(endpoint.base_url)
            values['model'].setEditText(endpoint.model)
            values['timeout'].setValue(endpoint.timeout)
            values['protocol'].setCurrentIndex(values['protocol'].findData(endpoint.protocol))
            values['remember'].setChecked(settings.remember[role])
            try:
                values['key'].setText(settings.key(role))
            except (ValueError,OSError) as exc:
                self.status.setText(str(exc))
                values['key'].clear()
            for name in ('vision','json_mode','edits'):
                if name in values:
                    values[name].setChecked(getattr(endpoint,name))
            for name in ('image_size','aspect_ratio','resolution'):
                if name in values:
                    values[name].setCurrentText(getattr(endpoint,name))
            if 'quality' in values:
                values['quality'].setCurrentIndex(values['quality'].findData(endpoint.quality))
            self.protocol_changed(role)

    def protocol_changed(self, role):
        if role != 'image':
            return
        values = self.fields[role]
        native = values['protocol'].currentData() == 'gemini'
        for name in ('image_size','quality','edits'):
            values[name].setEnabled(not native)
        for name in ('aspect_ratio','resolution'):
            values[name].setEnabled(native)

    def address_changed(self, role):
        self.fields[role]['key'].clear()
        self.fields[role]['remember'].setChecked(False)
        self.status.setText('地址已改变，请重新填写该服务的 Key，避免向其他地址发送旧密钥。')

    def preset(self, role, name):
        if name is None:
            return
        values = self.fields[role]
        values['url'].setText({'deepseek':'https://api.deepseek.com','openai':'https://api.openai.com/v1',
            'gemini':'https://generativelanguage.googleapis.com/v1beta'}[name])
        values['model'].clear()
        values['protocol'].setCurrentIndex(values['protocol'].findData('gemini' if name=='gemini' else 'openai'))
        if role=='image':
            values['edits'].setChecked(name=='openai')
        self.address_changed(role)

    def endpoint(self, role) -> Endpoint:
        values = self.fields[role]
        data = dict(base_url=values['url'].text().strip(),model=values['model'].currentText().strip(),
                    timeout=values['timeout'].value(),protocol=values['protocol'].currentData())
        for name in ('json_mode','vision','edits'):
            if name in values:
                data[name] = values[name].isChecked()
        for name in ('image_size','aspect_ratio','resolution'):
            if name in values:
                data[name] = values[name].currentText()
        if 'quality' in values:
            data['quality'] = values['quality'].currentData()
        return Endpoint(**data).validated(False)

    def fetch_models(self, role, button):
        if self.check_cancel is not None:
            self.status.setText('请等待上一次连接检查结束。')
            return
        try:
            auth = AuthEndpoint(self.endpoint(role),self.fields[role]['key'].text().strip()).validate(False)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        button.setEnabled(False)
        self.check_cancel = threading.Event()
        cancel = self.check_cancel
        self.status.setText('正在读取此服务的模型列表…')
        def done(kind, data):
            if kind not in ('result','error','cancelled'):
                return
            button.setEnabled(True)
            self.check_cancel = None
            if kind=='result':
                combo = self.fields[role]['model']
                previous = combo.currentText()
                combo.clear()
                combo.addItems(data)
                combo.setEditText(previous)
                self.status.setText(f'已读取 {len(data)} 个模型，请主动选择。连接成功不代表具有生图权限；本次未生图。')
            else:
                self.status.setText(redact(str(data),auth.key))
        self.controller.window.launch(lambda _emit:list_models(auth,cancel),done)

    def save(self):
        try:
            endpoints = {role:self.endpoint(role) for role in self.fields}
            keys = {role:values['key'].text().strip() for role,values in self.fields.items()}
            remember = {role:values['remember'].isChecked() for role,values in self.fields.items()}
            active = (['planner'] if self.smart.isChecked() else []) + (['image'] if self.backend.currentData()=='api' else [])
            for role in active:
                AuthEndpoint(endpoints[role],keys[role]).validate()
            self.controller.settings.save(self.backend.currentData(),self.smart.isChecked(),endpoints,keys,remember)
            self.controller.load_error = ''
            self.controller.apply_mode()
            self.status.setText('已保存。仅在点击生成时调用所选服务；本次没有付费生成。')
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))

    def closeEvent(self, event):
        if self.check_cancel:
            self.check_cancel.set()
        super().closeEvent(event)
