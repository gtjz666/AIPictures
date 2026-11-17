"""Register only after separate local layout and reference-edit execution evidence."""
import argparse,json
from pathlib import Path
from PIL import Image
from aipictures.storage import write_json
from aipictures import moss_image as moss


def register(config,layout_proof,edit_proof,destination):
 c=json.loads(Path(config).read_text('utf-8'));proofs=[]
 for mode,path in [('layout',Path(layout_proof)),('edit',Path(edit_proof))]:
  request=json.loads((path/'request.json').read_text('utf-8'));result=json.loads((path/'result.json').read_text('utf-8'))
  if request['moss_mode']!=mode or result['protocol']!=moss.PROTOCOL or request['moss_settings']['models']!=c['models']:raise ValueError('Evidence / model mismatch')
  checks=json.loads((path/'model-verification.json').read_text('utf-8'))
  if {(r['path'],r['sha256']) for r in checks}!={(r['path'],r['sha256']) for r in c['models']}:raise ValueError('Model verification missing')
  for stage in ['encode','sample','decode']:
   if json.loads((path/stage/'process.json').read_text('utf-8'))['status']!='stopped':raise ValueError('An inference stage is still running')
  with Image.open(result['images'][0]) as im:
   if im.size!=(request['width'],request['height']):raise ValueError('Unexpected output dimensions')
  proofs.append(dict(mode=mode,path=str(path.resolve()),elapsed_seconds=result['elapsed_seconds']))
 c.update(validated=True,validated_modes=['layout','edit'],edit_experimental=True,protocol=moss.PROTOCOL,execution_evidence=proofs,prompt_expander=False)
 dest=Path(destination)
 if dest.exists():
  backup=dest.with_name(dest.name+'.before-moss-registration.json')
  if backup.exists():raise ValueError('Keep the previous settings backup before registering again')
  write_json(backup,json.loads(dest.read_text('utf-8')))
 write_json(dest,c,durable=True);return c


def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--layout-proof',type=Path,required=True);p.add_argument('--edit-proof',type=Path,required=True);p.add_argument('--destination',type=Path,required=True);a=p.parse_args()
 register(a.config,a.layout_proof,a.edit_proof,a.destination);print('MOSS registered: layout + experimental community reference editing')


if __name__=='__main__':main()
