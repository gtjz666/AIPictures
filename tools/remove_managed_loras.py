"""Remove only byte-identical AIPictures LoRAs listed in its own installation receipts."""
import argparse
import json
from pathlib import Path

from aipictures.storage import write_json
from aipictures.workflow_library import digest


def remove(receipts: list[Path], model_root: Path, report: Path) -> dict:
    root = Path(model_root).resolve()/'loras'/'AIPictures'
    catalog=json.loads((Path(__file__).resolve().parents[1]/'aipictures/resources/lora_catalog.json').read_text('utf-8'))
    allowed={row['filename'].replace('\\','/').removeprefix('AIPictures/'):row['download']['sha256'] for row in catalog['models']}
    allowed['animation/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors']='85c4a61c30e0497aa44b91d93a893b624708461a56fe5485183b28fa07e2dfb3'
    result={'deleted':[],'skipped':[],'reclaimed_bytes':0,'scope':str(root),'style_lora_enabled':False}
    seen=set()
    for receipt in receipts:
        for row in json.loads(Path(receipt).read_text('utf-8')).get('files',[]):
            path=Path(row['path'])
            if str(path) in seen:continue
            seen.add(str(path))
            resolved=path.resolve()
            if path.suffix.lower()!='.safetensors' or not resolved.is_relative_to(root):continue
            relative=resolved.relative_to(root).as_posix()
            if relative not in allowed or row.get('sha256')!=allowed[relative]:
                result['skipped'].append({'path':str(path),'reason':'not a publisher-verified managed LoRA'});continue
            if not path.is_file():continue
            if path.is_symlink() or path.stat().st_size!=row['bytes'] or digest(path)!=allowed[relative]:
                result['skipped'].append({'path':str(path),'reason':'modified or linked file preserved'});continue
            # Recheck the absolute resolved target immediately before deleting this one file.
            if path.resolve()!=resolved or not resolved.is_relative_to(root):raise ValueError('Model path changed; stopped.')
            size=path.stat().st_size
            path.unlink()
            result['deleted'].append(dict(row));result['reclaimed_bytes']+=size
            write_json(report,result)
    write_json(report,result)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--models',type=Path,required=True)
    p.add_argument('--receipt',type=Path,action='append',required=True);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    from aipictures.engine import ComfyClient,EngineUnavailable
    try:
        client=ComfyClient();queue=client.request('/queue')
        if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('后端有任务，暂不删除模型。')
        client.request('/free',{'unload_models':True,'free_memory':True})
    except EngineUnavailable:pass
    result=remove(args.receipt,args.models,args.report)
    print(json.dumps({'deleted':len(result['deleted']),'reclaimed_bytes':result['reclaimed_bytes'],'skipped':len(result['skipped'])}))


if __name__=='__main__':main()
