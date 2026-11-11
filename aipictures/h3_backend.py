"""Optional isolated FreeVideo/VDN-H3 process; no style LoRA or cloud fallback."""
import json
import os
import subprocess
import threading
from pathlib import Path

from .engine import Cancelled


def settings(data: Path) -> dict:
    path=Path(data)/'h3-settings.json'
    if not path.is_file():return {}
    try:
        config=json.loads(path.read_text('utf-8'))
        if not config.get('validated') or not Path(config['python']).is_file():return {}
        if not (Path(config['source'])/'freevideo_engine/cli.py').is_file():return {}
        if not all(Path(config[k]).exists() for k in ('cache','base','checkpoint','model_paths','encoder_root','vdn_root')):return {}
        return config
    except (OSError,ValueError,KeyError):return {}


def generate(folder: Path, params: dict, cancel: threading.Event, emit) -> dict:
    if params.get('motion_reference'):raise ValueError('动作参考需要专用Ref2VA引擎，不能使用静态参考的快速权重。')
    folder=Path(folder)
    if cancel.is_set():raise Cancelled('动画已取消，尚未启动独立引擎。')
    if (folder/'h3-command.json').exists() or (folder/'animation.artifacts').exists():
        raise ValueError('此目录已有生成记录，请先检查旧任务；不会自动重复提交。')
    config=params.get('h3_settings',{})
    if not config.get('validated'):raise ValueError('H3 环境尚未通过本地验证；请先完成独立引擎设置。')
    from .engine import ComfyClient,EngineUnavailable
    from .engine_service import release_idle_models
    try:
        client=ComfyClient(params.get('url') or 'http://127.0.0.1:8188');queue=client.request('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):
            raise ValueError('共享 ComfyUI 正在运行其他任务，请结束后再运行独立 H3。')
        release_idle_models(client)
    except EngineUnavailable:pass
    from .video_generation import generation_prompt
    prompt=generation_prompt(params,bool(params.get('reference')))
    if params['negative'].strip():prompt+='\n避免以下问题：'+params['negative'].strip()
    (folder/'prompt.txt').write_text(prompt,'utf-8')
    target=(folder/'animation.mp4').resolve()
    command=[config['python'],'-u','-m','freevideo_engine','generate','--prompt-file',str((folder/'prompt.txt').resolve()),
        '--cache',config['cache'],'--base',config['base'],'--checkpoint',config['checkpoint'],'--encoder-root',config['encoder_root'],
        '--encoder',config['encoder'],'--model-paths',config['model_paths'],'--seconds',str(params['seconds']),'--width',str(config.get('width',768)),
        '--height',str(config.get('height',1024)),'--seed',str(params['seed']),'--out',str(target),
        '--resource-retries','0','--no-tuning','--two-pass' if params.get('h3_two_pass') else '--no-two-pass']
    if params.get('h3_frames'):
        command[command.index('--seconds')]='--frames';command[command.index('--frames')+1]=str(params['h3_frames'])
    if params.get('h3_continue_video'):
        previous=Path(params['h3_continue_video']).resolve()
        from .workflow_library import digest
        if not params.get('h3_two_pass') or digest(previous)!=params['h3_continue_sha256']:raise ValueError('续接画面已变化或未启用原生续接流程。')
        command+=['--continue-from',str(previous),'--first-frame-reference']
    reuse=params.get('h3_reuse_conditioning')
    if reuse and params.get('h3_continue_video'):raise ValueError('原生视频续接不接受预编码文字入口，请使用本段当前文字重新编码。')
    if reuse:
        from .workflow_library import digest
        if digest(Path(reuse['path']))!=reuse['sha256'] or digest(folder/'prompt.txt')!=reuse['prompt_sha256']:
            raise ValueError('已保存的文字/参考条件与本次任务不一致，不会自动重算或套用。')
        command[command.index('--prompt-file')]='--conditioning'
        command[command.index('--conditioning')+1]=reuse['path']
        media={'version':1,'conditioning_info':reuse['info']}
        (folder/'media.json').write_text(json.dumps(media,ensure_ascii=False),'utf-8')
        command+=['--task',reuse['info']['task'],'--media',str((folder/'media.json').resolve())]
    elif params.get('h3_continue_video'):pass
    elif params.get('continuation_frame'):
        # The generated endpoint already has the target canvas; do not shrink it again.
        media={'version':1,'first':str(Path(params['continuation_frame']).resolve())}
        (folder/'media.json').write_text(json.dumps(media,ensure_ascii=False),'utf-8')
        command+=['--task','i2va','--media',str((folder/'media.json').resolve())]
    elif params.get('reference'):
        from PIL import Image,ImageOps
        with Image.open(params['reference']) as source:
            if source.width*source.height>16_000_000:raise ValueError('参考图超过1600万像素，请先缩小图片。')
            rgba=ImageOps.exif_transpose(source).convert('RGBA')
            rgb=Image.new('RGBA',rgba.size,'#e8e8e8');rgb.alpha_composite(rgba)
            size=(config.get('width',768),config.get('height',1024))
            fitted=ImageOps.contain(rgb.convert('RGB'),(round(size[0]*.9),round(size[1]*.9)),Image.Resampling.LANCZOS)
            canvas=Image.new('RGB',size,'#e8e8e8');canvas.paste(fitted,((size[0]-fitted.width)//2,(size[1]-fitted.height)//2))
            canvas.save(folder/'reference_rgb.png')
        media={'version':1,'first':str((folder/'reference_rgb.png').resolve())}
        (folder/'media.json').write_text(json.dumps(media,ensure_ascii=False),'utf-8')
        command+=['--task','i2va','--media',str((folder/'media.json').resolve())]
    env=dict(os.environ,FREEVIDEO_HOME=config['root'],FREEVIDEO_VDN_ROOT=config['vdn_root'],
        PYTHONUTF8='1',PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1')
    from .storage import write_json
    write_json(folder/'h3-command.json',{'command':command,'cwd':config['source']})
    emit('video_stage',{'message':'正在用独立 H3 引擎生成完整动画…'})
    log=folder/'h3.log'
    with log.open('w',encoding='utf-8') as output:
        if cancel.is_set():raise Cancelled('动画已取消，尚未启动独立引擎。')
        from .owned_process import OwnedProcessJob,gated_module_command
        process=subprocess.Popen(gated_module_command(command),cwd=config['source'],env=env,stdin=subprocess.PIPE,stdout=output,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        owner=None
        if process.poll() is None:
            try:owner=OwnedProcessJob(process.pid)
            except OSError:
                process.terminate();process.wait(timeout=15)
                raise ValueError('无法建立独立任务的退出保护，已停止启动。请查看Windows进程权限。')
        write_json(folder/'h3-process.json',{'pid':process.pid,'status':'running'})
        emit('h3_process',{'pid':process.pid,'owner':owner})
        try:
            if cancel.is_set():raise Cancelled('H3 已取消，尚未进入模型计算。')
            process.stdin.write(b'go\n');process.stdin.flush();process.stdin.close()
            from contextlib import ExitStack
            with ExitStack() as readers:
                streams={};pending={};last_stage='';last_completed=-1
                while process.poll() is None:
                    if cancel.wait(.3):raise Cancelled('H3 已取消，原始结果与日志保留。')
                    lines=[]
                    for path in (log,folder/'animation.engine.log',folder/'animation.encoding.log'):
                        if path not in streams and path.is_file():
                            streams[path]=readers.enter_context(path.open(encoding='utf-8',errors='replace'));pending[path]=''
                        if path in streams:
                            parts=(pending[path]+streams[path].read()).split('\n');pending[path]=parts.pop();lines.extend(parts)
                    for line in lines:
                        try:event=json.loads(line)
                        except ValueError:continue
                        if not isinstance(event,dict):continue
                        completed=event.get('completed_steps');total=event.get('total')
                        if event.get('event')=='decode_progress':emit('video_decode_progress',event)
                        if completed is not None and completed>last_completed and completed>0 and total:
                            emit('progress',{'value':completed,'max':total});last_completed=completed
                        stage=stage_message(event)
                        if stage and stage!=last_stage:
                            emit('video_stage',{'message':stage});last_stage=stage
        finally:
            if owner:owner.close()
            if process.poll() is None:
                if os.name!='nt' or owner is None:process.terminate()
                process.wait(timeout=15)
            write_json(folder/'h3-process.json',{'pid':process.pid,'status':'stopped','returncode':process.returncode})
        if cancel.is_set():raise Cancelled('H3 已取消，结果与日志保留。')
        if process.returncode or not target.is_file():raise ValueError('H3 生成失败，记录保留：'+str(log))
    result={'video':str(target),'backend':'FreeVideo/VDN-H3','style_lora':False}
    rgb=folder/'animation.artifacts/rgb.npy'
    if rgb.is_file():result['native_rgb']=str(rgb.resolve())
    return result


def stage_message(event: dict) -> str:
    name=event.get('event','')
    if name in ('reference_assets_download','sampling_preset_download'):
        total=event.get('total_bytes') or 1
        return f"准备音画续接数据 · {round(100*event.get('done_bytes',0)/total)}%"
    if name=='prepared_blocks':return f"加载动画模型 · {event.get('blocks',0)}/{event.get('total',0)} 个模块"
    if name=='model_load_phase':return '正在加载动画模型…'
    if name.startswith('sampling_'):return f"制作完整动画 · 已完成 {event.get('completed_steps',0)}/{event.get('total',8)} 步"
    if name=='decode_progress':return f"解码原生动画 · {event.get('done',0)}/{event.get('total',0)} 帧"
    if name.startswith('decode') or name=='sample_finalize':return '采样已完成，正在解码完整动画…'
    if name in ('encoding_start','encode_start','text_encode_start'):return '正在理解文字与参考图…'
    return ''
