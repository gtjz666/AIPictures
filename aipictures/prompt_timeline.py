"""One authoritative detailed timeline, without changing untimed user constraints."""
import re

TITLE='以下为可编辑动作时间线，以此处时序为准：'
ROW=re.compile(r'^\s*\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?\s*秒[：:]')


def remove_owned_timeline(text:str)->str:
    lines=text.splitlines();out=[];i=0
    while i<len(lines):
        if lines[i].strip()==TITLE:
            i+=1
            if i<len(lines) and lines[i].startswith('时间为参考素材秒数；'):i+=1
            while i<len(lines) and ROW.match(lines[i]):i+=1
        else:out.append(lines[i]);i+=1
    return re.sub(r'\n{3,}','\n\n','\n'.join(out)).strip()


def remove_generated_summary(text:str,rows:list[dict])->str:
    """Discard a recognizable generated timing summary; retain ordinary prose."""
    if not rows:return text
    text=remove_owned_timeline(text);out=[]
    cue=re.compile(r'从\s*\d+(?:\.\d+)?\s*秒开始\s*[：:]')
    timed_line=re.compile(r'^\s*\d+(?:\.\d+)?\s*(?:[–—-]\s*\d+(?:\.\d+)?)?\s*(?:秒|s)\s*[：:]',re.I)
    for line in text.splitlines():
        found=cue.search(line)
        if found:line=line[:found.start()].rstrip()
        elif timed_line.match(line):continue
        if line.strip():out.append(line)
    return '\n'.join(out).strip()
