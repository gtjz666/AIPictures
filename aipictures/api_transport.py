"""Cancellable HTTPS transport. Auth stays on the configured origin; POST is never retried."""
import asyncio
import contextlib
import json
import re
import threading
from urllib.parse import urlsplit
from urllib.request import getproxies, proxy_bypass

import httpx

from .api_config import AuthEndpoint, loopback
from .engine import Cancelled

MAX_JSON = 72 * 1024 * 1024
MAX_IMAGE = 32 * 1024 * 1024


class ApiError(RuntimeError):
    pass


def redact(value: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, '[密钥已隐藏]')
    value = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [已隐藏]', value)
    value = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[密钥已隐藏]', value)
    value = re.sub(r'data:image/\S+', '[图片内容已省略]', value)
    value = re.sub(r'https?://\S+', '[服务地址已省略]', value)
    return value[:700]


async def cancellable(awaitable, cancel: threading.Event):
    task = asyncio.create_task(awaitable)
    try:
        while not task.done():
            if cancel.is_set():
                raise Cancelled('已取消本地等待；服务端可能仍在处理并计费，未自动重新提交。')
            await asyncio.wait({task}, timeout=.08)
        if cancel.is_set():
            raise Cancelled('已取消本地等待；已接收的本地文件保留。')
        return await task
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def run(awaitable, cancel: threading.Event, timeout: int | None = None):
    async def bounded():
        try:
            return await asyncio.wait_for(cancellable(awaitable,cancel),timeout)
        except asyncio.TimeoutError as exc:
            raise ApiError('API 等待超时，未自动重试；服务端可能已处理，请核对平台记录。') from exc
    return asyncio.run(bounded())


def _client(url: str, timeout: int) -> httpx.AsyncClient:
    host = urlsplit(url).hostname or ''
    proxy = None
    if not loopback(host) and not proxy_bypass(host):
        proxy = getproxies().get(urlsplit(url).scheme)
    return httpx.AsyncClient(proxy=proxy, trust_env=False, follow_redirects=False,
        timeout=httpx.Timeout(timeout, connect=10, write=30, pool=10))


async def request(auth: AuthEndpoint, route: str, *, payload=None, files=None,
                  limit: int = MAX_JSON, require_model: bool = True) -> dict:
    auth = auth.validate(require_model)
    url = auth.endpoint.base_url + route
    headers = ({'x-goog-api-key': auth.key} if auth.endpoint.protocol == 'gemini'
               else {'Authorization': 'Bearer ' + auth.key})
    headers['Accept'] = 'application/json'
    try:
        async with _client(url, auth.endpoint.timeout) as client:
            kwargs = {'files': files, 'data': payload} if files else {'json': payload}
            async with client.stream('GET' if payload is None else 'POST', url, headers=headers, **kwargs) as response:
                if 300 <= response.status_code < 400:
                    raise ApiError('服务返回重定向，未转发 Key；请填写服务商最终 API 基础地址。')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > (min(limit, 64 * 1024) if response.is_error else limit):
                        raise ApiError('服务返回的数据过大，已停止接收；没有重新提交。')
                if response.is_error:
                    reason = {401: 'Key 无效或已过期', 403: '该 Key 没有此模型权限',
                        404: '地址、接口或模型不存在，请核对服务商协议',
                        429: '额度不足或请求过于频繁'}.get(response.status_code, '服务请求失败')
                    detail = ''
                    try:
                        error = json.loads(body).get('error', {})
                        detail = error.get('message', '') if isinstance(error, dict) else str(error)
                    except (ValueError, AttributeError):
                        pass
                    raise ApiError(f'{reason}（HTTP {response.status_code}）。' + redact(detail, auth.key) +
                        ' 未自动重试；已提交请求是否收费以平台记录为准。')
                try:
                    data = json.loads(body)
                except ValueError as exc:
                    raise ApiError('服务没有返回 JSON，请核对是否为兼容 API 地址。未自动重试。') from exc
                if not isinstance(data, dict):
                    raise ApiError('服务返回格式无效，应为 JSON 对象。')
                return data
    except httpx.TimeoutException as exc:
        raise ApiError('API 等待超时，未自动重试；请求可能已被服务端处理，请先核对平台记录。') from exc
    except httpx.HTTPError as exc:
        raise ApiError('API 连接中断，未自动重试；请检查地址、网络或系统代理，并核对平台请求记录。') from exc


async def image_download(url: str, auth: AuthEndpoint) -> bytes:
    # Never send a provider Key to an image host, including redirects or signed URLs.
    for _ in range(6):
        if auth.key in url:
            raise ApiError('图片下载地址包含 API Key，已阻止转发。')
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        allowed_local = loopback(host) and loopback(urlsplit(auth.endpoint.base_url).hostname or '')
        if not host or parsed.username or parsed.password or parsed.fragment or (
                parsed.scheme != 'https' and not (parsed.scheme == 'http' and allowed_local)):
            raise ApiError('服务返回了不安全的图片下载地址。')
        if loopback(host) and not allowed_local:
            raise ApiError('远程服务不能指定本机图片下载地址。')
        try:
            async with _client(url, auth.endpoint.timeout) as client:
                async with client.stream('GET', url) as response:
                    if response.is_redirect:
                        from urllib.parse import urljoin
                        url = urljoin(url, response.headers.get('location', ''))
                        continue
                    if response.is_error:
                        raise ApiError(f'图片下载失败（HTTP {response.status_code}），没有重新生图。')
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_IMAGE:
                            raise ApiError('返回图片超过 32MB，已停止下载。')
                    return bytes(body)
        except httpx.HTTPError as exc:
            raise ApiError('图片下载中断；不会因此重新调用生图接口。') from exc
    raise ApiError('图片下载重定向过多。')


def list_models(auth: AuthEndpoint, cancel: threading.Event) -> list[str]:
    route = '/models?pageSize=1000' if auth.endpoint.protocol == 'gemini' else '/models'
    data = run(request(auth, route, require_model=False), cancel, auth.endpoint.timeout)
    items = data.get('data', data.get('models', []))
    if not isinstance(items, list):
        raise ApiError('接口没有返回模型列表；可以手动填写服务商给出的模型 ID。')
    ids = [item.get('id', item.get('name', '')) for item in items if isinstance(item, dict)]
    return sorted({name.removeprefix('models/') for name in ids if isinstance(name, str) and
                   0 < len(name) <= 200 and auth.key not in name and not any(ord(c)<33 for c in name)})
