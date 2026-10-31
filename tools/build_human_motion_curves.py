"""Extract compact, retargetable sagittal motion curves from two public CMU captures.

The data used in this project was obtained from mocap.cs.cmu.edu.
Raw ASF/AMC files stay in the ignored research directory; no model is trained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def build(root,action):
    name='16_05' if action=='jump' else '14_01'
    tracks=dict(np.load(root/(name+'-world.npz')))
    if action=='jump':
        axis=tracks['root'][260]-tracks['root'][40];axis[1]=0
        timeline=((0,40),(.08,70),(.18,110),(.26,135),(.41,160),(.52,175),(.70,193),(.80,204),(.90,230),(1,260))
    else:
        axis=tracks['rradius'][169]-tracks['rclavicle'][169];axis[1]=0
        timeline=((0,120),(.12,130),(.26,151),(.37,169),(.46,169),(.68,206),(.84,230),(1,230))
    axis/=np.linalg.norm(axis)
    length=sum(np.linalg.norm(tracks[b][0]-tracks[a][0]) for a,b in (('rhipjoint','rfemur'),('rfemur','rtibia')))
    pelvis=(tracks['rhipjoint']+tracks['lhipjoint'])/2
    ankles=(tracks['rtibia']+tracks['ltibia'])/2
    def angle(a,b,up=False):
        d=tracks[b]-tracks[a]
        return np.unwrap(np.arctan2(d@axis,d[:,1] if up else -d[:,1]))
    values={'lean':angle('root','upperneck',True),
        'down':((pelvis[40 if action=='jump' else 120,1]-ankles[40 if action=='jump' else 120,1])-(pelvis[:,1]-ankles[:,1]))/length,
        'balance':((pelvis-ankles)@axis)/length,
        'root_x':((tracks['root']-tracks['root'][120 if action=='attack' else 40])@axis)/length,
        'twist':((tracks['rclavicle']-tracks['lclavicle'])@axis)/length}
    for side in ('r','l'):
        for label,a,b in (('upper_arm','clavicle','humerus'),('lower_arm','humerus','radius'),
                          ('upper_leg','hipjoint','femur'),('lower_leg','femur','tibia')):
            values[side+'_'+label]=angle(side+a,side+b)
        values[side+'_ankle_x']=((tracks[side+'tibia']-pelvis)@axis)/length
        foot=tracks[side+'toes']-tracks[side+'tibia']
        pitch=np.unwrap(np.arctan2(-foot[:,1],foot@axis))
        rest=np.median(pitch[30:60] if action=='jump' else pitch[110:135])
        values[side+'_roll']=pitch-rest
    phases=np.linspace(0,1,65);source=np.interp(phases,*np.array(timeline).T)
    frames=[]
    for phase,at in zip(phases,source):
        row={'phase':round(float(phase),6),'source_frame':round(float(at),4)}
        for key,series in values.items():row[key]=round(float(np.interp(at,np.arange(len(series)),series)),7)
        frames.append(row)
    return {'schema_version':1,'action':action,'source':{'database':'CMU Graphics Lab Motion Capture Database',
        'credit':'The data used in this project was obtained from mocap.cs.cmu.edu.',
        'url':'http://mocap.cs.cmu.edu/subjects/'+name[:2]+'/'+name+'.amc','sample':name,'fps':120,
        'sha256':hashlib.sha256((root/(name+'.amc')).read_bytes()).hexdigest(),
        'format_note':'Projected global joint directions; extracted relative curves, not source bone lengths.',
        'projection_axis':axis.tolist(),'source_frame_index_base':0,'frame_mapping':timeline},'units':'radians and source leg lengths',
        'frames':frames}


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('data/motion-research/cmu'))
    p.add_argument('--out',type=Path,default=Path('aipictures/resources/human_motion'));args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    for action in ('jump','attack'):
        data=build(args.source,action)
        (args.out/(action+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(action,data['source']['sample'],'65 curve samples')


if __name__=='__main__':main()
