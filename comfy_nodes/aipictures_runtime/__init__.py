"""Release completed encoders before Wan conditions; keep official VAE math unchanged."""
import time

from comfy_api.latest import ComfyExtension, io
from comfy_extras.nodes_wan import WanAnimateToVideo, WanImageToVideo
import comfy.model_management as memory
from server import PromptServer


class _PrepareConditions:
    @classmethod
    def define_schema(cls):
        schema = super().define_schema()
        schema.node_id = cls.NODE_ID
        schema.display_name = 'AIPictures · 分阶段编码动画条件'
        schema.category = 'AIPictures/runtime'
        return schema

    @classmethod
    def execute(cls, **kwargs):
        server = PromptServer.instance
        def notify(message):
            server.send_sync('aipictures_stage',{'message':message,'node':server.last_node_id,
                'phase':'condition_encode'},server.client_id)
        notify('释放已完成的文字与参考编码器，准备动画条件…')
        # Their embeddings are already computed. This does not alter any prompt, VAE,
        # precision, image size or frame. Comfy executes one prompt at a time.
        memory.unload_all_models()
        memory.soft_empty_cache()
        original_vae = kwargs['vae']
        started = time.monotonic()
        class ObservedVAE:
            def __init__(self): self.calls = 0
            def __getattr__(self,name): return getattr(original_vae,name)
            def encode(self,pixels):
                self.calls += 1
                total=3 if kwargs.get('pose_video') is not None else 1
                notify(f'编码动画条件 {self.calls}/{total} · {pixels.shape[0]} 张输入 · 已用 {time.monotonic()-started:.0f} 秒')
                return original_vae.encode(pixels)
        kwargs['vae'] = ObservedVAE()
        result = super().execute(**kwargs)
        notify(f'动画条件编码完成 · {time.monotonic()-started:.1f} 秒，准备动作采样…')
        return result


class AIPicturesWanAnimateToVideo(_PrepareConditions,WanAnimateToVideo):
    NODE_ID='AIPicturesWanAnimateToVideo'


class AIPicturesWanImageToVideo(_PrepareConditions,WanImageToVideo):
    NODE_ID='AIPicturesWanImageToVideo'


class AIPicturesReleaseCompletedEncoders(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='AIPicturesReleaseCompletedEncoders',category='AIPictures/runtime',
            inputs=[io.Model.Input('model'),io.Conditioning.Input('conditioning')],outputs=[io.Model.Output()])

    @classmethod
    def execute(cls,model,conditioning):
        memory.unload_all_models();memory.soft_empty_cache()
        return io.NodeOutput(model)


class RuntimeExtension(ComfyExtension):
    async def get_node_list(self):
        return [AIPicturesWanAnimateToVideo,AIPicturesWanImageToVideo,AIPicturesReleaseCompletedEncoders]


async def comfy_entrypoint():
    return RuntimeExtension()
