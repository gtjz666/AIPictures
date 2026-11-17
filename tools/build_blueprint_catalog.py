"""Render current native registry data, rather than a second handwritten catalog."""
import argparse
import json
from pathlib import Path


def cell(value):
    if isinstance(value,dict):value='；'.join(str(k)+'：'+str(v) for k,v in value.items())
    elif isinstance(value,bool):value='开' if value else '关'
    return str(value).replace('|','／').replace('\n',' ')


def build(data):
    modules=data['game_modules']
    rows=['# AlI Blueprint 0.5 模块与参数手册','','2026年11月18日 · Godot 4.6 · API 6 · 2D版。',
          '',f"原生注册表只读提取：{len(modules)}类游戏模块、{len(data['character_types'])}类角色模块、{sum(len(m['fields']) for m in modules)}项游戏字段。19项角色动作是动作模块内的选项。",'',
          '先读[使用步骤](BLUEPRINT_05_PLAN.md)与[技术文档](GODOT_BLUEPRINT_TECHNICAL.md)。白色执行、橙色事件；绿色布尔、蓝色数字、粉色文字，其余类型使用不同数据色。事件口仍沿用执行端口编号，不破坏旧图。',
          '', '## 游戏模块索引','','| 模块 | 分类 | 用途 |','| --- | --- | --- |']
    for m in modules:rows.append(f"| {m['name']}（{m['id']}） | {m['category']} | {m['description']} |")
    rows+=['','## 全部游戏模块字段','','端口从0编号。表中数据类型对应默认参数；改变value_type等参数后，端口随之变化。未连数据线时使用默认值。JSON默认null表示所选类型的默认值。资源需项目内res://路径，节点需相对游戏根节点路径。']
    for m in modules:
        rows+=['','### '+m['name']+'（'+m['id']+'）','',m['description'],'',
               '输入：'+('；'.join(f"{i} {v}（{m['input_types'][i]}）" for i,v in enumerate(m['inputs'])) or '无。'),'',
               '输出：'+('；'.join(f"{i} {v}（{m['output_types'][i]}）" for i,v in enumerate(m['outputs'])) or '无。'),'']
        if m['core']:rows+=['此模块保留一个。通用2D只要求session／input／hud／mixer／screen；跑酷另需runner／world／spawner配套。','']
        if not m['fields']:rows+=['无参数，按执行连线编排。'];continue
        rows+=['| 字段／参数 | 类型 | 默认 | 范围／选项 |','| --- | --- | --- | --- |']
        for f in m['fields']:
            detail=cell(f[4])+'～'+cell(f[5]) if len(f)>5 else cell(f[4]) if len(f)>4 else ''
            rows.append('| '+cell(f[0])+'／'+cell(f[1])+' | '+cell(f[2])+' | '+cell(f[3])+' | '+detail+' |')
    roles=[('key','按键','0按住、1按下','code或input_action；可选InputMap默认动作或自定义名称'),('event','角色事件','0发生','ready／hurt／death／land／animation_finished'),('action','封装动作','0执行→0动画','19项动作；同类动作只声明一次'),('animation','SpriteFrames','0执行→0动画时刻','clip动画名，实际素材必须存在'),('sound','音效','0播放','path／trigger=start,frame,repeat／frame／interval／volume'),('branch','条件','0执行、1布尔→0真、1假','condition／invert；已落地、空中、移动、奔跑、始终'),('sequence','顺序','0执行→0、1','立即发出两个执行，不等待'),('delay','延迟','0执行→0完成','seconds：0.01–60秒'),('boolean','布尔变量','0布尔数据','name／value'),('custom','自定义脚本','0执行→0、1','RefCounted.execute(context)，同步接口'),('receive_event','接收参数事件','0事件、1类型化参数','name／scope=game,project,role／value_type'),('send_event','发送参数事件','0执行、1类型化数据→0完成','name／scope／value_type／json'),('typed_value','类型化常量','0类型化数据','value_type／json')]
    rows+=['','## 角色模块（13类）','','角色工作台负责单个角色，异步服务、地图、菜单、相机在游戏工作台编排。','', '| 类型 | 名称 | 端口 | 参数 |','| --- | --- | --- | --- |']
    for row in roles:rows.append('| '+' | '.join(row)+' |')
    rows+=['','复杂类型支持bool／number／text／Vector2／Vector3数据／Color／Node／Resource／Array／Dictionary。JSON向量写数组、颜色写HTML、资源写res://路径、节点写角色下的相对路径。',
           '', '角色默认运动参数：速度180、奔跑倍率1.8、重力980、起跳速度-380。角色动作包括移动、待机、行走、奔跑、跳跃、攻击、受击、死亡、冲刺、翻滚、防御、施法、交互、攀爬、下落、落地。特殊技能仍需玩法模块或自定义代码；动作槽不自动提供命中判定、背包或AI。',
           '', '## 模板与边界','','新建游戏框架提供空白2D、基础2D、平台跳跃、跑酷；生成六类可编辑原生场景。菜单、保存与设置接线和动画均有效。只创建新目录，只有用户勾选才修改启动场景。',
           '', '旧自含游戏API低于6时只读绑定，创建新名称场景升级。原Sequence保持立即双输出，等待请用task_group。旧v1子图仍可加载，参数子图保存为version2。',
           '', '3D／2.5D暂缓；不包含完整行为树、多人联网、整套装备／任务／对话编辑器或自动关卡美术识别。使用Godot原生TileSet／TileMapLayer编辑器设计地图，蓝图负责动态逻辑。蓝图执行不启动AI推理。','']
    return '\n'.join(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--schema',type=Path,required=True);parser.add_argument('--output',type=Path,default=Path('docs/GODOT_BLUEPRINT_CATALOG.md'));args=parser.parse_args()
    args.output.write_text(build(json.loads(args.schema.read_text('utf-8'))),'utf-8');print(args.output.resolve())
