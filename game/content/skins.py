"""皮肤数据。只描述外观，不影响任何规则结果。"""
from dataclasses import dataclass


@dataclass
class DiceSkin:
    id: str
    name: str
    size: float = 84            # 下面的尺寸都按这个参考边长给，绘制时按实际大小缩放
    radius: float = 16
    border_width: float = 3
    body: str = "#FFFFFF"
    border_hot: str = "#5A8CD2"     # 可以掷的时候
    border_idle: str = "#AAAFBE"    # 忙或暂停的时候
    pip: str = "#32466E"
    pip_one: str = "#E14650"        # 1 点单独上色
    pip_r: float = 7
    pip_one_r: float = 9
    pip_spread: float = 22          # 点到中心的距离
    shadow_alpha: int = 40
    roll_time: float = 0.8          # 翻滚时长（秒）
    settle_time: float = 0.35       # 定格回弹时长（秒）
    face_dir: str = None            # 有 1.png~6.png 时用贴图代替画点
