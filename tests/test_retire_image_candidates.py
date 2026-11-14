import hashlib,json,os
import pytest
from tools import retire_unused_image_models as retire

@pytest.fixture
def setup(tmp_path,monkeypatch):
    root=tmp_path/'models';root.mkdir();data=tmp_path/'data';data.mkdir()
    (data/'reference-edit-settings.json').write_text('{"validated":false}','utf-8')
    target=root/'candidate.bin';target.write_bytes(b'candidate')
    sha=hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.setattr(retire,'specifications',lambda:[(retire.Path('candidate.bin'),9,sha,'not adopted')])
    class Client:
        def __init__(self,url):self.url=url
        def request(self,*args,**kwargs):return dict(queue_running=[],queue_pending=[])
    monkeypatch.setattr(retire,'ComfyClient',Client)
    return root,data,tmp_path/'receipt.json',target

def test_only_verified_allowlisted_file_is_removed(setup):
    root,data,report,target=setup;other=root/'keep.bin';other.write_bytes(b'active')
    result=retire.retire(root,data,report,['http://localhost:1'])
    assert not target.exists() and other.read_bytes()==b'active'
    assert result['deleted_bytes']==9 and len(result['deleted'])==1
    assert 'pending' not in json.loads(report.read_text('utf-8'))

def test_revalidated_engine_cannot_be_retired(setup):
    root,data,report,target=setup
    (data/'reference-edit-settings.json').write_text('{"validated":true}','utf-8')
    with pytest.raises(ValueError,match='unvalidated'):retire.retire(root,data,report,['http://localhost:1'])
    assert target.exists() and not report.exists()

def test_modified_file_and_hardlinked_file_are_preserved(setup):
    root,data,report,target=setup;target.write_bytes(b'different')
    result=retire.retire(root,data,report,['http://localhost:1'])
    assert target.exists() and result['deleted_bytes']==0
    target.write_bytes(b'candidate');link=root/'shared.bin';os.link(target,link)
    result=retire.retire(root,data,report.with_name('second.json'),['http://localhost:1'])
    assert target.exists() and link.exists() and result['deleted_bytes']==0

def test_new_queue_work_blocks_delete_after_hashing(setup,monkeypatch):
    root,data,report,target=setup
    class Client:
        def __init__(self,url):self.calls=0
        def request(self,*args,**kwargs):
            self.calls+=1
            return dict(queue_running=[] if self.calls==1 else ['new task'],queue_pending=[])
    monkeypatch.setattr(retire,'ComfyClient',Client)
    with pytest.raises(ValueError,match='busy'):retire.retire(root,data,report,['http://localhost:1'])
    assert target.exists()

def test_outside_root_is_preserved_even_with_matching_hash(setup,monkeypatch):
    root,data,report,target=setup;outside=root.parent/'outside.bin';outside.write_bytes(b'candidate')
    monkeypatch.setattr(retire,'specifications',lambda:[(retire.Path('../outside.bin'),9,hashlib.sha256(b'candidate').hexdigest(),'not adopted')])
    result=retire.retire(root,data,report,['http://localhost:1'])
    assert outside.exists() and target.exists() and result['deleted_bytes']==0

def test_unknown_offline_consumers_block_delete(setup,monkeypatch):
    root,data,report,target=setup
    class Client:
        def __init__(self,url):self.url=url
        def request(self,*args,**kwargs):raise retire.EngineUnavailable(self.url)
    monkeypatch.setattr(retire,'ComfyClient',Client)
    def unknown():raise ValueError('inventory unknown')
    monkeypatch.setattr(retire,'no_local_engines',unknown)
    with pytest.raises(ValueError,match='unknown'):retire.retire(root,data,report,['http://localhost:1'],True)
    assert target.exists() and not report.exists()
