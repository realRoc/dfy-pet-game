"""皮肤数据。只描述外观，不影响任何规则结果。"""
from dataclasses import dataclass


@dataclass
class DiceSkin:
    id: str
    name: str
    style: str = "flat"         # flat：平面圆角方块；cube：带体积的立方体
    size: float = 84            # 下面的尺寸都按这个参考边长给，绘制时按实际大小缩放
    radius: float = 16
    border_width: float = 3
    body: str = "#FFFFFF"
    side: str = "#E6DCC8"           # cube：棱边和暗面的底色
    border_hot: str = "#5A8CD2"     # 可以掷的时候
    border_idle: str = "#AAAFBE"    # 忙或暂停的时候
    pip: str = "#32466E"
    pip_one: str = "#E14650"        # 1 点单独上色
    pip_r: float = 7
    pip_one_r: float = 9
    pip_spread: float = 22          # 点到中心的距离
    shadow_alpha: int = 40
    # flat 的时序
    roll_time: float = 0.8          # 翻滚时长（秒）
    settle_time: float = 0.35       # 定格回弹时长（秒）
    # cube 的时序：按下压缩 → 弹起旋转 → 落地回弹 → 读点数
    press_time: float = 0.10
    spin_time: float = 0.45
    land_time: float = 0.18
    read_time: float = 0.18
    lift: float = 70                # 弹起高度
    face_dir: str = None            # 有 1.png~6.png 时用贴图代替画点（flat）

    @property
    def rolling_time(self):
        """从按下到点数朝上的时长。"""
        if self.style == "cube":
            return self.press_time + self.spin_time + self.land_time
        return self.roll_time

    @property
    def reveal_time(self):
        """点数朝上后停留展示的时长，之后开始移动。"""
        return self.read_time if self.style == "cube" else self.settle_time
