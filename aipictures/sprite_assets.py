"""Desktop bridge to the independent sprite package; original frames stay intact."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from sprite_pipeline import PipelineConfig, PipelineError, run_pipeline
from sprite_pipeline.config import write_document
from sprite_pipeline.pipeline import StageCallback


def export_pixel_assets(manifest_path: str | Path, target: str | Path, config: PipelineConfig,
                        progress: StageCallback | None = None) -> dict[str, Any]:
    """Process native matte frames if available, then atomically save a portable ZIP."""
    manifest_path, target = Path(manifest_path).resolve(), Path(target).resolve()
    manifest = json.loads(manifest_path.read_text('utf-8'))
    if manifest.get('status') != 'completed' or not manifest.get('frames'):
        raise PipelineError('动画未完成，请等待生成完成后导出像素素材。')
    originals = []
    fallback = []
    for entry in manifest['frames']:
        source = manifest_path.parent / entry.get('native_matte', entry['image'])
        if not source.is_file():
            raise PipelineError('找不到动画透明帧：' + str(source))
        if not entry.get('native_matte'):
            fallback.append(entry['image'])
        originals.append(source.resolve())
    if target == manifest_path or target in originals or target.is_relative_to(manifest_path.parent):
        raise PipelineError('请将 ZIP 保存到本次生成缓存目录以外，避免覆盖或清理时删除。')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='aipictures-sprites-') as temp:
        root = Path(temp); source_dir = root/'source'; source_dir.mkdir()
        sources = {}
        for index, source in enumerate(originals):
            name = f'frame_{index:04d}.png'
            shutil.copyfile(source, source_dir/name)
            sources[name] = {'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        output = root/'out'
        report = run_pipeline(source_dir, output, config, progress)
        state_path = output/'pipeline-state.json'
        state = json.loads(state_path.read_text('utf-8')); state['sources'] = sources
        write_document(state_path, state)
        metadata_path = output/'sprite_sheet.json'
        metadata = json.loads(metadata_path.read_text('utf-8'))
        for frame in metadata['frames']:
            frame['source'] = sources[frame['name']]
        metadata['generation']['sequence_manifest'] = str(manifest_path)
        metadata['generation']['source_seed'] = manifest.get('seed')
        if config.seed != manifest.get('seed'):
            report['warnings'].append('导出配置 seed 与动画记录不一致；后处理不会重新生成，请核对生成阶段。')
        if fallback:
            report['warnings'].append('此旧缓存没有原生透明帧，使用旧版结果；既有缩放或校色无法逆转。新生成任务会保存独立 native_matte。')
        # Keep the original location as provenance, and a portable anchor for reruns.
        portable = json.loads((output/'pipeline.json').read_text('utf-8'))
        if config.anchor:
            with Image.open(config.anchor) as anchor:
                anchor.convert('RGBA').save(output/'anchor.png')
            portable['anchor'] = 'anchor.png'
        write_document(output/'pipeline.json', portable)
        write_document(output/'report.json', report)
        write_document(metadata_path, metadata)
        if not report['pass']:
            raise PipelineError('像素素材结构验收失败，未覆盖目标文件；请在 CLI 中查看 report.json 逐项修正。')
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name+'.', suffix='.sprite-tmp', delete=False) as temporary_file:
            temporary = Path(temporary_file.name)
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(output.rglob('*')):
                    if file.is_file():
                        archive.write(file, file.relative_to(output).as_posix())
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {'path': str(target), 'report': report, 'frame_count': len(originals)}
