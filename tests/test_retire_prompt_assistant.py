import json
import os
from unittest.mock import patch
import pytest
from aipictures.storage import write_json
from aipictures.workflow_library import digest
from tools import retire_prompt_assistant as cleanup


@pytest.fixture
def installed(tmp_path,monkeypatch):
    root=tmp_path/'assistant';models=root/'models';models.mkdir(parents=True)
    weight=models/'assistant.gguf';weight.write_bytes(b'known dedicated assistant')
    fragment=models/'assistant.gguf.intent-download.part';fragment.write_bytes(b'incomplete')
    native=tmp_path/'native-text-encoder';native.write_bytes(b'keep generation encoder')
    sha=digest(weight);size=weight.stat().st_size
    write_json(root/'installation.json',dict(files=[dict(path=str(weight),bytes=size,sha256=sha)]))
    data=tmp_path/'data';data.mkdir();write_json(data/'local-intent-settings.json',dict(validated=True,model=str(weight)))
    write_json(data/'h3-image-settings.json',dict(encoder=str(native)))
    monkeypatch.setattr(cleanup,'WEIGHTS',{weight.name:(size,sha)});monkeypatch.setattr(cleanup,'FRAGMENTS',{fragment.name})
    monkeypatch.setattr(cleanup,'idle',lambda *_:dict(process_inventory_succeeded=True))
    return root,data,weight,fragment,native,tmp_path/'receipt.json'


def test_only_verified_assistant_files_removed_native_encoder_kept(installed):
    root,data,weight,fragment,native,report=installed
    expected=weight.stat().st_size+fragment.stat().st_size
    result=cleanup.retire(root,data,report,True)
    assert result['deleted_bytes']==expected and not weight.exists() and not fragment.exists()
    assert native.read_bytes()==b'keep generation encoder' and (root/'installation.json').exists()
    assert json.loads((data/'local-intent-settings.json').read_text())['retired']
    assert report.with_name(report.stem+'-settings-backup.json').exists()


def test_dry_run_is_non_destructive(installed):
    root,data,weight,fragment,native,report=installed
    result=cleanup.retire(root,data,report)
    assert result['status']=='planned' and not result['deleted'] and weight.exists() and fragment.exists()
    assert json.loads((data/'local-intent-settings.json').read_text())['validated']


def test_wrong_checksum_refuses_before_any_deletion(installed):
    root,data,weight,fragment,native,report=installed;weight.write_bytes(b'x'*weight.stat().st_size)
    with pytest.raises(ValueError,match='checksum'):cleanup.retire(root,data,report,True)
    assert weight.exists() and fragment.exists() and not report.exists()


def test_shared_file_or_active_engine_reference_is_retained(installed):
    root,data,weight,fragment,native,report=installed
    write_json(data/'audio-settings.json',dict(model=str(weight)))
    with pytest.raises(ValueError,match='another active engine'):cleanup.retire(root,data,report,True)
    assert weight.exists() and not report.exists()


def test_hard_link_is_not_unlinked(installed,tmp_path):
    root,data,weight,fragment,native,report=installed;os.link(weight,tmp_path/'shared.gguf')
    with pytest.raises(ValueError,match='Linked/shared'):cleanup.retire(root,data,report,True)
    assert weight.exists() and not report.exists()


def test_failed_process_inventory_blocks_all_changes(installed):
    root,data,weight,fragment,native,report=installed
    with patch.object(cleanup,'idle',side_effect=ValueError('Process inventory failed')):
        with pytest.raises(ValueError,match='inventory'):cleanup.retire(root,data,report,True)
    assert weight.exists() and fragment.exists() and not report.exists()
