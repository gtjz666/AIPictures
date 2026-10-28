"""Fast vector stand-in for reviewing poses; never an AI output or exported artwork."""
import math
from PIL import Image
import numpy as np
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QPen,QPainterPath


def palette_from_reference(path,base):
    colors={'hair':'#4c536b','shirt':'#dce5ed','lower':'#596675','skin':'#efd2bc','shoe':'#424951'}
    if not path: return colors
    with Image.open(path) as image: pixels=np.asarray(image.convert('RGBA'))
    p=base['joints']
    def sample(x,y,radius=14):
        x=int(np.clip(x,0,pixels.shape[1]-1)); y=int(np.clip(y,0,pixels.shape[0]-1))
        patch=pixels[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1]
        opaque=patch[:,:,:3][patch[:,:,3]>200]
        return QColor(*map(int,np.median(opaque,axis=0))) if len(opaque) else None
    neck=p['neck']; hip=p['right_hip']; knee=p['right_knee']; ankle=p['right_ankle']; nose=p['nose']
    positions={'hair':(nose[0]-22,nose[1]-28),'shirt':((neck[0]+hip[0])/2,(neck[1]+hip[1])/2),
        'lower':((hip[0]+knee[0])/2,(hip[1]+knee[1])/2),'skin':(nose[0]-6,nose[1]+8),
        'shoe':(ankle[0]+12,ankle[1]+18)}
    for key,point in positions.items():
        value=sample(*point)
        if value: colors[key]=value
    return colors


def draw_puppet(painter,rig,palette):
    """Show mass and weight shift with reference colors, without inventing hidden textures."""
    p=rig['joints']; point=lambda name:QPointF(*p[name][:2])
    length=sum(math.dist(p[a][:2],p[b][:2]) for a,b in
        (('right_hip','right_knee'),('right_knee','right_ankle')))
    unit=max(.35,min(1.4,length/440))
    def limb(a,b,color,width):
        pen=QPen(QColor(color),width*unit,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen); painter.drawLine(point(a),point(b))
    def side(name,dark=False):
        lower=QColor(palette['lower']); skin=QColor(palette['shirt']); shoe=QColor(palette['shoe'])
        if dark: lower=lower.darker(115); skin=skin.darker(110); shoe=shoe.darker(115)
        limb(name+'_hip',name+'_knee',lower,33); limb(name+'_knee',name+'_ankle',lower,26)
        limb(name+'_heel',name+'_toe',shoe,19)
        limb(name+'_shoulder',name+'_elbow',skin,23); limb(name+'_elbow',name+'_wrist',skin,19)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(palette['skin']))
        painter.drawEllipse(point(name+'_wrist'),9*unit,13*unit)
    side('left',True)
    neck=point('neck'); hips=(point('right_hip')+point('left_hip'))/2
    vector=hips-neck; distance=math.hypot(vector.x(),vector.y()) or 1
    normal=QPointF(vector.y()/distance,-vector.x()/distance)*24*unit
    path=QPainterPath(); path.moveTo(neck+normal); path.lineTo(hips+normal*.82)
    path.lineTo(hips-normal*.82); path.lineTo(neck-normal); path.closeSubpath()
    painter.setPen(QPen(QColor('#8d98a6'),1.5)); painter.setBrush(QColor(palette['shirt'])); painter.drawPath(path)
    side('right')
    nose=point('nose'); center=nose+QPointF(-16*unit,-10*unit)
    painter.setPen(QPen(QColor('#8d98a6'),1.5)); painter.setBrush(QColor(palette['skin']))
    painter.drawEllipse(center,32*unit,45*unit)
    painter.setBrush(QColor(palette['hair'])); painter.drawPie(QRectF(center.x()-34*unit,center.y()-47*unit,68*unit,82*unit),0,180*16)
    painter.setPen(QPen(QColor('#4e5965'),4*unit,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
    painter.drawPoint(nose+QPointF(5*unit,-8*unit))
