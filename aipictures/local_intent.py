"""On-demand local VLM, strict output, cancellation and process-owned GPU lifetime."""
import asyncio
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx

from .engine import Cancelled
from .intent_plan import SCHEMA, SYSTEM, parse_plan, route
from .owned_process import OwnedProcessJob
from .storage import write_json


def settings(data: Path, *, require_validated: bool = True) -> dict | None:
    path = Path(data)/'local-intent-settings.json'
    if not path.is_file():
        return None
    try:
        config = json.loads(path.read_text('utf-8'))
        if config.get('schema_version') != 1 or require_validated and not config.get('validated'):
            return None
        if any(not Path(config[k]).is_file() for k in ('server', 'model', 'projector')):
            return None
        if not 4096 <= config['context'] <= 16384 or not 256 <= config['max_tokens'] <= 3000 or not 30 <= config['timeout'] <= 600:
            return None
        return config
    except (OSError, KeyError, TypeError, ValueError):
        return None


class LocalSession:
    """Never attaches to an existing service, never terminates a shared process."""
    def __init__(self, config: dict, folder: Path, cancel: threading.Event, emit):
        self.config, self.folder, self.cancel, self.emit = config, folder, cancel, emit
        self.process = self.job = self.log = None

    def check(self):
        if self.cancel.is_set():
            raise Cancelled('需求识别已取消；没有提交生成。')

    def command(self, port: int) -> list[str]:
        return [self.config['server'], '-m', self.config['model'], '--mmproj', self.config['projector'],
                '--alias', 'local-intent',
                '--host', '127.0.0.1', '--port', str(port), '-c', str(self.config['context']),
                '-ngl', '99', '-np', '1', '-t', '6', '-b', '256', '-ub', '128',
                '--flash-attn', 'on', '--no-warmup', '--no-webui']

    def __enter__(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self.check()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            self.url = f'http://127.0.0.1:{port}'
            command = self.command(port)
            write_json(self.folder/'runtime.json', dict(command=command, private=True, network='loopback only'))
            self.log = (self.folder/'runtime.log').open('wb')
            self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT,
                cwd=str(Path(self.config['server']).parent), creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.job = OwnedProcessJob(self.process.pid)
            self.emit('intent_stage', {'message': '正在加载本地识别模型…'})
            deadline = time.monotonic() + 90
            with httpx.Client(trust_env=False, timeout=1) as client:
                while time.monotonic() < deadline:
                    self.check()
                    if self.process.poll() is not None:
                        raise RuntimeError('本地识别引擎启动失败，请查看本次 runtime.log；未提交生成。')
                    try:
                        if client.get(self.url+'/health').status_code == 200:
                            return self
                    except httpx.HTTPError:
                        pass
                    self.cancel.wait(.2)
            raise TimeoutError('本地识别模型启动超时，已释放本次进程；可重新整理需求。')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    async def _request(self, payload):
        async with httpx.AsyncClient(trust_env=False, timeout=self.config['timeout']) as client:
            async with client.stream('POST', self.url+'/v1/chat/completions', json=payload) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 2 * 1024**2:
                        raise ValueError('识别输出过大，已停止；未提交生成。')
                if response.status_code != 200:
                    raise ValueError(f'本地识别请求失败（{response.status_code}），请查看运行日志。')
                return json.loads(body)

    def complete(self, messages, *, schema=None, max_tokens=None):
        from .api_transport import cancellable
        payload = dict(model='local-intent', messages=messages, temperature=.1, seed=42,
            max_tokens=max_tokens or self.config['max_tokens'], stream=False,
            response_format={'type': 'json_schema', 'json_schema': {'name': 'art_intent', 'strict': True, 'schema': schema or SCHEMA}})
        async def bounded():
            return await asyncio.wait_for(cancellable(self._request(payload), self.cancel), self.config['timeout'])
        self.emit('intent_stage', {'message': '正在识别素材、动作与生成目标…'})
        try:
            data = asyncio.run(bounded())
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise TimeoutError('本地需求识别超时，已停止并释放引擎；原输入保留，没有重复提交。') from exc
        self.check()
        try:
            choice = data['choices'][0]
            if choice.get('finish_reason') != 'stop':
                write_json(self.folder/'incomplete-response.json', data)
                raise ValueError('识别输出未完成；请缩短描述或减少参考片段。')
            return choice['message']['content'], dict(usage=data.get('usage'), timings=data.get('timings'))
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError('本地识别返回无效，未提交生成。') from exc

    def __exit__(self, *_):
        if self.job:
            self.job.close()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=5)
        if self.log:
            self.log.close()


def analyze(config: dict, brief: str, negative: str, reference: Path | None, motion: Path | None,
            folder: Path, cancel: threading.Event, emit=lambda *_: None, *, selected_kind='image',
            role='appearance', start=0., seconds=8., output_seconds=4., session_factory=LocalSession) -> dict:
    """No generation here. Output references an allowlisted route, never arbitrary tools."""
    from .intent_media import prepare
    from .workflow_library import digest
    if not isinstance(brief, str) or not brief.strip() or len(brief) > 12000 or len(negative) > 6000:
        raise ValueError('请描述生成目标；需求不超过12000字，反向要求不超过6000字。')
    if selected_kind not in ('image', 'animation'):
        raise ValueError('请选择图片或动画。')
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    write_json(folder/'request.json', dict(brief=brief, negative=negative, selected_kind=selected_kind,
        role=role, motion_start=start, motion_seconds=seconds, output_seconds=output_seconds, status='analyzing'))
    try:
        emit('intent_stage', {'message': '正在读取素材及原始动作时间…'})
        content, evidence = prepare(reference, motion, folder, cancel, role=role, start=start, seconds=seconds)
        details = dict(user_request=brief, original_negative_constraints=negative, selected_kind=selected_kind,
            requested_output_seconds=output_seconds, reference_roles=[{'id': a['id'], 'role': a['role']} for a in evidence['assets']],
            motion_source_duration=evidence['duration'])
        details['analysis_matte_is_not_background'] = any(a.get('analysis_matte_only') for a in evidence['assets'])
        task = ('按时间对比动作帧，分解可见的准备、伸展/接触、回收阶段。时间轴与正向词都要具体描述肢体、头和躯干的变化，不能只写模仿动作。'
                if motion else '按需求整理单张画面；明确请求的视角、风格与背景变化必须保留。')
        task += ' 外观图与动作图用途独立。输出成品描述，排除词只用用户明确排除的内容；未指定的背景省略。'
        messages = [{'role': 'system', 'content': SYSTEM},
                    {'role': 'user', 'content': [{'type': 'text', 'text': json.dumps(details, ensure_ascii=False)}, *content,
                                                 {'type': 'text', 'text': task}]}]
        with session_factory(config, folder, cancel, emit) as session:
            if evidence['assets']:
                from .intent_observation import observe
                emit('intent_stage', {'message': '正在分别观察外观与逐帧动作…'})
                observations = observe(session, content, evidence, folder)
                # Planning sees factual observations, not mixed-purpose images.
                details['visual_observations'] = observations
                messages[1]['content'] = [{'type': 'text', 'text': json.dumps(details, ensure_ascii=False)},
                                          {'type': 'text', 'text': task}]
            output, stats = session.complete(messages)
            if evidence['assets']:
                # Validate structure before any optional, bounded text-only repair.
                parse_plan(output, {a['id'] for a in evidence['assets']}, evidence['duration'])
                from .intent_quality import repair_anatomy
                output = repair_anatomy(session, output, observations, brief, folder)
        # The process is gone before a caller can submit a GPU generation.
        if cancel.is_set():
            raise Cancelled('需求识别已取消；没有提交生成。')
        write_json(folder/'response.json', dict(content=output, **stats))
        plan = parse_plan(output, {a['id'] for a in evidence['assets']}, evidence['duration'])
        if evidence['assets']:
            from dataclasses import replace
            facts = []
            if 'appearance' in observations:
                facts.append(dict(asset='appearance', description='；'.join(observations['appearance'].values())[:1800]))
            if 'motion' in observations:
                facts.append(dict(asset='motion', description=observations['motion']['camera']))
            plan = replace(plan, observations=facts)
        if plan.kind != selected_kind:
            from dataclasses import replace
            title = '动画' if plan.kind == 'animation' else '单张图片'
            plan = replace(plan, questions=[*plan.questions, f'需求更像{title}，请确认并切换生成类型后重新发送。'])
        for asset in evidence['assets']:
            if digest(Path(asset['source'])) != asset['sha256']:
                raise ValueError('识别期间素材发生变化，请重新导入；未提交生成。')
        # Never silently drop an explicitly supplied exclusion.
        if negative.strip() and negative.strip() not in plan.negative_prompt:
            from dataclasses import replace
            plan = replace(plan, negative_prompt=(plan.negative_prompt+'\n'+negative.strip()).strip())
        selected_route = None if plan.questions else route(plan, reference=bool(reference), motion=bool(motion))
        result = dict(schema_version=1, plan=plan.to_dict(), route=selected_route, evidence=evidence,
            request=dict(brief=brief, negative=negative, selected_kind=selected_kind, reference_role=role),
            elapsed_seconds=round(time.monotonic()-started, 3), model=config.get('name'),
            engine_released=True, status='needs_input' if plan.questions else 'ready')
        if evidence['assets'] and 'motion' in observations:
            rows = observations['motion']['frames']
            end = next(a['end'] for a in evidence['assets'] if a['id']=='motion')
            # The review timeline covers all sampled evidence even if the planner
            # summarizes only some phases. It describes SOURCE poses, not a rig.
            result['reference_timeline'] = [dict(start=row['time'], end=rows[i+1]['time'] if i+1<len(rows) else end,
                                               description=row['pose']) for i, row in enumerate(rows)]
        write_json(folder/'plan.json', result)
        return result
    except BaseException as exc:
        write_json(folder/'failure.json', dict(status='cancelled' if cancel.is_set() else 'failed', error=str(exc),
                                              elapsed_seconds=round(time.monotonic()-started, 3)))
        raise
