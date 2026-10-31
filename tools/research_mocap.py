"""Offline ASF/AMC forward kinematics for studying public CMU human motion.

Column-vector convention: G_child = G_parent C M C^-1; endpoint = parent + G_child d L.
Source format: https://research.cs.wisc.edu/graphics/Courses/cs-838-1999/Jeff/ASF-AMC.html
This module does not import or change the shared Comfy installation.
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def rotation(channels,angles):
    result=np.eye(3)
    for channel,value in zip(channels,angles):
        a=math.radians(value);c,s=math.cos(a),math.sin(a)
        matrix={'rx':((1,0,0),(0,c,-s),(0,s,c)),
                'ry':((c,0,s),(0,1,0),(-s,0,c)),
                'rz':((c,-s,0),(s,c,0),(0,0,1))}[channel]
        result=np.asarray(matrix)@result
    return result


def read_asf(path):
    section='';bone=None;bones={};children={}
    for raw in Path(path).read_text().splitlines():
        tokens=raw.strip().split()
        if not tokens or tokens[0].startswith('#'):continue
        if tokens[0].startswith(':'):section=tokens[0];continue
        if section==':bonedata':
            key=tokens[0]
            if key=='begin':bone={'dof':[]}
            elif key=='end':
                bone['C']=rotation(['r'+a.lower() for a in bone['order']],bone['axis'])
                bones[bone['name']]=bone
            elif key in ('id','name'):bone[key]=tokens[1]
            elif key=='direction':bone[key]=np.asarray(list(map(float,tokens[1:4])))
            elif key=='length':bone[key]=float(tokens[1])
            elif key=='axis':bone['axis']=list(map(float,tokens[1:4]));bone['order']=tokens[4]
            elif key=='dof':bone[key]=tokens[1:]
        elif section==':hierarchy' and tokens[0] not in ('begin','end'):
            children[tokens[0]]=tokens[1:]
    return bones,children


def read_amc(path):
    frames=[];frame=None
    for raw in Path(path).read_text().splitlines():
        parts=raw.split()
        if not parts or parts[0].startswith(('#',':')):continue
        if len(parts)==1 and parts[0].isdigit():
            if frame is not None:frames.append(frame)
            frame={}
        else:frame[parts[0]]=list(map(float,parts[1:]))
    if frame is not None:frames.append(frame)
    if not frames:raise ValueError('No AMC motion frames.')
    return frames


def world_positions(asf,amc):
    bones,children=read_asf(asf);frames=read_amc(amc);tracks={n:[] for n in ['root']+list(bones)}
    for frame in frames:
        root=frame['root'];positions={'root':np.asarray(root[:3])};matrices={'root':rotation(('rx','ry','rz'),root[3:])}
        def visit(parent):
            for name in children.get(parent,[]):
                b=bones[name];C=b['C'];M=rotation(b['dof'],frame.get(name,[]))
                if b['dof'] and len(frame.get(name,[]))!=len(b['dof']):raise ValueError('Missing AMC channels: '+name)
                matrices[name]=matrices[parent]@C@M@C.T
                positions[name]=positions[parent]+matrices[name]@(b['direction']*b['length'])
                visit(name)
        visit('root')
        for name,point in positions.items():tracks[name].append(point)
    return {name:np.asarray(points) for name,points in tracks.items()},bones,children


def contact_sheet(tracks,children,indices,axis,target):
    points=np.concatenate([tracks[n][indices] for n in tracks]);xy=np.stack((points@axis,-points[:,1]),axis=1)
    lo=xy.min(0);hi=xy.max(0);scale=min(180/(hi[0]-lo[0]),250/(hi[1]-lo[1]))
    sheet=Image.new('RGB',(240*8,310*math.ceil(len(indices)/8)),(244,245,247));draw=ImageDraw.Draw(sheet)
    for cell,index in enumerate(indices):
        center=tracks['root'][index]@axis
        def point(n):
            p=tracks[n][index]
            return (cell%8*240+120+(p@axis-center)*scale,cell//8*310+20+(-p[1]-lo[1])*scale)
        for parent,names in children.items():
            for name in names:
                draw.line((*point(parent),*point(name)),width=3,fill='#265dd9' if name.startswith('r') else '#dc780d')
        draw.text((cell%8*240+10,cell//8*310+290),str(index),fill='black')
    sheet.save(target)


def main():
    p=argparse.ArgumentParser();p.add_argument('--subject',default='16');p.add_argument('--motion',default='16_05')
    p.add_argument('--root',type=Path,default=Path('data/motion-research/cmu'));args=p.parse_args()
    tracks,bones,children=world_positions(args.root/(args.subject+'.asf'),args.root/(args.motion+'.amc'))
    np.savez(args.root/(args.motion+'-world.npz'),**tracks)
    root=tracks['root'];axis=root[-1]-root[0];axis[1]=0;axis/=max(1e-9,np.linalg.norm(axis))
    indices=np.linspace(0,len(root)-1,32,dtype=int).tolist()
    contact_sheet(tracks,children,indices,axis,args.root/(args.motion+'-sheet.png'))
    report={'frames':len(root),'root_min':root.min(0).tolist(),'root_max':root.max(0).tolist(),'axis':axis.tolist(),
            'ankles_y':{s:[float(tracks[s+'tibia'][:,1].min()),float(tracks[s+'tibia'][:,1].max())] for s in ('r','l')}}
    (args.root/(args.motion+'-report.json')).write_text(json.dumps(report,indent=2))
    print(report)


if __name__=='__main__':main()
