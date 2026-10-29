"""A measured reference head crop for Animate's existing face conditioning branch."""
from PIL import Image


def reference_face(image,base):
    p=base.get('joints',{})
    points=[p[name] for name in ('nose','right_eye','left_eye','right_ear','left_ear')
        if name in p and p[name][2]>.6]
    if len(points)<2 or base.get('annotation')=='silhouette_estimate':
        return None,{'used':False,'reason':'no_reliable_face_landmarks'}
    neck=p.get('neck')
    if not neck: return None,{'used':False,'reason':'no_neck'}
    top=min(point[1] for point in points);left=min(point[0] for point in points);right=max(point[0] for point in points)
    height=neck[1]-top
    if not 20<height<image.height*.35:
        return None,{'used':False,'reason':'face_geometry_not_applicable'}
    size=max((right-left)*1.7,height*1.5,64)
    cx=(left+right)/2;cy=(top+neck[1])/2-height*.15
    box=(max(0,round(cx-size/2)),max(0,round(cy-size/2)),min(image.width,round(cx+size/2)),min(image.height,round(cy+size/2)))
    result=image.convert('RGB').crop(box).resize((512,512),Image.Resampling.LANCZOS)
    return result,{'used':True,'source_box':list(box),'output_size':[512,512],
        'expression':'fixed_original_reference','estimated_face_not_used':True}
