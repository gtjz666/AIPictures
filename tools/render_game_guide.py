"""Dependency-free offline HTML reader for the checked-in game guide."""
import argparse
import base64
import html
import re
from pathlib import Path


def render_guide(source,*,title='AlI 小恐龙式游戏制作指南',navigation_title='使用步骤'):
    source=Path(source).resolve();lines=source.read_text('utf-8').splitlines();blocks=[];toc=[]
    def inline(text):
        text=html.escape(text)
        text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
        guides = {'GODOT_BLUEPRINT_CATALOG.md':'蓝图模块手册.html',
                  'GODOT_BLUEPRINT_TECHNICAL.md':'蓝图技术文档.html',
                  'BLUEPRINT_05_PLAN.md':'蓝图0.5阶段文档.html',
                  'GODOT_SCENE_BLUEPRINT_GUIDE.md':'场景蓝图教程.html',
                  'DINO_AI_ASSETS_TUTORIAL.md':'小恐龙实际生图测试步骤.html',
                  'GODOT_ASSETS.md':'素材导出指南.html'}
        for filename,label in guides.items():
            text=re.sub(r'\[([^]\n]+)\]\('+re.escape(filename)+r'\)',lambda match:'<a href="'+label+'">'+match[1]+'</a>',text)
        text=re.sub(r'\[([^]\n]+)\]\((https?://[^ )]+)\)',r'<a href="\2">\1</a>',text)
        return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text)
    index=0
    while index<len(lines):
        line=lines[index];index+=1
        if not line.strip():continue
        if line.startswith('```'):
            code=[]
            while index<len(lines) and not lines[index].startswith('```'):code.append(lines[index]);index+=1
            index+=1;blocks.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>');continue
        if line.startswith('#'):
            level=len(line)-len(line.lstrip('#'));heading=line[level:].strip();anchor='section-'+str(index)
            if level>1:toc.append((anchor,heading))
            blocks.append(f'<h{level} id="{anchor}">{inline(heading)}</h{level}>');continue
        image=re.fullmatch(r'!\[([^]]*)\]\(([^)]+)\)',line)
        if image:
            path=(source.parent/image[2]).resolve()
            if not path.is_relative_to(source.parent):raise ValueError('Guide images must stay inside the docs folder.')
            data=base64.b64encode(path.read_bytes()).decode('ascii')
            blocks.append(f'<figure><img alt="{html.escape(image[1])}" src="data:image/png;base64,{data}"><figcaption>{inline(image[1])}</figcaption></figure>');continue
        if line.startswith('|'):
            rows=[line]
            while index<len(lines) and lines[index].startswith('|'):rows.append(lines[index]);index+=1
            cells=[]
            for row_index,row in enumerate(rows):
                if row_index==1 and set(row.replace('|','').replace(' ','').replace(':',''))=={'-'}:continue
                tag='th' if row_index==0 else 'td';cells.append('<tr>'+''.join(f'<{tag}>{inline(v.strip())}</{tag}>' for v in row.strip('|').split('|'))+'</tr>')
            blocks.append('<table>'+''.join(cells)+'</table>');continue
        ordered=re.match(r'^\d+\. (.*)',line);bullet=line.startswith('- ')
        if ordered or bullet:
            tag='ol' if ordered else 'ul';items=[ordered[1] if ordered else line[2:]]
            while index<len(lines):
                match=re.match(r'^\d+\. (.*)',lines[index]) if ordered else re.match(r'^- (.*)',lines[index])
                if not match:break
                items.append(match[1]);index+=1
            blocks.append(f'<{tag}>'+''.join('<li>'+inline(item)+'</li>' for item in items)+f'</{tag}>');continue
        blocks.append('<p>'+inline(line)+'</p>')
    navigation='<nav><strong>'+html.escape(navigation_title)+'</strong><ol>'+''.join(f'<li><a href="#{a}">{html.escape(t)}</a></li>' for a,t in toc)+'</ol></nav>'
    style='''body{margin:0;background:#eff4f3;color:#183c43;font:16px/1.8 "Microsoft YaHei",system-ui,sans-serif}main{max-width:1000px;margin:28px auto;padding:42px;background:white;border-radius:12px}h1{font-size:30px}h2{margin-top:42px;border-bottom:2px solid #d6e9e3;padding-bottom:8px}h3{margin-top:28px}nav{padding:20px 28px;background:#edf6f2;border-radius:8px}li{margin:9px 0}a{color:#236c69}code{background:#edf2f2;border-radius:3px;padding:2px 5px;overflow-wrap:anywhere}pre{overflow:auto;background:#edf2f2;padding:18px}table{border-collapse:collapse;width:100%;font-size:15px}th,td{border:1px solid #cbdad7;padding:10px;text-align:left}th{background:#edf6f2}img{width:100%;height:auto;border:1px solid #dbe6e2}figure{margin:24px 0}figcaption{font-size:14px;color:#5c7776} @media print{body{background:white;font-size:11px}main{margin:0;padding:0}nav{display:none}h2{break-after:avoid}table,figure,pre{break-inside:avoid}}'''
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+style+'</style><main>'+blocks[0]+navigation+''.join(blocks[1:])+'</main></html>'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=Path('docs/GODOT_RUNNER_GUIDE.md'));parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(render_guide(args.source),'utf-8');print(args.output.resolve())
