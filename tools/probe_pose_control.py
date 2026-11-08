"""Offline, CPU-only DWPose input audit. Never launches generation or edits UI.

Uses the installed controlnet_aux pre/postprocessor directly. A full-image box
is intentional for this single-actor diagnostic, not a validated person detector.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


POSE_SHA = '724f4ff2439ed61afb86fb8a1951ec39c6220682803b4a8bd4f598cd913b1843'
BODY_NAMES = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
              'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
              'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
              'left_knee', 'right_knee', 'left_ankle', 'right_ankle')
EDGES = ((5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
         (11, 12), (11, 13), (13, 15), (12, 14), (14, 16))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rgba_rgb(image):
    from PIL import Image
    rgba = image.convert('RGBA')
    bg = Image.new('RGBA', rgba.size, (127, 127, 127, 255))
    return Image.alpha_composite(bg, rgba).convert('RGB')


def source_samples(path, seconds):
    from PIL import Image
    # Pillow seeks GIFs with their compositing/disposal intact. Read PTS before
    # choosing samples; no interpolated frames or inferred actions.
    with Image.open(path) as gif:
        pts, frames, durations, elapsed = [], [], [], 0
        for i in range(gif.n_frames):
            gif.seek(i)
            duration = int(gif.info.get('duration', 100))
            if duration <= 0:
                raise ValueError('GIF contains a nonpositive frame duration')
            pts.append(elapsed / 1000)
            durations.append(duration)
            frames.append(rgba_rgb(gif))
            elapsed += duration
    result = []
    for t in seconds:
        if not 0 <= t < elapsed / 1000:
            raise ValueError('Sample timestamp outside source')
        index = max(i for i, start in enumerate(pts) if start <= t + 1e-9)
        result.append((f'source {t:.2f}s / frame {index}', frames[index],
                       dict(requested_time=t, source_frame=index, source_pts=pts[index])))
    return result, dict(frame_count=len(frames), duration=elapsed / 1000,
                        timestamps=pts, durations_ms=durations)


def draw_overlay(image, points, scores, threshold=.3):
    from PIL import ImageDraw
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    colors = ('#ff6030', '#32d8ff', '#e45dff', '#50e343')
    for n, (a, b) in enumerate(EDGES):
        if min(scores[a], scores[b]) >= threshold:
            draw.line((tuple(points[a]), tuple(points[b])), fill=colors[n % 4], width=3)
    for i in range(17):
        if scores[i] < threshold:
            continue
        x, y = map(float, points[i])
        draw.ellipse((x-3, y-3, x+3, y+3), fill='#ffff00', outline='black')
        draw.text((x+4, y-4), str(i), fill='black', stroke_width=1, stroke_fill='white')
    return overlay


def run(args):
    if args.folder.exists():
        raise ValueError('Refusing to overwrite an existing probe directory')
    if digest(args.model) != POSE_SHA:
        raise ValueError('DWPose checksum differs from publisher; leaving it untouched')
    if args.packages:
        sys.path.insert(0, str(args.packages.resolve()))
    import cv2
    import numpy as np
    import onnxruntime as ort
    from PIL import Image, ImageDraw, ImageOps
    helper = args.aux / 'src/custom_controlnet_aux/dwpose/dw_onnx/cv_ox_pose.py'
    spec = importlib.util.spec_from_file_location('aipictures_probe_dwpose_inference', helper)
    preprocessor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preprocessor)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(args.model), sess_options=options,
                                  providers=['CPUExecutionProvider'])
    shape = session.get_inputs()[0].shape
    input_size = (int(shape[-1]), int(shape[-2]))
    samples, source_meta = source_samples(args.source, args.seconds)
    with Image.open(args.target) as image:
        samples.append(('target appearance (not source motion)', rgba_rgb(image), dict(target=True)))
    args.folder.mkdir(parents=True)
    rows, cards = [], []
    for i, (label, image, meta) in enumerate(samples):
        started = time.perf_counter()
        # Aux receives RGB from its public detector, not OpenCV's default BGR.
        points, scores = preprocessor.inference_pose(session, [], np.array(image), input_size)
        seconds = time.perf_counter() - started
        if points.shape != (1, 133, 2) or scores.shape != (1, 133):
            raise ValueError(f'Unexpected pose output: {points.shape}, {scores.shape}')
        p, s = points[0], scores[0]
        image.save(args.folder / f'{i:02d}-original.png')
        overlay = draw_overlay(image, p, s)
        overlay.save(args.folder / f'{i:02d}-overlay.png')
        low = [BODY_NAMES[j] for j in range(5, 17) if s[j] < .3]
        row = dict(label=label, **meta, size=list(image.size), elapsed=seconds,
                   keypoints=p.tolist(), scores=s.tolist(),
                   visible_limb_joints=int(sum(s[5:17] >= .3)),
                   low_confidence_limb_joints=low,
                   limb_confidence={BODY_NAMES[j]: float(s[j]) for j in range(5, 17)})
        rows.append(row)
        card = Image.new('RGB', (500, 420), 'white')
        for x, im in ((0, image), (250, overlay)):
            fitted = ImageOps.contain(im, (243, 360))
            card.paste(fitted, (x+(243-fitted.width)//2, 28+(360-fitted.height)//2))
        d = ImageDraw.Draw(card)
        d.text((4, 5), label, fill='black')
        d.text((4, 392), f'limb joints >=0.3: {row["visible_limb_joints"]}/12; low: {len(low)}', fill='black')
        cards.append(card)
        print(json.dumps(dict(label=label, elapsed=round(seconds, 3),
                              visible_limb_joints=row['visible_limb_joints'], low=low)), flush=True)
    sheet = Image.new('RGB', (1500, ((len(cards)+2)//3)*420), '#d0d0d0')
    for i, card in enumerate(cards):
        sheet.paste(card, ((i%3)*500, (i//3)*420))
    sheet.save(args.folder / 'body-overlays.png')
    result = dict(schema=1, cpu_only=True, provider=session.get_providers(),
                  detector='none; full-image box; single-actor diagnostic only',
                  model=dict(path=str(args.model.resolve()), sha256=POSE_SHA),
                  helper=dict(path=str(helper.resolve()), sha256=digest(helper)),
                  dependencies=dict(onnxruntime=ort.__version__, opencv=cv2.__version__, numpy=np.__version__),
                  source=dict(path=str(args.source.resolve()), sha256=digest(args.source), **source_meta),
                  target=dict(path=str(args.target.resolve()), sha256=digest(args.target),
                              analysis_background_rgb=[127, 127, 127]),
                  body_index_names=BODY_NAMES, body_edges=EDGES, threshold=.3,
                  samples=rows, visual_review_required=True, input_gate_passed=None,
                  note='Confidence is not accuracy. Missing joints are not filled or smoothed; no generation launched.')
    (args.folder / 'extraction.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'target', 'model', 'aux', 'folder'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--packages', type=Path)
    parser.add_argument('--seconds', type=float, nargs='+', default=[0, .4, .8, 1.4, 2, 3, 4, 6])
    run(parser.parse_args())


if __name__ == '__main__':
    main()
