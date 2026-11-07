"""One authoritative detailed timeline, without changing untimed user constraints."""
import re

TITLE='以下为可编辑动作时间线，以此处时序为准：'
REFERENCE_TITLE='以下为可编辑动作时间线（自动分析供核对，动作以参考视频为准）：'
LEGACY_MANUAL_TITLE='用户修改的动作时间线（仅覆盖对应时间段，其余以参考视频为准）：'
MANUAL_TITLE='用户修改的动作时间线（成片时间 / 秒）：'
ROW=re.compile(r'^\s*\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?\s*秒[：:]')


def remove_owned_timeline(text:str)->str:
    lines=text.splitlines();out=[];i=0
    while i<len(lines):
        if lines[i].strip() in (TITLE,REFERENCE_TITLE,MANUAL_TITLE,LEGACY_MANUAL_TITLE):
            i+=1
            if i<len(lines) and lines[i].startswith('时间为参考素材秒数；'):i+=1
            while i<len(lines) and ROW.match(lines[i]):i+=1
        else:out.append(lines[i]);i+=1
    return re.sub(r'\n{3,}','\n\n','\n'.join(out)).strip()


def corrected_rows(rows:list[dict],baseline:list[dict])->list[dict]:
    """Only explicit corrections compete with the actual visual motion guide.

    Compare coverage as well as text, so clipping a previously edited table to
    a shorter output does not promote its untouched rows to manual overrides.
    Times are already validated and rounded to the editor's millisecond clock.
    """
    corrected=[]
    for row in rows:
        cursor=row['start']
        for original in baseline:
            if original['end']<=cursor+.001:continue
            if original['start']>cursor+.001 or original['description']!=row['description']:break
            cursor=original['end']
            if cursor>=row['end']-.001:break
        if cursor<row['end']-.001:corrected.append(dict(row))
    return corrected


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
