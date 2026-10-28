"""Explicit SDXL vocabulary. Wan receives the user's original Chinese instructions."""
import re

NEGATIVE = {
    '人物身份变化':'different character', '脸部变化':'changed face', '发型变化':'changed hairstyle',
    '发色变化':'changed hair color', '服装变化':'changed outfit', '颜色缺失':'missing colors',
    '局部褪色':'faded colors', '黑色衣物消失':'missing black clothing', '身体比例变化':'inconsistent proportions',
    '多个人物':'multiple characters', '重复人物':'duplicate character', '多余手臂':'extra arms',
    '多余腿部':'extra legs', '多余手指':'extra fingers', '缺失肢体':'missing limbs',
    '肢体融合':'fused limbs', '关节扭曲':'twisted joints', '身体断裂':'disconnected body parts',
    '手脚畸形':'deformed hands and feet', '头部裁切':'cropped head', '脚部裁切':'cropped feet',
    '人物出框':'subject out of frame', '视角变化':'changing viewpoint', '镜头移动':'camera movement',
    '人物大小变化':'changing subject size', '画面抖动':'flickering', '动作突变':'abrupt motion',
    '脚底滑动':'foot sliding', '脚部悬空':'floating feet', '棋盘格背景':'checkerboard background',
    '复杂背景':'busy background', '模糊':'blurry', '重影':'ghosting', '残影':'motion trails',
    '文字':'text', '水印':'watermark', '标志':'logo', '低质量':'low quality',
    '多余肢体':'extra limbs', '肢体畸形':'deformed limbs', '重复手臂':'duplicate arms',
    '重复手部':'duplicate hands', '断手':'disconnected hands', '颜色变化':'changed colors',
}

APPEARANCE = {
    '参考图中的同一人物':'same character as the reference', '参考图中的同一角色':'same character as the reference',
    '同一人物':'same character', '单个人物':'one single character', '面朝右方':'facing right',
    '面朝左方':'facing left', '右侧视图':'strict right-facing side profile', '左侧视图':'strict left-facing side profile',
    '头部与双脚完整入镜':'entire head and both feet in frame', '头部、手部与双脚完整入镜':'entire head, hands and feet in frame',
    '人物居中':'centered character', '轮廓清晰':'clean outlines', '背景简洁':'plain background',
    '固定镜头':'fixed camera', '保持人物身份':'preserve character identity',
    '身体比例一致':'consistent body proportions', '配色一致':'consistent colors', '服装一致':'same outfit',
    '双臂自然下垂':'arms relaxed at sides', '双脚平稳接触地面':'feet planted on the ground',
    '自然站立':'standing naturally', '手肘自然伸展':'elbow extended naturally',
    '黄色':'yellow', '白色':'white', '黑色':'black', '粉色':'pink', '蓝色':'blue', '紫色':'purple',
    '红色':'red', '绿色':'green', '橙色':'orange', '棕色':'brown',
    '小恐龙':'small dinosaur', '恐龙':'dinosaur', '小鸟':'bird', '企鹅':'penguin',
    '小鸭':'duck', '小鸡':'chick', '小猫':'cat', '小狗':'dog', '兔子':'rabbit', '吉祥物':'mascot',
    '卡通':'cartoon', '可爱':'cute', '圆润':'rounded', '大眼睛':'large eyes', '肚皮':'belly',
    '长发':'long hair', '连衣裙':'dress', '外套':'coat', '靴子':'boots', '短裤':'shorts',
}


def translate_vocabulary(text, vocabulary):
    result = text
    for phrase, english in sorted(vocabulary.items(), key=lambda item: -len(item[0])):
        result = result.replace(phrase, ' ' + english + ' ')
    unknown = ''.join(re.findall(r'[\u3400-\u9fff]+', result))
    # Unmapped words remain visible in the actual conditioning; never claim full translation.
    result = re.sub(r'[，。；、\n]+', ', ', result)
    result = re.sub(r' +', ' ', result).strip(' ,')
    return result, unknown


def negative_text(text):
    if not re.search(r'[\u3400-\u9fff]', text): return text, ''
    return translate_vocabulary(text, NEGATIVE)
