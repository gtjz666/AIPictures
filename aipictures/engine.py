import json
import time
import uuid
from urllib.request import Request, urlopen, ProxyHandler, build_opener
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError
import websocket


class Cancelled(Exception):
    pass


class ComfyClient:
    def __init__(self, url='http://127.0.0.1:8188'):
        self.url = url.rstrip('/')
        parsed = urlparse(self.url)
        if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('本地模式只允许 localhost / 127.0.0.1 / ::1 的 HTTP 地址')
        self.http = build_opener(ProxyHandler({}))

    def request(self, path, body=None, raw=False):
        req = Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
        try:
            with self.http.open(req, timeout=20) as response:
                result = response.read()
        except HTTPError as error:
            raise RuntimeError(error.read().decode('utf-8', 'replace')) from error
        return result if raw else (json.loads(result) if result.strip() else {})

    def discover(self):
        info = self.request('/object_info')
        def choices(node, field):
            return info.get(node, {}).get('input', {}).get('required', {}).get(field, [[]])[0]
        return {'checkpoints': choices('CheckpointLoaderSimple', 'ckpt_name'),
                'loras': choices('LoraLoader', 'lora_name'),
                'samplers': choices('KSampler', 'sampler_name'),
                'schedulers': choices('KSampler', 'scheduler'), 'nodes': list(info)}

    def cancel(self, prompt_id):
        # Never interrupt another client's running task.
        self.request('/queue', {'delete': [prompt_id]})
        queue = self.request('/queue')
        if any(row[1] == prompt_id for row in queue.get('queue_running', [])):
            self.request('/interrupt', {'prompt_id': prompt_id})

    def generate(self, graph, folder, emit, cancel, submitted=lambda _: None, timeout=1800):
        client_id = uuid.uuid4().hex
        ws = websocket.create_connection(self.url.replace('http:', 'ws:', 1) + '/ws?clientId=' + client_id,
                                         timeout=1, http_proxy_host=None)
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
                    message = ws.recv()
                    if isinstance(message, str):
                        event = json.loads(message)
                        data = event.get('data', {})
                        if data.get('prompt_id') == prompt_id:
                            emit(event['type'], data)
                            if event['type'] in ('execution_error', 'execution_interrupted'):
                                raise RuntimeError(data.get('exception_message', '执行中断'))
                except websocket.WebSocketTimeoutException:
                    pass
                if time.monotonic() - checked >= 1:
                    checked = time.monotonic()
                    history = self.request('/history/' + prompt_id).get(prompt_id)
                    if history:
                        if history.get('status', {}).get('status_str') == 'error':
                            raise RuntimeError(json.dumps(history['status'], ensure_ascii=False))
                        images = []
                        for output in history.get('outputs', {}).values():
                            for item in output.get('images', []):
                                if item.get('type', 'output') != 'output':
                                    continue
                                content = self.request('/view?' + urlencode(item), raw=True)
                                path = folder / f'image_{len(images):03d}.png'
                                path.write_bytes(content)
                                images.append(str(path))
                        if not images:
                            raise RuntimeError('工作流执行结束但没有保存图片，请使用 SaveImage 输出节点')
                        return {'prompt_id': prompt_id, 'images': images, 'history': history}
            raise TimeoutError(f'等待超过 {timeout} 秒；ComfyUI 任务可能仍在执行，任务 ID：{prompt_id}')
        finally:
            ws.close()
