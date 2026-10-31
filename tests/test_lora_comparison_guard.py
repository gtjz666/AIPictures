"""An expensive comparison must never silently reuse incompatible/failed output."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aipictures.lora_catalog import catalog
from aipictures.workflow_library import digest
from tools.verify_lora_walks import one_case


@pytest.mark.parametrize('change', [None, 'source', 'seed', 'lora', 'strength', 'failed', 'incomplete'])
def test_completed_comparison_reuse_requires_same_inputs(tmp_path, change):
    reference = tmp_path / 'reference.png'
    reference.write_bytes(b'immutable test source')
    entry = next(item for item in catalog() if item['id'] == 'ghibli')
    folder = tmp_path / 'results' / 'ghibli'
    folder.mkdir(parents=True)
    record = {'functional_execution_passed': True, 'original_sha256': digest(reference),
              'lora': entry['filename'], 'strength': entry['recommended_strength']}
    sequence = {'seed': 123}
    if change == 'source':
        reference.write_bytes(b'a different source image')
    if change == 'seed':
        sequence['seed'] = 456
    if change == 'lora':
        record['lora'] = 'another-model.safetensors'
    if change == 'strength':
        record['strength'] = .1
    if change == 'failed':
        record['functional_execution_passed'] = False
    if change != 'incomplete':
        (folder / 'acceptance.json').write_text(json.dumps(record), encoding='utf-8')
    (folder / 'sequence.json').write_text(json.dumps(sequence), encoding='utf-8')
    args = SimpleNamespace(one='ghibli', out=folder.parent, reference=reference, seed=123)
    with patch('tools.verify_lora_walks.ComfyClient') as client:
        if change is None:
            one_case(args)
        else:
            with pytest.raises(ValueError):
                one_case(args)
        client.assert_not_called()
