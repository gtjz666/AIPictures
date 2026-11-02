"""Lightweight RGB preparation; no segmentation or legacy pose-analysis imports."""
from PIL import Image


def opaque_reference(rgba: Image.Image) -> Image.Image:
    rgba = rgba.convert('RGBA')
    image = Image.new('RGB', rgba.size, (242, 243, 245))
    image.paste(rgba, mask=rgba.getchannel('A'))
    return image
