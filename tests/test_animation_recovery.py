import json

import pytest

from aipictures.workflow_library import digest
from tools.recover_animation_export import saved_sampling


def source(tmp_path):
    video = tmp_path / 'video'
    (video / 'decode').mkdir(parents=True)
    latent = video / 'samples_000.latent'
    latent.write_bytes(b'original saved inference')
    (tmp_path / 'sequence.json').write_text(json.dumps({
        'status': 'failed', 'frames': [], 'sampling_prompt_id': 'original-task'}))
    (video / 'sampling_result.json').write_text(json.dumps({
        'prompt_id': 'original-task', 'latents': ['old-moved-folder/samples_000.latent']}))
    (video / 'decode/source.json').write_text(json.dumps({'latent_sha256': digest(latent)}))
    return latent


def test_moved_saved_sample_is_recovered_only_with_verified_hash(tmp_path):
    latent = source(tmp_path)
    manifest, sample = saved_sampling(tmp_path)
    assert sample['prompt_id'] == manifest['sampling_prompt_id'] == 'original-task'
    assert sample['latents'] == [str(latent.resolve())]
    latent.write_bytes(b'changed')
    with pytest.raises(ValueError, match='校验不一致'):
        saved_sampling(tmp_path)


def test_exported_frames_and_mismatched_tasks_cannot_be_overwritten(tmp_path):
    source(tmp_path)
    path = tmp_path / 'sequence.json'
    manifest = json.loads(path.read_text())
    manifest['sampling_prompt_id'] = 'another-task'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='编号不匹配'):
        saved_sampling(tmp_path)
    manifest['frames'] = [{'image': 'frame_000.png'}]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='不能覆盖'):
        saved_sampling(tmp_path)
