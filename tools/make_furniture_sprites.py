"""给后宅家具画手绘图：方块白模定角度和占地，AI 照着重画，再抠图对齐回格子。

    python tools/make_furniture_sprites.py guide <工作目录> [家具 id ...]   # 按 catalog 里的 boxes 画白模 <id>_guide.png
    python tools/make_furniture_sprites.py gen <工作目录> [家具 id ...]     # 白模 + 风格样板 → <id>_raw.png（已有的跳过）
    python tools/make_furniture_sprites.py import <工作目录> [家具 id ...]  # 去底、对齐、缩放，写进 content/room/furniture/ 和 catalog

不给 id 就是 DESC 里写了描述的全部家具。

和碧蓝航线后宅一样，每件家具只画一个朝向，另一个朝向网页里左右镜像，所以一件只要一张图。

- 白模：网页同一套等距投影（x 往右下、y 往左下、z 往上），按 boxes 画带描边的纯色方块，白底。
  AI 最容易画歪的就是等距角度和占地，白模把这两样定死，造型、质感、细节交给 AI 按 DESC 重新设计。
- 生成：走 Codex CLI 的图片生成（`codex exec --enable image_generation`，用的是本机 Codex 登录的 ChatGPT；CLI 位置见 CODEX），
  第一张图是白模，后面跟着 STYLE_REFS 里已经定稿的家具图当画风样板，整套家具才像一个人画的。
- 导入：从四边往里把和底色相近的连通区域抠掉（家具都有描边，里面的白色不会被抠），
  按「外框宽度一样、外框底边中点对齐」把成图套回白模，换算出格子原点（锚点）在图上的位置；
  裁掉空白、缩到每屏幕单位 SCALE 像素，写 PNG 和 catalog 的 sprite 字段。
  套得不准的件在 NUDGE 里手动挪（白模像素）。

只用 PySide6，不需要别的库。
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt   # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPolygonF   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "content", "room", "catalog.json")
OUT_DIR = os.path.join(ROOT, "content", "room", "furniture")
TILE_W, TILE_H, UNIT_Z = 64, 32, 36   # 和 room/src/model.ts 一样
CANVAS = 1024
FILL = 0.62          # 白模外框占画布的比例：四周留白给 AI 发挥（靠背、装饰会比方块高一点）
SCALE = 3            # 导入后每屏幕单位几个像素：房间最大放大 2.2 倍 × 2x 屏，够清楚
BG_TOL = 40          # 和底色差多少以内算背景（RGB 各通道差的和）
ALPHA_MIN = 24
PAD = 2
# Codex CLI：默认模型要新版 CLI，Homebrew / npm 装的可能太旧，优先用 ChatGPT 桌面版自带的
CODEX = os.environ.get("CODEX_BIN") or next(
    (p for p in ("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",) if os.path.exists(p)), "codex")

COMMON = """把第一张图里的方块白模重画成一件精致的日系手游「后宅」家具图。
要求：
- 严格保持白模的视角和摆放：2:1 等距视角，看得到顶面和左右两个侧面；家具的朝向、占地轮廓、在画面里的位置和大小都和白模一致。
  白模只是体块示意，造型按下面的描述重新设计，但角度、占地、哪一侧高（靠背、床头在哪）不能变。
- 画风：Q 版、圆润可爱、略带夸张的造型；干净的彩色描边（比底色深一档的同色系线条，不用纯黑线）；
  赛璐璐上色：底色 + 一层暗部 + 一笔高光，光从左上方来；饱和但柔和的配色；有小细节（纹理、花纹、小摆件），一眼能看出是什么。
- 只画这件家具本身：透明背景（做不到就用纯白背景），不画地板、墙和投在地上的影子，不要文字、不要人物。整件家具完整地在画面里，四周留白。"""
STYLE = "第二张图开始是同一套家具里已经定稿的样子：画风、线条粗细、上色方式、光照方向和它们保持一致。"

# 每件家具的设计描述（造型、材质、细节）。白模里高起来的部分对应靠背、床头。
DESC = {
    "shell_bed": "贝壳床：床头是一面竖起来的粉色大扇贝壳（有一道道放射状的棱，边缘是波浪形），立在白模里高起来的那一侧；"
                 "床身是圆润的粉色贝壳底座，铺着奶白色厚床垫和浅粉色被子，被子上点缀几颗小海星；靠床头放一个蓬松的白枕头。",
    "driftwood_table": "浮木小桌：一张矮矮的方形小茶几，桌面是一整块被海浪磨圆的浮木板，看得见木纹和年轮，边缘不规整；"
                       "四条歪歪扭扭的浮木桌腿；桌面正中放着一个圆肚子的玻璃瓶，里面装着蓝色海水和两颗小贝壳。",
    "coral_stool": "珊瑚凳：一个小圆凳，凳腿是一丛分叉的珊瑚红色珊瑚，凳面是软软鼓鼓的珊瑚粉圆坐垫，坐垫边上一圈白色小圆点。",
    "lifebuoy_rug": "救生圈地毯：平铺在地上、几乎没有厚度的圆形地毯，图案是红白四段相间的救生圈，外圈绕着一圈米色细绳，"
                    "圆心是米色的。只看得到地毯的正面，像贴在地上一样平。",
    "lighthouse_lamp": "灯塔落地灯：一座红白横条纹的小灯塔做成的落地灯，底座是白色圆台；上面是一圈透明玻璃的灯室，"
                       "里面一颗暖黄色灯泡在发光（带一圈柔和光晕）；顶上是红色的圆锥尖顶和一个小风向标。",
    # ---------- 安静书房 ----------（「正面」= 白模里朝左下方的那一面）
    "study_desk": "书桌：一张圆角的原木色小书桌，桌腿短短胖胖；左边是一个带两个小抽屉的桌柜（抽屉上有圆圆的木把手），"
                  "抽屉、坐人的那一面朝白模里左下方的正面；桌面右边一盏奶黄色的小台灯（圆圆的灯罩），"
                  "左边摊着一本打开的蓝色笔记本，旁边一支铅笔。",
    "bookshelf": "书架：一个靠墙站的原木色矮书架，三层，圆角边框，顶上有一圈小小的弧形装饰；"
                 "敞开的那一面朝白模里左下方的正面，看得见每层塞满了彩色的书（红、蓝、绿、橙、紫，高矮不一，有一本斜靠着），"
                 "最上层除了书还有一个小地球仪和一盆小多肉。",
    "swivel_chair": "转椅：一把圆滚滚的蓝色软包办公转椅，椅背在白模里高起来的那一侧、坐垫朝左下方的正面；"
                    "椅背上缝着一个白色小鲸鱼尾巴图案；底下是灰色的升降杆和五个小轮子的星形脚。",
    "beanbag": "懒人沙发：一个胖乎乎、软塌塌的芥末黄豆袋懒人沙发，靠背一侧鼓起来（在白模里高起来的那一侧），"
               "坐的地方压出一个舒服的凹陷，表面有布料褶皱和缝线；上面随手丢着一个小鲸鱼抱枕。",
    # ---------- 健身角 ----------
    "yoga_mat": "瑜伽垫：一张平铺在地上的薄荷绿瑜伽垫，长条形、圆角，几乎没有厚度，靠一头卷起一小截；"
                "垫子上印着浅色的波浪纹；旁边不放别的东西。只看得到垫子的正面，像贴在地上一样平。",
    "dumbbell_rack": "哑铃架：一个矮矮的灰色金属哑铃架，两层；上层左右各架着一对圆头的粉色和蓝色小哑铃，"
                     "下层放着一个白色的小电饭煲（主人拿它当壶铃练硬拉），电饭煲盖子上有个小把手。",
    "water_cooler": "饮水机：一台圆润的白色立式饮水机，顶上倒扣着一桶透明的浅蓝色桶装水（水桶上贴着一个白色小水滴贴纸，"
                    "能看到水里的高光），出水口和蓝、红两个小龙头在白模里左下方的正面，下面有一个接水的小托盘。",
    # ---------- 不属于套装 ----------
    "pothos": "绿萝盆栽：一个圆肚子的赤陶色花盆（盆口一圈白边），里面是一大丛茂盛的绿萝，心形叶子有深浅两种绿和浅色叶脉，"
              "有几条藤垂到盆外面。",
    "round_rug": "米色地毯：一张平铺在地上、几乎没有厚度的椭圆形米色绒毛地毯，边缘一圈深一点的奶咖色滚边，"
                 "中间织着一圈浅色的小花纹。只看得到地毯的正面，像贴在地上一样平。",
}
# 已经定稿、拿来当画风样板的家具（按顺序附在白模后面）
STYLE_REFS = ["shell_bed", "driftwood_table"]
# 套回白模时手动挪一下（白模像素，往右、往下为正）
NUDGE = {}


def load_catalog():
    with open(CATALOG, encoding="utf-8") as f:
        return json.load(f)


def project(x, y, z=0.0):
    return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2 - z * UNIT_Z


def box_faces(item):
    """白模的多边形（屏幕单位），从后往前：每个 box 的 +y 面、+x 面、顶面，和网页的 itemPolys 一样。"""
    boxes = sorted(item["boxes"], key=lambda b: (b["at"][0] + b["size"][0] / 2 + b["at"][1] + b["size"][1] / 2, b["at"][2]))
    out = []
    for b in boxes:
        (x0, y0, z0), (w, d, h) = b["at"], b["size"]
        x1, y1, z1 = x0 + w, y0 + d, z0 + h
        c = QColor(b["color"])
        out.append(([project(x0, y1, z0), project(x1, y1, z0), project(x1, y1, z1), project(x0, y1, z1)], c.darker(139)))
        out.append(([project(x1, y0, z0), project(x1, y1, z0), project(x1, y1, z1), project(x1, y0, z1)], c.darker(116)))
        out.append(([project(x0, y0, z1), project(x1, y0, z1), project(x1, y1, z1), project(x0, y1, z1)], c))
    return out


def guide_frame(item):
    """白模在画布上的摆法：每屏幕单位 k 像素，格子原点在 (ox, oy)；外框 (左, 上, 右, 下)。"""
    pts = [p for poly, _ in box_faces(item) for p in poly]
    sx, sy = item["size"]
    pts += [project(0, sy), project(sx, 0), project(sx, sy)]   # 占地的左右角和前角也算进来
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    k = CANVAS * FILL / max(x1 - x0, y1 - y0)
    ox = CANVAS / 2 - (x0 + x1) / 2 * k
    oy = CANVAS / 2 - (y0 + y1) / 2 * k + CANVAS * 0.06   # 稍微往下放，上面多留点空
    return k, ox, oy


def guide(work, ids):
    os.makedirs(work, exist_ok=True)
    cat = {it["id"]: it for it in load_catalog()["items"]}
    for iid in ids:
        item = cat[iid]
        k, ox, oy = guide_frame(item)
        img = QImage(CANVAS, CANVAS, QImage.Format.Format_ARGB32)
        img.fill(QColor("#ffffff"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for poly, color in box_faces(item):
            p.setBrush(color)
            p.setPen(QPen(color.darker(160), 2.5))
            p.drawPolygon(QPolygonF([QPointF(ox + x * k, oy + y * k) for x, y in poly]))
        p.end()
        img.save(os.path.join(work, f"{iid}_guide.png"))
        print(f"{iid}: 白模", flush=True)


def silhouette(img, bg=True):
    """不透明（或和白底不一样）的像素外框 (左, 上, 右, 下)，右、下不含。"""
    w, h = img.width(), img.height()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            c = img.pixelColor(x, y)
            if c.alpha() >= ALPHA_MIN and not (bg and c.red() + c.green() + c.blue() > 3 * 250):
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


# ---------- 生成 ----------
def gen_one(work, iid):
    raw = os.path.join(work, f"{iid}_raw.png")
    if os.path.exists(raw):
        return
    refs = [os.path.join(OUT_DIR, f"{r}.png") for r in STYLE_REFS if r != iid]
    refs = [r for r in refs if os.path.exists(r)]
    prompt = (COMMON + ("\n" + STYLE if refs else "") + "\n这件家具：" + DESC[iid] +
              f"\n\n用图片生成工具画一张 1024x1024 的图。画好后把图片文件复制到 {raw}，只做这一件事，不要改别的文件。")
    since = time.time()
    cmd = [CODEX, "exec", "--enable", "image_generation", "--skip-git-repo-check", "-s", "workspace-write",
           "-c", 'model_reasoning_effort="medium"',
           "-C", work, "-i", os.path.join(work, f"{iid}_guide.png")]
    for r in refs:
        cmd += ["-i", r]
    for attempt in range(4):   # 「model is at capacity」这类临时错误：等一会儿重来
        if subprocess.run(cmd + ["--", prompt], stdin=subprocess.DEVNULL).returncode == 0:
            break
        if os.path.exists(raw) or attempt == 3:
            break
        print(f"{iid}: Codex 出错，{60 * (attempt + 1)} 秒后重试", flush=True)
        time.sleep(60 * (attempt + 1))
    if not os.path.exists(raw):   # 没复制过来：去 Codex 存生成图的地方找这次新画的
        found = [f for f in glob.glob(os.path.expanduser("~/.codex/generated_images/**/*.png"), recursive=True)
                 if os.path.getmtime(f) >= since]
        if not found:
            raise RuntimeError(f"{iid}: 没拿到生成的图")
        shutil.copy(max(found, key=os.path.getmtime), raw)
    print(f"{iid}: 生成完", flush=True)


def gen(work, ids):
    missing = [i for i in ids if not os.path.exists(os.path.join(work, f"{i}_guide.png"))]
    if missing:
        guide(work, missing)
    for iid in ids:
        gen_one(work, iid)


# ---------- 导入 ----------
def cut_background(img):
    """从四边往里，把和角上底色相近的连通像素变透明。"""
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    if all(img.pixelColor(x, y).alpha() < ALPHA_MIN for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))):
        return img   # 本来就是透明底
    bg = img.pixelColor(0, 0)
    br, bgc, bb = bg.red(), bg.green(), bg.blue()
    seen = bytearray(w * h)
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    clear = QColor(0, 0, 0, 0)
    while stack:
        x, y = stack.pop()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        c = img.pixelColor(x, y)
        if abs(c.red() - br) + abs(c.green() - bgc) + abs(c.blue() - bb) > BG_TOL:
            continue
        img.setPixelColor(x, y, clear)
        if x > 0:
            stack.append((x - 1, y))
        if x < w - 1:
            stack.append((x + 1, y))
        if y > 0:
            stack.append((x, y - 1))
        if y < h - 1:
            stack.append((x, y + 1))
    return img


def import_one(work, iid, cat_items):
    item = cat_items[iid]
    k, ox, oy = guide_frame(item)
    gl, gt, gr, gb = silhouette(QImage(os.path.join(work, f"{iid}_guide.png")))
    img = cut_background(QImage(os.path.join(work, f"{iid}_raw.png")))
    l, t, r, b = silhouette(img, bg=False)
    s = (gr - gl) / (r - l)             # 白模像素 / 成图像素
    nx, ny = NUDGE.get(iid, (0, 0))
    # 成图外框底边中点 ↔ 白模外框底边中点，再换算出格子原点在成图上的位置
    ax = (l + r) / 2 + (ox - (gl + gr) / 2 - nx) / s
    ay = b + (oy - gb - ny) / s
    per_unit = k / s                    # 成图像素 / 屏幕单位
    f = min(1.0, SCALE / per_unit)
    l, t, r, b = max(0, l - PAD), max(0, t - PAD), min(img.width(), r + PAD), min(img.height(), b + PAD)
    crop = img.copy(l, t, r - l, b - t)
    out = crop.scaled(round(crop.width() * f), round(crop.height() * f),
                      Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    os.makedirs(OUT_DIR, exist_ok=True)
    out.save(os.path.join(OUT_DIR, f"{iid}.png"))
    return {"src": f"{iid}.png", "anchor": [round((ax - l) * f, 1), round((ay - t) * f, 1)], "scale": round(per_unit * f, 3)}


def set_sprite(text, iid, sprite):
    """catalog.json 是手排的格式：只改这件家具的 sprite 那一行，别的原样不动。"""
    start = text.index(f'"id": "{iid}"')
    end = text.index("\n    }", start)
    body = re.sub(r',\n      "sprite": \{[^\n]*\}', "", text[start:end])
    return text[:start] + body + ',\n      "sprite": ' + json.dumps(sprite, ensure_ascii=False) + text[end:]


def import_(work, ids):
    with open(CATALOG, encoding="utf-8") as f:
        text = f.read()
    items = {it["id"]: it for it in json.loads(text)["items"]}
    for iid in ids:
        if not os.path.exists(os.path.join(work, f"{iid}_raw.png")):
            print(f"{iid}: 还没生成，跳过", flush=True)
            continue
        sprite = import_one(work, iid, items)
        text = set_sprite(text, iid, sprite)
        print(f"{iid}: {sprite}", flush=True)
    json.loads(text)
    with open(CATALOG, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("guide", "gen", "import"):
        sys.exit(__doc__)
    _app = QGuiApplication.instance() or QGuiApplication([])   # noqa: F841  QPainter 画字体、抗锯齿要有个 app
    work, ids = sys.argv[2], sys.argv[3:] or list(DESC)
    unknown = [i for i in ids if i not in DESC]
    if unknown:
        sys.exit(f"这些家具还没写描述（DESC）：{unknown}")
    {"guide": guide, "gen": gen, "import": import_}[sys.argv[1]](work, ids)


if __name__ == "__main__":
    main()
