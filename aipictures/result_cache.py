"""Generated tasks are disposable; explicit exports live outside these cache roots."""
import json
import os
import stat
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .storage import DATA, write_json


def unlink_readonly(path,root,error):
    """Delete a managed Windows cache link without changing other links' attributes."""
    path=Path(path);resolved=path.resolve()
    if os.name!='nt' or not isinstance(error,PermissionError) or not resolved.is_relative_to(root):raise error
    info=path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or not getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_READONLY:raise error
    import ctypes as c
    from ctypes import wintypes as w
    api=c.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE];api.CreateFileW.restype=w.HANDLE
    api.SetFileInformationByHandle.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];api.SetFileInformationByHandle.restype=w.BOOL
    api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
    handle=api.CreateFileW(str(resolved),0x10000,7,None,3,0x00200000,None)  # DELETE, share all, OPEN_EXISTING
    if handle==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
    try:
        flags=w.DWORD(0x11)  # FILE_DISPOSITION_DELETE | FILE_DISPOSITION_IGNORE_READONLY_ATTRIBUTE
        if not api.SetFileInformationByHandle(handle,21,c.byref(flags),c.sizeof(flags)):raise c.WinError(c.get_last_error())
    finally:api.CloseHandle(handle)


class ResultCache:
    def __init__(self,data=DATA):
        self.data=Path(data).resolve()
        self.roots={'image':self.data/'jobs','walk':self.data/'animations','video':self.data/'videos','audio':self.data/'audio'}
        self.saved_index=self.data/'saved-files.json'

    def entries(self,kind):
        root=self.roots[kind]
        return sorted((p for p in root.glob('*') if p.is_dir() and
                       any((p/name).is_file() for name in ('job.json','sequence.json','video.json','audio.json'))),reverse=True)

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
                if not any((target/name).is_file() for name in ('job.json','sequence.json','video.json','audio.json')):
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
                def recover(operation,path,info):unlink_readonly(path,target,info[1])
                shutil.rmtree(target,onerror=recover)
                report['deleted'].append(str(target))
            except (OSError,ValueError) as exc:
                report['errors'].append(str(exc))
        return report


def within_any(path,folders):
    if not path: return False
    path=Path(path).resolve()
    return any(path.is_relative_to(Path(folder).resolve()) for folder in folders)
