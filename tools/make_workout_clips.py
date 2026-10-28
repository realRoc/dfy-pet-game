"""用 Seedance 生成跟练动画，再抠成透明 webm：

    python tools/make_workout_clips.py gen <工作目录> [名字 ...]   # 提交生成，下载绿幕 mp4 到工作目录（已有的跳过）
    python tools/make_workout_clips.py import <工作目录>           # 抠绿幕、算外框，产物放 content/workout/clips/

生成走 TeamoRouter 的视频接口（POST /v1/videos，Seedance 2.5 图生视频，首尾帧），
Key 从环境变量 TEAMOROUTER_API_KEY 读，地址可用 TEAMOROUTER_BASE 改（默认 https://api.teamorouter.vip/v1）。

每段的首帧、尾帧默认都是同一张「中立」图：sprites/正面.png 原样放大贴在纯绿幕上。
所以每段都从原版站姿开始、回到原版站姿，任意两段首尾相接都不会跳——中立 → 动作 / 表情 → 中立。
躺着、蹲着练的动作拆成 进入 / 循环 / 起身 三段：进入那段不给尾帧，
取它的最后一帧当循环段的首尾帧和起身段的首帧（SPECS 里 first / last 写别的段名）。
首帧 / 尾帧也可以写 "side"：sprites/侧面.png 按同样的大小和位置贴绿幕（朝画面左边），给要转身走开、走回来的片段用。

别的素材（比如喝水提醒，tools/make_water_clips.py）复用这里的生成和抠像，只换 SPECS 和产物目录。

需要本机装有带 libvpx 的 ffmpeg（brew install ffmpeg）。
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "content", "workout", "clips")
SPRITE = os.path.join(ROOT, "sprites", "正面.png")
SIDE_SPRITE = os.path.join(ROOT, "sprites", "侧面.png")
BASE = os.environ.get("TEAMOROUTER_BASE", "https://api.teamorouter.vip/v1")
MODEL = "seedance-2-5-image-to-video-basic"
CANVAS = 960          # 中立图边长（1:1）
SPRITE_H = 540        # 中立图里人物的身高
FOOT_MARGIN = 110     # 脚底离画面底边
PAD = 4
ALPHA_MIN = 24
GREEN = (0, 250, 4)   # Seedance 出来的绿幕实际是这个颜色
MATTE_LO = 0.2        # 不透明度低于这个的算背景：发光特效会把一大片绿幕照亮，留着就是一层罩住整段画面的白雾
WORKERS = 5           # 同时生成几段；接口有频率限制，太多会被拒

COMMON = (
    "固定机位，镜头完全不动，不推拉不摇移。纯绿幕背景（#00FF00），全程没有地面、阴影和任何背景元素，"
    "不出现文字和字幕。画面里只有角色本身：不画墙、不画地面和地面线、不画任何影子。角色始终完整在画面内。严格保持参考图里的角色：Q版二头身鲸鱼娘女仆，蓝色长发、"
    "白色女仆头饰、蓝色鲸鱼耳朵、深蓝女仆裙配白围裙（围裙上有小鲸鱼图案）、裙摆白色花边、身后蓝色鲸鱼尾巴；"
    "画风、比例、配色、线条都和参考图一致，衣服款式全程不变，不要变成长腿、不要变写实。"
    "动作要软萌、Q弹、夸张一点，像日系萌系动画；表情生动可爱。"
)
BACK = "最后一秒回到和首帧完全一样的正面站姿和表情，乖巧站好。"

# 名字: (秒数, 首帧, 尾帧, 动作描述)。首帧 / 尾帧：None = 中立图，"side" = 侧面图，"-" = 不给尾帧，其他 = 那一段的最后一帧
SPECS = {
    # ---------- 站着练 ----------
    "squat": (5, None, None, """动作：可爱的深蹲，做两次。
0-0.5秒：正面站好，双手握拳放在胸前，鼓起小脸认真地点一下头。
0.5-2秒：双脚稍微分开，屁股往后坐下深蹲到底，裙摆蓬起来盖住膝盖，双手往前平举保持平衡，脸憋得鼓鼓的、眯着眼用力，尾巴翘起来。
2-2.8秒：嘿咻一下站起来，身体Q弹地回弹一下，头发和鲸鱼耳朵跟着晃。
2.8-4.5秒：再蹲一次，这次更吃力，小脸皱成一团，蹲到底时微微发抖，然后猛地站起来。"""),
    "squat_open_close": (6, None, None, """动作：开合深蹲，宽一下窄一下。
0-0.5秒：正面站好，握拳给自己打气。
0.5-2秒：双脚往两边小跳分开成宽站距，屁股往下坐深蹲到底，双手合十放胸前，裙摆蓬开盖住腿。
2-2.6秒：站起来，双脚小跳并拢。
2.6-4.2秒：双脚并拢窄站距深蹲到底，膝盖并在一起，双手往前平举，小脸用力憋红。
4.2-5秒：站起来，身体Q弹回弹，头发晃一下。"""),
    "curtsy_lunge": (5, None, None, """动作：屈膝礼弓步（像女仆行屈膝礼），做两次。
0-0.5秒：正面站好，两手轻轻提起裙摆两边。
0.5-2秒：右腿往左后方斜着交叉到身后，两腿一起弯曲往下蹲，像优雅地行女仆屈膝礼，微微低头，表情害羞又认真。
2-2.6秒：右腿收回来站直。
2.6-4.2秒：再做一次屈膝礼弓步，这次蹲得更低，尾巴翘起来保持平衡，小身体有点晃。
4.2-5秒：收腿站直，放下裙摆。"""),
    "lunge": (6, None, None, """动作：弓步蹲，左右各一次。
0-0.5秒：正面站好，双手叉腰。
0.5-2.2秒：右腿往前迈一大步，两腿弯曲往下蹲成弓步，后膝快贴地，双手叉腰，小脸认真用力。
2.2-2.8秒：右腿收回来站直，Q弹一下。
2.8-4.5秒：左腿往前迈一大步蹲成弓步，有点晃，鲸鱼尾巴甩一下保持平衡。
4.5-5.2秒：左腿收回站直。"""),
    "deadlift": (7, None, None, """动作：拎着电饭煲做硬拉。
0-1秒：正面站好，从身后吭哧吭哧拿出一个白色的小电饭煲，双手拎着把手垂在身前，表情认真。
1-2.8秒：屁股往后推，上身前倾，背挺得平平的，电饭煲贴着腿慢慢放到小腿前，然后用力站起来，挺胸。
2.8-4.6秒：再来一次，电饭煲好重，小脸憋红，站起来时身体晃了一下。
4.6-6秒：把电饭煲藏回身后，拍拍手。"""),
    # ---------- 躺着练（进入 / 循环 / 起身）----------
    "bridge_enter": (4, None, "-", """动作：躺下准备做臀桥。
0-1秒：正面站好，看了看地面，乖乖地坐下来。
1-3秒：身体转成侧面朝向镜头，仰面躺下，头在画面左边、脚在画面右边，双膝弯曲立起来，双脚踩地，双手平放在身体两侧，裙摆盖好，表情乖巧。
3-4秒：保持仰躺屈膝的姿势不动，眨眨眼。"""),
    "bridge_loop": (5, "bridge_enter", "bridge_enter", """动作：仰躺着做臀桥，小幅度做两次。全程侧面朝向镜头仰躺，头在画面左边、脚在画面右边，双膝弯曲、双脚踩地。
端庄可爱：裙摆和白色衬裙全程盖住大腿，裙子不往下滑、不掀起；双脚一直穿着深蓝色小皮鞋和白色袜子。
0-0.5秒：保持仰躺屈膝。
0.5-2秒：屁股只往上抬起一点点（小幅度，离地一拳高），小脸用力憋红、腮帮子鼓起来，停一下，然后慢慢放下来。
2-2.5秒：躺平喘口气。
2.5-4.2秒：再抬一次，同样小幅度，抬起时身体微微发抖，然后慢慢放下。
4.2-5秒：回到和首帧一样的仰躺屈膝姿势。"""),
    "bridge_single_loop": (5, "bridge_enter", "bridge_enter", """动作：仰躺着做单腿臀桥，小幅度做两次。全程侧面朝向镜头仰躺，头在画面左边、脚在画面右边。
端庄可爱：裙摆和白色衬裙全程盖住大腿，裙子不往下滑、不掀起；两只脚一直穿着深蓝色小皮鞋和白色袜子，鞋子始终穿在脚上不脱落。
0-0.5秒：保持仰躺屈膝，把一条小短腿往前伸直，只抬到和另一条腿的膝盖差不多高（斜向前方，不要朝天高举）。
0.5-2秒：另一只脚踩地，屁股只往上抬起一点点（小幅度），伸直的腿保持在原来的高度，小脸皱成一团用力，然后慢慢放下。
2-3.6秒：再抬一次，同样小幅度，有点晃，赶紧稳住。
3.6-5秒：把伸直的腿收回来踩地，回到和首帧一样的仰躺屈膝姿势。"""),
    "bridge_exit": (4, "bridge_enter", None, """动作：做完臀桥起身。
0-1.5秒：仰躺着长出一口气，然后撑着地面坐起来。
1.5-3秒：慢慢站起来，转回正面，拍拍裙子上的灰。"""),
    "wall_sit_enter": (4, None, "-", """动作：准备静蹲（空气椅）。全程正面朝向镜头。
0-1.5秒：正面站好，双脚分开与肩同宽，握拳给自己打气。
1.5-3秒：屁股往后坐，慢慢蹲到大腿和地面平行，像坐在一把看不见的小椅子上，上身挺直，双手握拳放在胸前，裙摆盖住腿。
3-4秒：保持这个半蹲姿势不动，表情认真。"""),
    "wall_sit_loop": (5, "wall_sit_enter", "wall_sit_enter", """动作：静蹲（空气椅）坚持住。全程正面朝向镜头，保持大腿与地面平行的半蹲姿势，位置不变。
0-2秒：腿开始微微发抖，小脸憋红，额头冒出一滴汗。
2-3.5秒：抖得更厉害，咬紧牙关，鲸鱼耳朵耷拉下来，眼睛泪汪汪。
3.5-5秒：深吸一口气重新稳住，握拳给自己打气，回到和首帧一样的姿势和表情。"""),
    "wall_sit_exit": (4, "wall_sit_enter", None, """动作：静蹲结束站起来。
0-1.5秒：双手撑着膝盖慢慢站起来，腿软得晃了一下。
1.5-3秒：揉揉大腿，甩甩腿，长出一口气。"""),
    # ---------- 休息 / 结束 ----------
    "tired": (5, None, None, """动作：累了，弯腰大喘气。
0-1秒：正面站好，肩膀一下子垮下来。
1-3.5秒：弯腰双手扶着膝盖大口喘气，肩膀一起一伏，额头冒汗，舌头吐出来一点，鲸鱼耳朵和尾巴都耷拉着。
3.5-4.2秒：抹一把汗，慢慢直起身。"""),
    "drink": (6, None, None, """动作：休息喝水。
0-1秒：正面站好，从身后拿出一个蓝色的小水壶。
1-3.5秒：仰头咕嘟咕嘟大口喝水，脸颊鼓鼓的，喝完满足地“哈——”一声，眯着眼一脸幸福。
3.5-4.5秒：用袖子擦擦嘴，把水壶藏回身后。"""),
    "cheer": (5, None, None, """动作：练完啦，开心欢呼。
0-0.5秒：正面站好，眼睛一亮。
0.5-3.5秒：双手高高举起原地蹦跳两下，笑得眼睛眯成弯月，头发和鲸鱼耳朵跟着飘，尾巴开心地甩来甩去，身边冒出小星星。
3.5-4.2秒：落地，比一个胜利的手势。"""),
    "collapse": (8, None, None, """动作：练完彻底瘫倒，然后爬起来。
0-1.5秒：正面站好，晃了晃，腿一软。
1.5-3.5秒：整个人“啪叽”一下脸朝下趴倒在地上，四肢摊开，一个白色半透明的小鲸鱼魂从头顶飘出来。
3.5-5.5秒：小鲸鱼魂在头顶飘了一圈，又“嗖”地钻回身体里。
5.5-7.2秒：撑着地面慢慢爬起来，拍拍裙子，揉揉脸。"""),
    # ---------- 偷懒：中立 → 偷懒 → 被发现 → 中立 ----------
    "lazy_doze": (6, None, None, """动作：偷懒——站着打瞌睡，被发现后惊醒。
0-1秒：正面站好，眼皮慢慢变沉，打了一个小小的哈欠，用小手捂嘴。
1-3.5秒：站着睡着了，脑袋一点一点往下垂，身体左右轻轻摇晃，鼻子吹出一个透明的鼻涕泡，泡泡随呼吸一大一小，嘴角流一点口水，表情幸福又呆萌，尾巴软软地垂下来。
3.5-4.2秒：鼻涕泡“啵”地破了，她吓得原地一蹦，眼睛瞪得圆圆的，鲸鱼耳朵竖起来，头发炸开一下。
4.2-5.2秒：慌慌张张左右看了看，赶紧擦擦嘴，双手放到身侧立正，假装什么都没发生，脸有点红。"""),
    "lazy_phone": (7, None, None, """动作：偷懒——偷偷刷手机，被发现后慌忙藏起来。
0-1秒：正面站好，偷偷左右瞄了瞄，从围裙口袋里掏出一部小手机。
1-4秒：低头刷手机刷得入迷，手指不停往上划，脸被屏幕照亮，时不时捂嘴偷笑，尾巴开心地轻轻摇。
4-4.8秒：突然抬头发现被看到了，吓得一激灵，眼睛瞪圆，手机差点掉下来。
4.8-6秒：手忙脚乱把手机藏到身后，吐吐舌头尴尬地笑，假装在原地踏步。"""),
    "lazy_rice": (8, None, None, """动作：偷懒——偷偷干饭，被发现后赶紧收起来。
0-1.2秒：正面站好，从身后吭哧吭哧拿出一个白色的小电饭煲，打开盖子冒出热气，眼睛放光。
1.2-4.5秒：一屁股坐下来，抱着电饭煲用勺子大口大口吃白米饭，腮帮子塞得鼓鼓的，一脸幸福，嘴角沾着饭粒，尾巴满足地拍地。
4.5-5.3秒：突然发现被看到了，含着一大口饭僵住，眼睛瞪圆。
5.3-7.2秒：咕咚一口咽下去，赶紧盖上盖子把电饭煲藏回身后，站起来擦擦嘴，假装什么都没发生。"""),
    "lazy_think": (7, None, None, """动作：偷懒——假装在深度思考，其实在发呆。
0-1秒：正面站好，一只手托着下巴，抬头望天。
1-4.2秒：进入“深度思考”状态：眼神放空，嘴巴微张，头顶冒出一个转圈圈的小加载圆环和几个漂浮的问号，身体慢慢歪向一边，口水快流下来。
4.2-5秒：被发现了，猛地回神，加载圆环和问号“啪”地消失，吓一跳。
5-6.2秒：一本正经地推了推不存在的眼镜，点点头像是想明白了，然后乖乖站好。"""),
    "lazy_flop": (7, None, None, """动作：偷懒——直接躺平摆烂，被发现后弹起来。
0-1秒：正面站好，叹了一口长长的气，肩膀垮下来。
1-2秒：一屁股坐到地上，然后往后一倒，四仰八叉地躺平，像一条咸鱼。
2-4.2秒：躺着一动不动，眼睛半闭，偶尔用鲸鱼尾巴有气无力地拍一下地面，表情生无可恋。
4.2-5.2秒：发现被看到了，整个人“噌”地从地上弹起来站好。
5.2-6.2秒：拍拍裙子，敬了一个礼，表示准备好了。"""),
    "lazy_fish": (7, None, None, """动作：偷懒——偷吃小鱼干。
0-1秒：正面站好，偷偷左右看了看，从围裙口袋里摸出一条小鱼干。
1-4.2秒：背过一点身子偷偷啃小鱼干，咔嚓咔嚓，吃得眯起眼睛一脸陶醉，脸颊鼓鼓的，尾巴开心地摇。
4.2-5秒：被发现了，鱼干还叼在嘴里，眼睛瞪圆僵住。
5-6.2秒：“咕嘟”一口吞下去，把手背到身后，转回正面摇头假装没吃。"""),
    "lazy_fake": (7, None, None, """动作：偷懒——假装在练，只蹲一点点。
0-1.5秒：正面站好，偷偷瞄一眼，然后有气无力地只弯一点点膝盖，假装在深蹲，表情很敷衍。
1.5-4.2秒：一边只蹲一点点，一边夸张地擦汗、大口喘气，装出一副累坏了的样子，还偷偷打了个哈欠。
4.2-5.2秒：被发现了，尴尬地僵住，脸一下子红了。
5.2-6.2秒：挠挠头吐吐舌头，赶紧站好，握拳表示这次认真练。"""),
    "lazy_tailnap": (8, None, None, """动作：偷懒——抱着尾巴打盹。
0-1.2秒：正面站好，打了个大大的哈欠，慢慢蹲坐下来。
1.2-4.8秒：把自己的蓝色鲸鱼尾巴抱在怀里当枕头，脸蹭着尾巴缩成一团睡着了，头顶冒出“Zzz”，表情幸福，身体随呼吸一起一伏。
4.8-5.8秒：被发现了，猛地惊醒，尾巴一甩，整个人弹起来。
5.8-7.2秒：揉揉眼睛，拍拍裙子站好，不好意思地笑。"""),
}


# ---------- 生成 ----------
def _call(method, path, body=None, raw=False):
    key = os.environ.get("TEAMOROUTER_API_KEY")
    if not key:
        sys.exit("先设置环境变量 TEAMOROUTER_API_KEY")
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    return data if raw else json.loads(data)


def _data_uri(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def neutral(work, sprite=SPRITE, out_name="neutral.png"):
    """原版正面图放大贴到纯绿幕上，作为所有段的中立首尾帧。"""
    out = os.path.join(work, out_name)
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x00FF00:s={CANVAS}x{CANVAS}",
                        "-i", sprite, "-filter_complex",
                        f"[1]scale=-1:{SPRITE_H}:flags=lanczos[s];[0][s]overlay=(W-w)/2:H-h-{FOOT_MARGIN}:format=auto",
                        "-frames:v", "1", out], check=True)
    return out


def last_frame(work, name):
    out = os.path.join(work, f"{name}_last.png")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.1", "-i", os.path.join(work, f"{name}.mp4"),
                        "-update", "1", "-frames:v", "1", out], check=True)
    return out


def side(work):
    """侧面图，和中立图一样大、脚底在同一个位置：三视图的脚底中线都在图片正中。"""
    return neutral(work, SIDE_SPRITE, "side.png")


def still(work, key):
    """首帧 / 尾帧的图：None 中立图，"side" 侧面图，其他是那一段的最后一帧。"""
    if key is None:
        return neutral(work)
    if key == "side":
        return side(work)
    return last_frame(work, key)


def gen_one(work, name, specs=SPECS):
    mp4 = os.path.join(work, f"{name}.mp4")
    if os.path.exists(mp4):
        return
    secs, first, last, action = specs[name]
    first_img = still(work, first)
    body = {"model": MODEL, "prompt": COMMON + "\n" + action + ("\n" + BACK if last is None else ""),
            "seconds": str(secs), "resolution": "720p", "audio": False, "image_url": _data_uri(first_img)}
    if last != "-":
        body["end_image_url"] = _data_uri(still(work, last))
    job_file = os.path.join(work, f"{name}.job")   # 提交过的任务号：中途停掉再跑时接着等，不重复付钱
    if os.path.exists(job_file):
        with open(job_file) as f:
            vid = f.read().strip()
    else:
        while True:
            try:
                vid = _call("POST", "/videos", body)["id"]
                break
            except urllib.error.HTTPError as e:
                msg = e.read()[:300]
                if e.code != 429 and b"rate_limit" not in msg:
                    raise RuntimeError(f"{name}: 提交失败 {e.code} {msg!r}")
                time.sleep(30)
        with open(job_file, "w") as f:
            f.write(vid)
    print(f"{name}: 已提交 {vid}", flush=True)
    while True:
        time.sleep(15)
        try:
            job = _call("GET", f"/videos/{vid}")
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"{name}: 查询出错，重试 {e}", flush=True)
            continue
        if job.get("status") in ("completed", "succeeded"):
            break
        if job.get("status") in ("failed", "cancelled", "expired"):
            os.remove(job_file)
            raise RuntimeError(f"{name}: 生成失败 {json.dumps(job, ensure_ascii=False)[:500]}")
    data = _call("GET", f"/videos/{vid}/content", raw=True)
    with open(mp4 + ".part", "wb") as f:
        f.write(data)
    os.replace(mp4 + ".part", mp4)
    os.remove(job_file)
    print(f"{name}: 完成", flush=True)


def gen(work, names, specs=SPECS):
    os.makedirs(work, exist_ok=True)
    names = names or list(specs)
    unknown = [n for n in names if n not in specs]
    if unknown:
        sys.exit(f"没有这些动作：{unknown}")
    # 依赖别的段（取它的最后一帧）的，等那段先生成
    deps = {n: {d for d in specs[n][1:3] if d not in (None, "-", "side")} for n in names}
    for n in names:
        for d in deps[n]:
            if d not in names and not os.path.exists(os.path.join(work, f"{d}.mp4")):
                names.append(d)
                deps[d] = set()
    done, failed = set(), []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pending = {}
        while len(done) + len(failed) < len(names):
            for n in names:
                if n in done or n in pending or n in failed:
                    continue
                if all(d in done or os.path.exists(os.path.join(work, f"{d}.mp4")) for d in deps.get(n, ())):
                    pending[n] = pool.submit(gen_one, work, n, specs)
            time.sleep(1)
            for n, fut in list(pending.items()):
                if fut.done():
                    del pending[n]
                    try:
                        fut.result()
                        done.add(n)
                    except Exception as e:
                        print(e, flush=True)
                        failed.append(n)
            if not pending and all(n in done or n in failed or
                                   any(d in failed for d in deps.get(n, ())) for n in names):
                break
    if failed:
        sys.exit(f"失败：{failed}")


# ---------- 抠像 / 入库 ----------
def bbox(src, codec=()):
    """整段所有帧人物外框的并集 (x, y, w, h) 和帧数。"""
    out = subprocess.run(["ffmpeg", "-v", "info", *codec, "-i", src,
                          "-vf", f"alphaextract,bbox=min_val={ALPHA_MIN}", "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    boxes = [tuple(map(int, m)) for m in re.findall(r"x1:(\d+) x2:(\d+) y1:(\d+) y2:(\d+)", out)]
    frames = len(re.findall(r"\[Parsed_bbox_\d+ @ [^\]]+\] n:", out))
    x1, x2 = min(b[0] for b in boxes), max(b[1] for b in boxes)
    y1, y2 = min(b[2] for b in boxes), max(b[3] for b in boxes)
    return (x1, y1, x2 - x1 + 1, y2 - y1 + 1), frames


def matte_filter():
    """色差抠像：绿色比红、蓝多出多少就透明多少，再从半透明的像素里把绿幕的颜色减掉、还原前景色。
    比 chromakey + despill 强在半透明的地方：鬼魂、发光、鼻涕泡这些不会变成一圈灰黑的雾，换浅色桌面也干净。"""
    br, bg, bb = GREEN
    a = f"clip(1-(g(X,Y)-max(r(X,Y),b(X,Y)))/{bg - max(br, bb)},0,1)"

    def unmix(c, v):
        # 算作背景的地方颜色填 0：不然除出来的噪点全得编码进去，文件大三倍
        return f"st(0,{a});if(gt(ld(0),{MATTE_LO}),clip(({c}(X,Y)-(1-ld(0))*{v})/ld(0),0,255),0)"
    return (f"format=rgba,geq=r='{unmix('r', br)}':g='{unmix('g', bg)}':b='{unmix('b', bb)}':"
            f"a='255*clip(({a}-{MATTE_LO})/{0.97 - MATTE_LO},0,1)',format=yuva420p")


def key_one(work, name, out_dir=OUT_DIR):
    """抠绿幕 → 裁到整段外框 → VP9 + alpha 的 webm。"""
    src = os.path.join(work, f"{name}.mp4")
    keyed = os.path.join(work, f"{name}_keyed.webm")
    vf = matte_filter()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf, "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                    "-b:v", "0", "-crf", "30", "-auto-alt-ref", "0", "-an", keyed], check=True)
    (x, y, w, h), frames = bbox(keyed, ("-c:v", "libvpx-vp9"))
    x0, y0 = max(0, x - PAD), max(0, y - PAD)
    x1, y1 = min(CANVAS, x + w + PAD), min(CANVAS, y + h + PAD)
    x0, y0 = x0 - x0 % 2, y0 - y0 % 2          # yuv420 要偶数
    w, h = (x1 - x0 + 1) // 2 * 2, (y1 - y0 + 1) // 2 * 2
    dst = os.path.join(out_dir, f"{name}.webm")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-c:v", "libvpx-vp9", "-i", keyed, "-vf", f"crop={w}:{h}:{x0}:{y0}",
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30", "-auto-alt-ref", "0",
                    "-row-mt", "1", "-an", dst], check=True)
    print(f"{name}: {w}×{h} @ ({x0},{y0})  {frames} 帧  {os.path.getsize(dst) // 1024} KB", flush=True)
    # 文件已经裁过：crop 是文件里的范围，offset 是它在原画面里的位置
    return {"file": f"{name}.webm", "crop": [0, 0, w, h], "offset": [x0, y0], "frames": frames, "fps": 24}


def import_(work, specs=SPECS, out_dir=OUT_DIR, script="tools/make_workout_clips.py"):
    os.makedirs(out_dir, exist_ok=True)
    names = [n for n in specs if os.path.exists(os.path.join(work, f"{n}.mp4"))]
    missing = [n for n in specs if n not in names]
    if missing:
        print("还没生成，跳过：", missing)
    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 4) // 2)) as pool:
        results = dict(zip(names, pool.map(lambda n: key_one(work, n, out_dir), names)))
    manifest = {
        "source": f"Seedance 2.5（{MODEL}），首尾帧 = sprites/正面.png 贴绿幕；提示词见 {script}",
        # 中立图里 sprites/正面.png 整张图（含留白）的高度、中线、底边：运行时缩放到和桌宠的正面图一样大、
        # 摆在同一个位置，片段的首尾帧就和平时的正面图严丝合缝
        "ref": {"h": SPRITE_H, "cx": CANVAS / 2, "foot": CANVAS - FOOT_MARGIN},
        "clips": {n: results[n] for n in names},
    }
    with open(os.path.join(out_dir, "clips.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(out_dir, r["file"])) for r in results.values())
    print(f"共 {len(names)} 段，{total / 1048576:.1f} MB")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("gen", "import"):
        sys.exit(__doc__)
    if sys.argv[1] == "gen":
        gen(sys.argv[2], sys.argv[3:])
    else:
        import_(sys.argv[2])


if __name__ == "__main__":
    main()
