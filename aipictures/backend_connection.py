"""Reuse Comfy Desktop's actual local server, without starting a second model host."""
import json
import os
import re
import subprocess
from urllib.parse import urlparse

from .engine import ComfyClient


def local_processes():
    if os.name != 'nt':
        return []
    script = ("Get-CimInstance Win32_Process | Where-Object { "
              "$_.Name -match '^python(w)?\\.exe$|^Comfy( Desktop|UI)?\\.exe$' } | "
              "Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=8)
        rows = json.loads(result.stdout or '[]')
        return [rows] if isinstance(rows, dict) else rows
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def desktop_urls(rows):
    by_id = {row['ProcessId']: row for row in rows}
    found = []
    for row in rows:
        command = row.get('CommandLine') or ''
        if not re.search(r'(?:^|[\\/\s"])main\.py(?:"|\s|$)', command, re.I):
            continue
        parent = row
        for _ in range(5):
            parent = by_id.get(parent.get('ParentProcessId'))
            if not parent:
                break
            if re.fullmatch(r'Comfy(?: Desktop|UI)?\.exe', parent.get('Name', ''), re.I):
                port = re.search(r'--port(?:\s+|=)(\d+)', command)
                number = int(port.group(1)) if port else 8188
                if 1 <= number <= 65535:
                    url = f'http://127.0.0.1:{number}'
                    if url not in found:
                        found.append(url)
                break
    return found


def reachable(url):
    try:
        data = ComfyClient(url).request('/system_stats', timeout=2)
        return isinstance(data, dict) and 'system' in data and 'devices' in data
    except Exception:
        return False


def shared_backend_url(requested, rows=None):
    """Custom ports stay explicit. Standard local connections prefer the open Desktop.

    The caller must pin its existing client until its own queued tasks have finished.
    A discovery failure never terminates or reconfigures another server.
    """
    requested = ComfyClient(requested.strip()).url
    parsed = urlparse(requested)
    if parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.port not in (8188, 8189):
        return requested
    for url in desktop_urls(local_processes() if rows is None else rows):
        if reachable(url):
            return url
    return requested
