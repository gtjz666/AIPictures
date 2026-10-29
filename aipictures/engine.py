import json
import time
import uuid
import mimetypes
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen, ProxyHandler, build_opener
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError, URLError
import websocket


class Cancelled(Exception):
    pass


class EngineUnavailable(ConnectionError):
    """The local server is absent; resubmitting an existing job is never safe."""
    def __init__(self, url):
        super().__init__(f'本地生成引擎已断开（{url}）。请点击“启动本地引擎”，或启动 ComfyUI 后重新连接。当前任务不会自动重跑。')


def is_engine_unavailable(error):
    return isinstance(error, EngineUnavailable) or '本地生成引擎已断开' in str(error)


class ComfyClient:
    def __init__(self, url='http://127.0.0.1:8188'):
        self.url = url.rstrip('/')
        parsed = urlparse(self.url)
        if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('本地模式只允许 localhost / 127.0.0.1 / ::1 的 HTTP 地址')
        self.http = build_opener(ProxyHandler({}))

    def request(self, path, body=None, raw=False, timeout=20):
        req = Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
        try:
            with self.http.open(req, timeout=timeout) as response:
                result = response.read()
        except HTTPError as error:
            raise RuntimeError(error.read().decode('utf-8', 'replace')) from error
        except (URLError, ConnectionError, OSError) as error:
            reason = getattr(error, 'reason', error)
            if isinstance(reason, TimeoutError): raise
            raise EngineUnavailable(self.url) from error
        return result if raw else (json.loads(result) if result.strip() else {})

    def discover(self):
        info = self.request('/object_info')
        def choices(node, field):
            return info.get(node, {}).get('input', {}).get('required', {}).get(field, [[]])[0]
        return {'checkpoints': choices('CheckpointLoaderSimple', 'ckpt_name'),
                'loras': choices('LoraLoader', 'lora_name'),
                'samplers': choices('KSampler', 'sampler_name'),
                'schedulers': choices('KSampler', 'scheduler'), 'nodes': list(info), 'object_info': info}

    def upload_image(self, path, subfolder='AIPictures/references'):
        path = Path(path)
        boundary = 'AIPictures' + uuid.uuid4().hex
        filename = uuid.uuid4().hex + path.suffix.lower()
        parts = []
        for field, value in [('type', 'input'), ('subfolder', subfolder), ('overwrite', 'false')]:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"\r\n\r\n{value}\r\n'.encode())
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
        parts.extend([path.read_bytes(), f'\r\n--{boundary}--\r\n'.encode()])
        req = Request(self.url + '/upload/image', data=b''.join(parts),
                      headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        try:
            with self.http.open(req, timeout=30) as response:
                result = json.loads(response.read())
        except HTTPError as error:
            raise RuntimeError(error.read().decode('utf-8', 'replace')) from error
        except (URLError, ConnectionError, OSError) as error:
            if isinstance(getattr(error,'reason',error),TimeoutError): raise
            raise EngineUnavailable(self.url) from error
        return str(PurePosixPath(result.get('subfolder', '')) / result['name'])

    def cancel(self, prompt_id):
        # Never interrupt another client's running task.
        self.request('/queue', {'delete': [prompt_id]})
        queue = self.request('/queue')
        if any(row[1] == prompt_id for row in queue.get('queue_running', [])):
            self.request('/interrupt', {'prompt_id': prompt_id})

    def generate(self, graph, folder, emit, cancel, submitted=lambda _: None, timeout=1800):
        client_id = uuid.uuid4().hex
        try:
            ws = websocket.create_connection(self.url.replace('http:', 'ws:', 1) + '/ws?clientId=' + client_id,
                                             timeout=3, http_proxy_host=None)
        except (ConnectionError, OSError) as error:
            raise EngineUnavailable(self.url) from error
        prompt_id = None
        try:
            if cancel.is_set():
                raise Cancelled('任务已取消')
            response = self.request('/prompt', {'prompt': graph, 'client_id': client_id})
            prompt_id = response['prompt_id']
            submitted(prompt_id)
            emit('queued', {'prompt_id': prompt_id})
            start, checked = time.monotonic(), 0
            while time.monotonic() - start < timeout:
                if cancel.is_set():
                    self.cancel(prompt_id)
                    raise Cancelled('任务已取消')
                try:
                    message = ws.recv() if ws is not None else None
                    if isinstance(message, str):
                        event = json.loads(message)
                        data = event.get('data', {})
                        if data.get('prompt_id') == prompt_id:
                            emit(event['type'], data)
                            if event['type']=='execution_interrupted':
                                raise Cancelled('本任务已中断，已收到的结果保留。')
                            if event['type']=='execution_error':
                                raise RuntimeError(data.get('exception_message', '执行中断'))
                except websocket.WebSocketTimeoutException:
                    pass
                except (websocket.WebSocketConnectionClosedException, ConnectionError, OSError):
                    ws.close(); ws = None
                    emit('monitor_waiting', {'prompt_id':prompt_id,'message':'进度连接中断，正在通过任务记录继续检查。'})
                if ws is None and cancel.wait(1): continue
                if time.monotonic() - checked >= 1:
                    checked = time.monotonic()
                    try:
                        history = self.request('/history/' + prompt_id).get(prompt_id)
                    except EngineUnavailable:
                        raise
                    except (TimeoutError, URLError) as error:
                        emit('monitor_waiting', {'prompt_id': prompt_id, 'message': str(error)})
                        continue
                    if history:
                        if history.get('status', {}).get('status_str') == 'error':
                            raise RuntimeError(json.dumps(history['status'], ensure_ascii=False))
                        images = []; latents = []
                        for output in history.get('outputs', {}).values():
                            for item in output.get('images', []):
                                if item.get('type', 'output') != 'output':
                                    continue
                                content = self.request('/view?' + urlencode(item), raw=True)
                                path = folder / f'image_{len(images):03d}.png'
                                path.write_bytes(content)
                                images.append(str(path))
                            for item in output.get('latents', []):
                                if item.get('type', 'output') != 'output': continue
                                content = self.request('/view?' + urlencode(item), raw=True)
                                path = folder / f'samples_{len(latents):03d}.latent'
                                path.write_bytes(content); latents.append(str(path))
                        if not images:
                            raise RuntimeError('工作流执行结束但没有保存图片，请使用 SaveImage 输出节点')
                        return {'prompt_id': prompt_id, 'images': images, 'latents':latents, 'history': history}
            raise TimeoutError(f'等待超过 {timeout} 秒；ComfyUI 任务可能仍在执行，任务 ID：{prompt_id}')
        finally:
            if ws is not None: ws.close()
