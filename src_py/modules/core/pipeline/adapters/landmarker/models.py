from dataclasses import dataclass

@dataclass
class ResultFaceData:
    eye_left:float #左眨眼
    eye_right:float #右眨眼
    mouth_y:float #嘴巴打开度
    pitch:float #俯仰角，范围[-90, 90]
    yaw:float #偏航角，范围[-180, 180]
    roll:float #横滚角，范围[-180, 180]