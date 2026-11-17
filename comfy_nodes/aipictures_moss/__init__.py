"""Private MOSS stage packets. Reuses the exact safetensors checkpoint format."""
from pathlib import Path
import folder_paths
from .stream_weights import install_stream_loader
from .conditioning import save_packet,load_packet,SaveConditioning
install_stream_loader()


class SaveMoss:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'positive':('CONDITIONING',),'negative':('CONDITIONING',),'latent':('LATENT',)}}
 RETURN_TYPES=();FUNCTION='save';OUTPUT_NODE=True;CATEGORY='AIPictures/MOSS'
 def save(self,positive,negative,latent):
  save_packet(dict(positive=positive,negative=negative),latent,Path(folder_paths.get_output_directory())/'conditioning')
  return {'ui':{'latents':[dict(filename=n,subfolder='conditioning',type='output') for n in ('conditioning.safetensors','conditioning.json')]}}


class LoadMoss:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'manifest':('STRING',{'default':'conditioning/conditioning.json'})}}
 RETURN_TYPES=('CONDITIONING','CONDITIONING','LATENT');FUNCTION='load';CATEGORY='AIPictures/MOSS'
 def load(self,manifest):
  root=Path(folder_paths.get_input_directory()).resolve();path=(root/manifest).resolve(strict=True)
  if not path.is_relative_to(root):raise ValueError('Packet outside this task')
  pair,latent=load_packet(path);return pair['positive'],pair['negative'],latent


NODE_CLASS_MAPPINGS={'AIPicturesMossSave':SaveMoss,'AIPicturesMossLoad':LoadMoss,'AIPicturesSaveConditioning':SaveConditioning}
