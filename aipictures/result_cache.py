"""Generated tasks are disposable; explicit exports live outside these cache roots."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .storage import DATA, write_json


class ResultCache:
    def __init__(self,data=DATA):
        self.data=Path(data).resolve()
        self.roots={'image':self.data/'jobs','walk':self.data/'animations'}
        self.saved_index=self.data/'saved-files.json'

    def entries(self,kind):
        root=self.roots[kind]
        return sorted((p for p in root.glob('*') if p.is_dir() and
                       ((p/'job.json').is_file() or (p/'sequence.json').is_file())),reverse=True)

    def validate_export(self,path):
        path=Path(path).resolve()
        for root in self.roots.values():
            if path.is_relative_to(root.resolve()):
                raise ValueError('请选择生成缓存目录以外的位置保存，避免日后清理缓存时删除。')
        return path

    def saved_files(self):
        if not self.saved_index.exists(): return []
        return json.loads(self.saved_index.read_text('utf-8'))['files']

    def record_save(self,path,kind,source=None):
        path=self.validate_export(path)
        entries=[row for row in self.saved_files() if Path(row['path']).resolve()!=path]
        entries.append({'path':str(path),'kind':kind,'source':str(source) if source else None,
                        'saved_at':datetime.now(timezone.utc).isoformat()})
        write_json(self.saved_index,{'schema_version':1,'files':entries})

    def _checked_folder(self,path):
        # Recheck the resolved absolute target immediately before recursive deletion.
        path=Path(path)
        if path.is_symlink() or path.is_junction(): raise ValueError('不会清理链接或目录联接：'+str(path))
        target=path.resolve()
        for root in self.roots.values():
            if root.is_symlink() or root.is_junction(): continue
            if target.parent==root.resolve() and target!=root.resolve():
                if not (target/'job.json').is_file() and not (target/'sequence.json').is_file():
                    raise ValueError('该目录不是可识别的生成缓存：'+str(target))
                return target
        raise ValueError('清理范围仅限本软件的生成任务缓存：'+str(path))

    def clear(self,folders,protected=()):
        protected={Path(path).resolve() for path in protected}
        report={'deleted':[],'skipped':[],'errors':[]}
        for path in dict.fromkeys(str(p) for p in folders):
            try:
                target=self._checked_folder(path)
                if target in protected:
                    report['skipped'].append(str(target)); continue
                shutil.rmtree(target)
                report['deleted'].append(str(target))
            except (OSError,ValueError) as exc:
                report['errors'].append(str(exc))
        return report


def within_any(path,folders):
    if not path: return False
    path=Path(path).resolve()
    return any(path.is_relative_to(Path(folder).resolve()) for folder in folders)
