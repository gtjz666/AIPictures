import json
import time
import uuid
import mimetypes
import threading
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen, ProxyHandler, build_opener
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError, URLError
import websocket
from .storage import write_json


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
        self._active = set()
        self._active_lock = threading.Lock()

    def active_prompts(self):
        with self._active_lock: return sorted(self._active)

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
        self.request('/queue', {'delete': [prompt_id]},timeout=2)
        queue = self.request('/queue',timeout=2)
        if any(row[1] == prompt_id for row in queue.get('queue_running', [])):
            self.request('/interrupt', {'prompt_id': prompt_id},timeout=2)

    def generate(self, graph, folder, emit, cancel, submitted=lambda _: None, timeout=None, allow_latent_only=False):
        """Submit exactly once, then monitor the same task, even after a read timeout.

        Model loading and queueing have no default wall-clock deadline. A finite
        timeout is an explicit diagnostic option, not a generation quality limit.
        """
        client_id = uuid.uuid4().hex
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        ws = None
        try:
            ws = websocket.create_connection(self.url.replace('http:', 'ws:', 1) + '/ws?clientId=' + client_id,
                                             timeout=3, http_proxy_host=None)
        except (websocket.WebSocketTimeoutException, TimeoutError):
            emit('monitor_waiting', {'message':'进度连接暂时超时，将通过任务记录检查生成。'})
        except (ConnectionError, OSError) as error:
            raise EngineUnavailable(self.url) from error
        try:
            if cancel.is_set():
                raise Cancelled('任务已取消')
            write_json(folder/'submission.json',{'url':self.url,'client_id':client_id,'state':'submitting'})
            response = self.request('/prompt', {'prompt': graph, 'client_id': client_id})
            prompt_id = response['prompt_id']
            with self._active_lock:self._active.add(prompt_id)
            write_json(folder/'submission.json',{'url':self.url,'client_id':client_id,'prompt_id':prompt_id,'state':'submitted'})
            submitted(prompt_id)
            emit('queued', {'prompt_id': prompt_id})
            return self._wait_for_task(prompt_id, graph, Path(folder), emit, cancel, ws, timeout, allow_latent_only)
        finally:
            if 'prompt_id' in locals():
                with self._active_lock:self._active.discard(prompt_id)
            if ws is not None: ws.close()

    def resume(self, prompt_id, graph, folder, emit, cancel, allow_latent_only=False):
        """Recover results/progress by ID; never submit or regenerate a prompt."""
        return self._wait_for_task(prompt_id, graph, Path(folder), emit, cancel, None, None, allow_latent_only)

    def _wait_for_task(self, prompt_id, graph, folder, emit, cancel, ws, timeout, allow_latent_only):
        folder.mkdir(parents=True, exist_ok=True)
        start, checked, heartbeat = time.monotonic(), -float('inf'), -float('inf')
        state = {'prompt_id':prompt_id,'url':self.url,'state':'queued','node':None,
                 'node_type':None,'elapsed_seconds':0.,'last_progress':None}
        cancellation_sent = False
        missing_checks = 0

        def record(**changes):
            state.update(changes,elapsed_seconds=round(time.monotonic()-start,2))
            write_json(folder/'monitor.json',state)

        def notify_wait(message):
            record(connection_message=message)
            emit('monitor_waiting',dict(state,message=message))

        try:
            while timeout is None or time.monotonic()-start < timeout:
                if cancel.is_set() and not cancellation_sent:
                    try:
                        self.cancel(prompt_id)
                        cancellation_sent = True
                        record(state='cancelling')
                        emit('cancel_pending',dict(state,message='正在等待后端确认取消；当前节点结束前不会开始下一任务。'))
                    except EngineUnavailable:
                        raise Cancelled('后端已断开，取消状态无法确认；任务标识已保留，请重新连接后检查。')
                    except (TimeoutError, URLError):
                        notify_wait('取消请求暂时超时，继续确认同一任务；不会提交新任务。')
                try:
                    message = ws.recv() if ws is not None else None
                    if isinstance(message, str):
                        event = json.loads(message)
                        data = event.get('data', {})
                        if data.get('prompt_id') == prompt_id:
                            if event['type']=='executing' and data.get('node') is not None:
                                node=str(data['node'])
                                record(state='cancelling' if cancellation_sent else 'running',node=node,
                                       node_type=graph.get(node,{}).get('class_type'),node_started_seconds=round(time.monotonic()-start,2))
                            elif event['type']=='progress':
                                record(state='cancelling' if cancellation_sent else 'running',last_progress=data)
                            emit(event['type'], data)
                            if event['type']=='execution_interrupted':
                                # The interruption event can precede task_done().
                                # Keep the foreground job occupied until its queue
                                # entry disappears; do not overlap the next task.
                                cancellation_sent = True
                                record(state='cancelling')
                                emit('cancel_pending',dict(state,message='已收到中断通知，等待后端结束当前任务…'))
                            if event['type']=='execution_error':
                                raise RuntimeError(data.get('exception_message', '执行中断'))
                except websocket.WebSocketTimeoutException:
                    pass
                except (websocket.WebSocketConnectionClosedException, ConnectionError, OSError):
                    ws = None
                    notify_wait('进度连接中断，正在通过任务记录继续检查。')
                if time.monotonic() - checked >= 1:
                    checked = time.monotonic()
                    try:
                        if cancellation_sent:
                            queue=self.request('/queue')
                            if not any(row[1]==prompt_id for key in ('queue_running','queue_pending') for row in queue.get(key,[])):
                                record(state='cancelled')
                                raise Cancelled('任务已取消，后端已确认停止；已收到的结果保留。')
                        history = self.request('/history/' + prompt_id).get(prompt_id)
                    except EngineUnavailable:
                        raise
                    except (TimeoutError, URLError) as error:
                        notify_wait('任务记录读取暂时超时，继续等待同一任务。')
                        continue
                    if history:
                        if history.get('status', {}).get('status_str') == 'error':
                            raise RuntimeError(json.dumps(history['status'], ensure_ascii=False))
                        if cancel.is_set():
                            record(state='cancelled')
                            raise Cancelled('任务已结束，已按取消请求停止后续处理；后端结果保留。')
                        record(state='downloading')
                        images = []; latents = []
                        for output in history.get('outputs', {}).values():
                            for item in output.get('images', []):
                                if item.get('type', 'output') != 'output':
                                    continue
                                path = folder / f'image_{len(images):03d}.png'
                                self._download_output(item,path,emit,cancel,prompt_id)
                                images.append(str(path))
                            for item in output.get('latents', []):
                                if item.get('type', 'output') != 'output': continue
                                path = folder / f'samples_{len(latents):03d}.latent'
                                self._download_output(item,path,emit,cancel,prompt_id)
                                latents.append(str(path))
                        if not images and not (allow_latent_only and latents):
                            if allow_latent_only:
                                raise RuntimeError('工作流执行结束但没有保存图片或潜变量，请检查 SaveLatent / SaveImage 输出节点')
                            raise RuntimeError('工作流执行结束但没有保存图片，请使用 SaveImage 输出节点')
                        record(state='completed')
                        return {'prompt_id': prompt_id, 'images': images, 'latents':latents, 'history': history}
                    if time.monotonic()-heartbeat >= 10:
                        heartbeat=time.monotonic()
                        try:
                            queue=self.request('/queue')
                            running=any(row[1]==prompt_id for row in queue.get('queue_running',[]))
                            pending=any(row[1]==prompt_id for row in queue.get('queue_pending',[]))
                            missing_checks=0 if running or pending else missing_checks+1
                            if missing_checks>=3:
                                raise RuntimeError('后端连续三次既无此任务记录，也无排队或运行记录。可能已重启或清空历史；请查看 submitted.json，当前任务不会自动重新生成。')
                            record(state='cancelling' if cancellation_sent else 'running' if running else 'queued' if pending else 'checking')
                            emit('monitor_status',dict(state))
                        except (TimeoutError,URLError):
                            notify_wait('后端暂时忙碌，继续检查同一任务。')
                if ws is None:
                    if cancellation_sent: time.sleep(1)
                    else: cancel.wait(1)
            raise TimeoutError(f'等待超过 {timeout} 秒；ComfyUI 任务可能仍在执行，任务 ID：{prompt_id}')
        except Exception as exc:
            record(state='cancelled' if isinstance(exc,Cancelled) else 'failed',error=str(exc))
            raise

    def _download_output(self, item, path, emit, cancel, prompt_id):
        """Retry only safe reads. A busy server must not discard completed sampling."""
        while True:
            if cancel.is_set(): raise Cancelled('结果下载已取消，后端生成结果与任务标识保留。')
            try:
                content=self.request('/view?'+urlencode(item),raw=True)
                temporary=path.with_suffix(path.suffix+'.part')
                try:
                    temporary.write_bytes(content)
                    temporary.replace(path)
                finally: temporary.unlink(missing_ok=True)
                return
            except (TimeoutError,URLError):
                emit('monitor_waiting',{'prompt_id':prompt_id,'message':'结果下载暂时超时，重试读取已生成的文件，不会重新生成。'})
                cancel.wait(1)
