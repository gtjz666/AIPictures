"""Task snapshots of the owned Comfy allocator. These are not peak measurements."""
import time

from .storage import write_json


GIB = 1024 ** 3
SYSTEM_HEADROOM_GIB = 3.0


class VramSnapshots:
    def __init__(self, folder, *, cpu=False):
        self.path = folder / 'vram.json'
        self.cpu = cpu
        self.records = {}

    def capture(self, client, point):
        row = dict(time=time.time(), status='cpu' if self.cpu else 'unavailable')
        if not self.cpu:
            try:
                # Both private Comfy forks report CUDA free + reusable PyTorch
                # cache as vram_free, and allocator reserve as torch_vram_total.
                device = client.request('/system_stats', timeout=2)['devices'][0]
                if device['type'] == 'cuda':
                    name = device['name']
                    _, _, allocator = name.rpartition(' : ')
                    total = int(device['vram_total'])
                    reusable = int(device['torch_vram_free'])
                    free = int(device['vram_free']) - reusable
                    if 0 <= free <= total and total:
                        row.update(status='ok', device=name, device_total_bytes=total, cuda_free_bytes=free,
                                   allocator=allocator or 'unknown', allocator_counters='unavailable')
                        # Comfy reports allocated and reserved counters for both the
                        # native and cudaMallocAsync backends. Active = reserved -
                        # reusable cache; omitting that distinction is what shows
                        # reserved-but-reclaimable memory as real usage.
                        reserve = int(device['torch_vram_total'])
                        if 0 <= reusable <= reserve <= total:
                            row.update(allocator_counters='ok', torch_active_bytes=reserve - reusable,
                                       torch_reserved_bytes=reserve, torch_reusable_cache_bytes=reusable)
            except (OSError, RuntimeError, KeyError, IndexError, TypeError, ValueError) as exc:
                row['error'] = str(exc)
        self.records[point] = row
        try:
            write_json(self.path, dict(configured_headroom_bytes=0 if self.cpu else int(SYSTEM_HEADROOM_GIB * GIB),
                                       snapshots=self.records))
        except OSError:
            # A missing diagnostic must not replace an inference result.
            pass
        return row
