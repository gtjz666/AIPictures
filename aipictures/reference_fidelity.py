"""Explicit reference policy: source appearance wins over text in preserve mode."""
from .action_intent import ACTION_EN

PRESERVE_POSITIVE = ('the exact same single subject as the reference image, preserve original species, '
    'face, eye shape, hairstyle, hair color, outfit, garment patterns, accessories, footwear, '
    'body proportions, original colors, shading, linework and art style, no redesign')
PRESERVE_NEGATIVE = ('different identity, different species, changed face, changed eyes, changed hairstyle, '
    'changed outfit, changed accessories, changed colors, missing patterns, missing details, redesign')


def reference_positive(intent):
    # Only an action can change the reference; appearance prose cannot recolor it implicitly.
    return PRESERVE_POSITIVE + (', '+ACTION_EN[intent.action] if intent.action in ACTION_EN else '')


def effective_denoise(value, preserve):
    return min(float(value), .25) if preserve else float(value)
