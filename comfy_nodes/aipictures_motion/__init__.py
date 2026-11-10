"""Only installed into the application-owned H3 subprocess."""
from .stream_weights import install_stream_loader
install_stream_loader()
from .frames import AIPicturesMotionFrames
from .conditioning import SaveConditioning,LoadConditioning,SaveAudioLatent
NODE_CLASS_MAPPINGS={
 'AIPicturesMotionFrames':AIPicturesMotionFrames,
 'AIPicturesSaveConditioning':SaveConditioning,
 'AIPicturesLoadConditioning':LoadConditioning,
 'AIPicturesSaveAudioLatent':SaveAudioLatent,
}
