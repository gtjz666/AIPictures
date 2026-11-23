import json

from aipictures.comfy_vram import GIB, SYSTEM_HEADROOM_GIB, VramSnapshots


class Client:
    def __init__(self, device=None, error=None): self.device, self.error, self.calls = device, error, []
    def request(self, path, timeout=None):
        self.calls.append((path, timeout))
        if self.error: raise self.error
        return {'devices': [self.device]}


def device(*, total=12*GIB, reserve=2*GIB, reusable=512*1024**2, allocator='cudaMallocAsync'):
    # Comfy's vram_free is CUDA free plus reclaimable torch cache.
    free_cuda = total - reserve
    return {'type': 'cuda', 'name': 'cuda:0 NVIDIA Test GPU : '+allocator,
            'vram_total': total, 'vram_free': free_cuda + reusable,
            'torch_vram_total': reserve, 'torch_vram_free': reusable}


def test_active_and_reclaimable_cache_are_not_mixed(tmp_path):
    snapshots = VramSnapshots(tmp_path)
    row = snapshots.capture(Client(device()), 'after_graph')
    assert row['status'] == 'ok' and row['allocator'] == 'cudaMallocAsync'
    assert row['device_total_bytes'] == 12*GIB
    assert row['cuda_free_bytes'] == 10*GIB
    assert row['torch_active_bytes'] == 2*GIB - 512*1024**2
    assert row['torch_reserved_bytes'] == 2*GIB
    assert row['torch_reusable_cache_bytes'] == 512*1024**2
    assert row['allocator_counters'] == 'ok'
    saved = json.loads((tmp_path/'vram.json').read_text('utf-8'))
    assert saved['configured_headroom_bytes'] == int(SYSTEM_HEADROOM_GIB*GIB)
    assert saved['snapshots']['after_graph']['torch_active_bytes'] == row['torch_active_bytes']


def test_native_allocator_is_recorded_the_same_way(tmp_path):
    row = VramSnapshots(tmp_path).capture(Client(device(allocator='native')), 'before_graph')
    assert row['allocator'] == 'native' and row['torch_active_bytes'] == 2*GIB - 512*1024**2


def test_cpu_session_does_not_claim_gpu_metrics(tmp_path):
    client = Client(device())
    row = VramSnapshots(tmp_path, cpu=True).capture(client, 'after_graph')
    assert row['status'] == 'cpu' and 'torch_active_bytes' not in row and not client.calls


def test_missing_or_broken_stats_do_not_replace_a_result(tmp_path):
    row = VramSnapshots(tmp_path).capture(Client(error=OSError('backend gone')), 'before_graph')
    assert row['status'] == 'unavailable' and 'backend gone' in row['error']
    assert json.loads((tmp_path/'vram.json').read_text('utf-8'))['snapshots']['before_graph']['status'] == 'unavailable'


def test_two_snapshots_keep_both_points(tmp_path):
    snapshots = VramSnapshots(tmp_path)
    snapshots.capture(Client(device()), 'before_graph')
    snapshots.capture(Client(device(reserve=4*GIB, reusable=64*1024**2)), 'after_graph')
    saved = json.loads((tmp_path/'vram.json').read_text('utf-8'))['snapshots']
    assert set(saved) == {'before_graph', 'after_graph'}
    assert saved['before_graph']['torch_reserved_bytes'] == 2*GIB
    assert saved['after_graph']['torch_reserved_bytes'] == 4*GIB
