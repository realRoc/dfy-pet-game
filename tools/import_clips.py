"""把 dsh-pet 的动作动画整理成游戏素材：python tools/import_clips.py <dsh-pet 的 assets/webm 目录>

dsh-pet（https://github.com/PC2005-cloud/dsh-pet）的动画是 640×360、24 帧、10 秒的透明 webm（VP9 + alpha），
人物只占画面中间一小块。这里逐段：
- 用 ffmpeg 算出整段里人物的外框（所有帧的并集），运行时只画这一块
- 外框记的是原画面里的位置，运行时按「待机」那段的人物身高和脚底对齐，换哪段动画人都不会跳

webm 原样复制：试过裁边后重压，VP9 重压反而比原文件大；转成逐帧图片（WebP / PNG）更是大 4~8 倍。
640×360 的 VP9 解一帧不到 1ms，运行时整帧解码再裁不费事。

产物放角色包的 actions 动画目录（大肥鱼是 characters/dafeiyu/clips/）：每段一个 <名字>.webm，外加 clips.json（分类、外框、帧数）。
需要本机装有带 libvpx 的 ffmpeg（brew install ffmpeg）；运行时用 PyAV 解码，不需要 ffmpeg。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from character import CHAR   # noqa: E402  产物写进当前角色包（DFY_CHARACTER，默认 dafeiyu）
OUT_DIR = CHAR.anim_dir("actions") or CHAR.path("clips")
REF_CLIP = "待机呼吸休闲"
PAD = 4
ALPHA_MIN = 24   # VP9 的 alpha 有损，背景不是严格的 0

# 分类照搬 dsh-pet 的 config.jsonc（随机动作的分类池），另把点击回应、转身、走动、碎碎念并进来；
# 余额、工作状态是 DeepSeek Harness 专用的，不要。
CATEGORIES = [
    ("小动作", [
        "悠闲哼歌", "超大伸懒腰", "原地敲击桌面互动", "原地重力下蹲压缩", "哈欠连天",
        "原地小憩沉眠", "女仆屈膝礼仪", "被吓一跳", "小幅度原地360度旋转展示",
        "偷吃零食被抓住", "用鲸鱼尾巴拍打地面", "打瞌睡被惊醒", "照镜子", "整体换装试色",
        "轻快记录", "写代码", "摇扇纳凉", "晨间刷牙", "东张西望",
        "碎碎念-擦桌碎碎念", "碎碎念-发呆碎碎念", "碎碎念-对屏碎碎念",
        "螃蟹走路", "原地漂浮踏步", "原地左转奔跑",
    ]),
    ("互动", [
        "点击回应-开心跃动", "点击回应-害羞惊讶", "点击回应-傲娇生气", "点击回应-挠痒咯咯笑",
        "点击回应-元气挥手",
    ]),
    ("玩耍", [
        "原地专心玩魔方", "原地蹲下玩玩具汽车", "鲸鱼吐泡泡特效", "原地跳跃抓碎头顶物品",
        "玩游戏气急败坏", "玩水枪", "小提琴演奏", "蓝鲸现世", "优雅女仆舞", "轻快摇摆舞",
        "可爱宅舞", "吹气球", "动物环绕", "放风筝", "拆礼物", "变鸽子", "扑克魔术",
        "抽陀螺", "吹笛子", "蝴蝶蜜蜂环绕头顶开花", "撸猫", "凭空生花", "骑木马",
        "三球抛接", "踢毽子", "下五子棋", "荡秋千",
    ]),
    ("吃什么", [
        "吃白饭", "大口吃零食", "吃Token", "吃早餐", "吃午餐", "吃晚餐", "吃冰淇淋融化",
        "吃大闸蟹", "吃糖葫芦", "吃长寿面", "吃西瓜", "涮火锅",
    ]),
    ("时节", [
        "被落叶淹没", "中秋赏月吃月饼", "堆雪人", "放烟花", "吃粽子", "吃年糕", "吃青团",
        "吃腊八粥", "吃重阳糕", "收红包", "写福字", "穿针乞巧", "舞狮头", "讨糖南瓜灯",
        "插茱萸赏菊", "放河灯", "萌化小幽灵", "装点圣诞树", "放孔明灯", "吃汤圆", "吃饺子",
    ]),
    ("文字", ["是啊，吃什么", "深度思考碎碎念"]),
]


def label(name):
    """菜单里显示的名字：去掉「原地」「点击回应-」「碎碎念-」这类前缀。"""
    for prefix in ("点击回应-", "碎碎念-", "原地"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def bbox(src):
    """整段所有帧人物外框的并集 (x, y, w, h) 和帧数。"""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-c:v", "libvpx-vp9", "-i", src,
         "-vf", f"alphaextract,bbox=min_val={ALPHA_MIN}", "-f", "null", "-"],
        capture_output=True, text=True, check=True).stderr
    boxes = [tuple(map(int, m)) for m in re.findall(r"x1:(\d+) x2:(\d+) y1:(\d+) y2:(\d+)", out)]
    frames = len(re.findall(r"\[Parsed_bbox_\d+ @ [^\]]+\] n:", out))
    x1 = min(b[0] for b in boxes)
    x2 = max(b[1] for b in boxes)
    y1 = min(b[2] for b in boxes)
    y2 = max(b[3] for b in boxes)
    return (x1, y1, x2 - x1 + 1, y2 - y1 + 1), frames


def probe(src):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "json", src],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return s["width"], s["height"], int(num) / int(den)


def convert(src_dir, name):
    src = os.path.join(src_dir, f"{name}.webm")
    vw, vh, fps = probe(src)
    (x, y, w, h), frames = bbox(src)
    # 四周留一点余量
    x0, y0 = max(0, x - PAD), max(0, y - PAD)
    w, h = min(vw, x + w + PAD) - x0, min(vh, y + h + PAD) - y0
    dst = os.path.join(OUT_DIR, f"{name}.webm")
    shutil.copyfile(src, dst)
    print(f"{name}: {w}×{h} @ ({x0},{y0})  {frames} 帧  {os.path.getsize(dst) // 1024} KB")
    return {"file": f"{name}.webm", "crop": [x0, y0, w, h], "frames": frames, "fps": fps}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src_dir = sys.argv[1]
    os.makedirs(OUT_DIR, exist_ok=True)

    (rx, ry, rw, rh), _ = bbox(os.path.join(src_dir, f"{REF_CLIP}.webm"))
    names = [n for _, clips in CATEGORIES for n in clips]
    missing = [n for n in names if not os.path.exists(os.path.join(src_dir, f"{n}.webm"))]
    if missing:
        sys.exit(f"找不到这些动画：{missing}")
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = dict(zip(names, pool.map(lambda n: convert(src_dir, n), names)))

    manifest = {
        "source": "https://github.com/PC2005-cloud/dsh-pet",
        # 待机动画里人物的身高、中线和脚底（原画面像素），运行时按它把人物缩放到桌宠身高、脚底对齐
        "ref": {"h": rh, "cx": rx + rw / 2, "foot": ry + rh},
        "categories": [{"name": c, "clips": clips} for c, clips in CATEGORIES],
        "clips": {n: dict(results[n], label=label(n)) for n in names},
    }
    with open(os.path.join(OUT_DIR, "clips.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(OUT_DIR, r["file"])) for r in results.values())
    print(f"共 {len(names)} 段，{total / 1048576:.1f} MB")


if __name__ == "__main__":
    main()
