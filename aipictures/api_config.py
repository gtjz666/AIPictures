"""Public API settings and user-scoped Windows DPAPI secrets; no Qt dependency."""
import base64
import ctypes
import hashlib
import ipaddress
import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .storage import write_json


def loopback(host: str) -> bool:
    if host.lower() == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def api_base(value: str) -> str:
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.scheme not in ('https', 'http'):
        raise ValueError('API 地址应为完整的 https:// 地址。')
    if parsed.scheme == 'http' and not loopback(parsed.hostname):
        raise ValueError('远程 API 必须使用 HTTPS；HTTP 仅供本机接口使用。')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('API 地址不能包含账号、Key、查询参数或片段；Key 请填入专用输入框。')
    if any(ord(c) < 33 for c in value):
        raise ValueError('API 地址不能包含空格或控制字符。')
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError('API 地址端口无效。') from exc
    if parsed.path.endswith(('/chat/completions', '/images/generations', '/images/edits', '/models')):
        raise ValueError('请填写 API 基础地址，例如 https://平台地址/v1，不要包含具体接口路径。')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', ''))


@dataclass(frozen=True)
class Endpoint:
    base_url: str = ''
    model: str = ''
    json_mode: bool = False
    vision: bool = False
    edits: bool = False
    timeout: int = 300
    protocol: str = 'openai'
    image_size: str = '1024x1024'
    aspect_ratio: str = '1:1'
    resolution: str = '1K'
    quality: str = ''

    def validated(self, require_model: bool = True) -> 'Endpoint':
        normalized = api_base(self.base_url)
        if require_model and not self.model.strip():
            raise ValueError('请填写模型名称，或读取模型列表后主动选择。')
        if len(self.model) > 200 or any(ord(c) < 33 for c in self.model):
            raise ValueError('模型名称包含无效字符。')
        if not 15 <= self.timeout <= 1800:
            raise ValueError('API 等待时限应为 15–1800 秒。')
        if self.protocol not in ('openai', 'gemini'):
            raise ValueError('不支持此 API 协议。')
        if self.image_size not in ('auto', '1024x1024', '1536x1024', '1024x1536'):
            raise ValueError('请选择支持的 API 图片尺寸。')
        if self.aspect_ratio not in ('1:1','2:3','3:2','3:4','4:3','9:16','16:9') or self.resolution not in ('1K','2K','4K'):
            raise ValueError('Gemini 比例或分辨率无效。')
        if self.quality not in ('','auto','low','medium','high'):
            raise ValueError('API 画质设置无效。')
        from dataclasses import replace
        return replace(self, base_url=normalized, model=self.model.strip())


@dataclass(frozen=True)
class AuthEndpoint:
    endpoint: Endpoint
    key: str = field(repr=False)

    def validate(self, require_model: bool = True) -> 'AuthEndpoint':
        endpoint = self.endpoint.validated(require_model)
        if not self.key or len(self.key) > 4096 or any(not 33 <= ord(c) <= 126 for c in self.key):
            raise ValueError('请在 API 设置中填写有效的 Key（不要带空格或换行）。')
        if self.key in endpoint.base_url or self.key == endpoint.model:
            raise ValueError('Key 只能放在密钥输入框，不能放入地址或模型名称。')
        return AuthEndpoint(endpoint, self.key)


class _Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, entropy: bytes, decrypt: bool = False) -> bytes:
    if os.name != 'nt':
        raise ValueError('此系统不支持 Windows 加密存储，请使用“仅本次会话”。')
    buffers = [ctypes.create_string_buffer(item) for item in (data, entropy)]
    source, extra = [_Blob(len(item), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
                     for item, buf in zip((data, entropy), buffers)]
    output = _Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_Blob)]
    function.restype = ctypes.c_int
    if not function(ctypes.byref(source), None, ctypes.byref(extra), None, None, 1, ctypes.byref(output)):
        raise ValueError('无法读取或保护本机密钥，请重新填写；不回退为明文存储。')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class ApiSettings:
    def __init__(self, data: Path, load: bool = True):
        self.data = Path(data)
        self.path = self.data / 'api-settings.json'
        self.vault = self.data / 'api-secrets.local.json'
        self.session: dict[str, str] = {}
        self.backend = 'local'
        self.smart = False
        self.endpoints = {'planner': Endpoint('https://api.deepseek.com'),
                          'image': Endpoint('https://api.openai.com/v1')}
        self.remember = {'planner': False, 'image': False}
        if load and self.path.is_file():
            saved = json.loads(self.path.read_text('utf-8'))
            self.backend = saved.get('backend', 'local')
            if self.backend not in ('local', 'api'):
                raise ValueError('API 生图后端设置无效。')
            self.smart = bool(saved.get('smart', False))
            for role in self.endpoints:
                values = saved.get(role, {})
                self.endpoints[role] = Endpoint(**{f.name: values[f.name] for f in fields(Endpoint) if f.name in values}).validated(False)
                self.remember[role] = bool(saved.get('remember', {}).get(role, False))

    @staticmethod
    def scope(role: str, url: str) -> str:
        if role not in ('planner', 'image'):
            raise ValueError('无效的 API 用途。')
        return hashlib.sha256((role + '|' + api_base(url)).encode()).hexdigest()

    def key(self, role: str, endpoint: Endpoint | None = None) -> str:
        endpoint = endpoint or self.endpoints[role]
        scope = self.scope(role, endpoint.base_url)
        if scope in self.session:
            return self.session[scope]
        encrypted = json.loads(self.vault.read_text('utf-8')) if self.vault.exists() else {}
        if scope not in encrypted:
            return ''
        return _crypt(base64.b64decode(encrypted[scope], validate=True), scope.encode(), True).decode()

    def auth(self, role: str, require_model: bool = True) -> AuthEndpoint:
        return AuthEndpoint(self.endpoints[role], self.key(role)).validate(require_model)

    def save(self, backend: str, smart: bool, endpoints: dict[str, Endpoint],
             keys: dict[str, str], remember: dict[str, bool]) -> None:
        if backend not in ('local', 'api'):
            raise ValueError('无效的生图后端。')
        public = json.dumps({role:asdict(value) for role,value in endpoints.items()})
        if any(key.strip() and key.strip() in public for key in keys.values()):
            raise ValueError('地址和模型设置中包含 Key，请只在密钥框填写。')
        encrypted = json.loads(self.vault.read_text('utf-8')) if self.vault.exists() else {}
        sessions = self.session.copy()
        for role, endpoint in endpoints.items():
            endpoint.validated(False)
            scope = self.scope(role, endpoint.base_url)
            old = self.scope(role, self.endpoints[role].base_url)
            if old != scope:
                encrypted.pop(old, None)
                sessions.pop(old, None)
            key = keys[role].strip()
            if key:
                AuthEndpoint(endpoint, key).validate(False)
                sessions[scope] = key
            else:
                sessions.pop(scope, None)
            if key and remember.get(role):
                encrypted[scope] = base64.b64encode(_crypt(key.encode(), scope.encode())).decode()
            else:
                encrypted.pop(scope, None)
        write_json(self.vault, encrypted)
        write_json(self.path, {'schema_version': 1, 'backend': backend, 'smart': smart,
            **{role: asdict(value) for role, value in endpoints.items()}, 'remember': remember})
        self.backend, self.smart, self.endpoints, self.remember, self.session = backend, smart, endpoints, remember, sessions
