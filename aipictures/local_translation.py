"""Small CPU-only translation in a disposable process, outside Qt's environment."""
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from .engine import Cancelled


def settings(data: Path) -> dict:
    path = Path(data)/'translator-settings.json'
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text('utf-8'))
    except (OSError,ValueError):
        return {}
    model, python = Path(config.get('model_dir','')), Path(config.get('python',''))
    if not model.is_dir() or not python.is_file() or not (model/'pytorch_model.bin').is_file():
        return {}
    return config


def needed(text: str) -> bool:
    return bool(re.search(r'[\u3400-\u9fff]',text))


def translate(prompt: str, negative: str, config: dict, cancel: threading.Event) -> dict:
    if not needed(prompt+negative):
        return {'positive':prompt,'negative':negative,'translated':False}
    if cancel.is_set():
        raise Cancelled('翻译已取消。')
    # MT trained on prose can misread art terms (e.g. 五官 -> five officials).
    # Protect existing, explicit art vocabulary before neural translation.
    from .general_image import positive_text
    from .prompt_text import negative_text
    glossary={'动漫女孩':'anime girl','女孩':'girl','男孩':'boy','五官模糊':'blurry facial features',
        '自然站立':'natural standing pose','双手放在身体两侧':'both hands at the sides',
        '游戏道具':'game item','玻璃小瓶':'small glass bottle','玻璃瓶':'glass bottle',
        '中装有':'containing','装满':'filled with','发光':'glowing','药水':'potion',
        '软木塞':'cork stopper','封口':'sealed','物件居中':'centered object',
        '浅灰色背景':'plain light gray background','轮廓清晰':'clear silhouette',
        '成年女性':'adult woman','成年男性':'adult man','冒险者':'adventurer',
        '双手清楚可见':'both hands clearly visible','平涂配色':'flat colors'}
    for source,target in sorted(glossary.items(),key=lambda pair:-len(pair[0])):
        prompt = prompt.replace(source,' '+target+' ')
        negative = negative.replace(source,' '+target+' ')
    prompt = positive_text(prompt)[0]
    negative = negative_text(negative)[0]
    prompt = re.sub(r'穿(?=\s*[A-Za-z])','wearing ',prompt)
    for source,target in {'五官':'facial features'}.items():
        prompt = prompt.replace(source,target)
        negative = negative.replace(source,target)
    if not needed(prompt+negative):
        return {'positive':prompt,'negative':negative,'translated':True,'method':'art_glossary','device':'cpu'}
    script = Path(__file__).resolve().parents[1]/'tools'/'translate_prompt.py'
    payload = json.dumps({'positive':prompt,'negative':negative,'model_dir':config['model_dir']},ensure_ascii=False)
    process = subprocess.Popen([config['python'],str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,encoding='utf-8',
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    deadline = time.monotonic()+min(180,max(15,float(config.get('timeout_seconds',60))))
    try:
        while True:
            if cancel.is_set():
                raise Cancelled('翻译已取消，未提交生图任务。')
            if time.monotonic()>deadline:
                raise TimeoutError('本地翻译超过等待时限，未提交生图；可关闭“中文转英文”后自行输入英文。')
            try:
                output,error = process.communicate(input=payload,timeout=.15)
                break
            except subprocess.TimeoutExpired:
                payload = None
        if process.returncode:
            raise ValueError('本地翻译运行失败，未提交生图。请检查独立模型/运行环境，或关闭翻译后输入英文。')
        result = json.loads(output)
        for name in ('positive','negative'):
            if not isinstance(result.get(name),str) or len(result[name])>24000:
                raise ValueError('翻译返回无效结果，未提交生图。')
        if prompt.strip() and not result['positive'].strip():
            raise ValueError('翻译未返回画面描述，未提交生图。')
        return result
    finally:
        if process.poll() is None:
            if sys.platform=='win32':
                # venv python.exe may be a launcher with a child; stop only our own tree.
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,timeout=3)
            else:
                process.terminate()
            try: process.communicate(timeout=2)
            except subprocess.TimeoutExpired: process.kill(); process.communicate(timeout=2)
