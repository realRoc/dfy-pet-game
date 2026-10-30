# 健身跟练素材

## 训练计划

桌宠右键「🏋️ 跟练」（或单击面板的 🏋️）里列出的计划来自两处：

- `content/workout/plans/*.json`：内置，目前只有 Kris（THENX）的 [6 分钟腿部训练（不跳）](https://www.bilibili.com/video/BV17Z4y1M7YV/)
- 仓库根目录的 `workouts/*.json`：自己写的，菜单里「打开计划文件夹…」会建好这个目录并放一份示例；和内置的同名时用自己写的

格式：

```json
{
  "name": "菜单里显示的名字",
  "rest": 15,          // 每个动作后休息几秒（默认 15），单步可以用 "rest" 覆盖，0 就是紧接着下一个
  "round_rest": 45,    // 多轮时轮与轮之间休息几秒（默认 30）
  "rounds": 1,         // 默认练几轮，菜单「轮数」可以临时改
  "steps": [
    {"move": "squat_open_close", "secs": 45},
    {"move": "curtsy_lunge", "secs": 22, "side": "right", "rest": 0},
    {"move": "curtsy_lunge", "secs": 22, "side": "left"},
    {"move": "collapse", "secs": 10, "label": "躺平一下"}
  ]
}
```

`side` 是 `left` / `right`，会显示成「（左）」「（右）」，左边的画面是镜像的。`label` 可以改动作在气泡和语音里的名字。

### 可用的动作（move）

| move | 名字 | 说明 |
| --- | --- | --- |
| `squat_open_close` | 开合深蹲 | 宽站距、窄站距交替 |
| `squat` | 深蹲 | |
| `curtsy_lunge` | 屈膝礼弓步 | 女仆屈膝礼，其实是弓步蹲 |
| `lunge` | 弓步蹲 | 左右交替 |
| `deadlift` | 硬拉 | 没哑铃就拎电饭煲 |
| `glute_bridge` | 臀桥 | |
| `glute_bridge_single` | 单腿臀桥 | 配 `side` |
| `wall_sit` | 靠墙静蹲 | 越到后面抖得越厉害 |
| `tired` | 累了 | 大肥鱼人设动作：弯腰大喘气 |
| `collapse` | 瘫倒 | 趴地上，魂飞出来 |
| `slack` | 偷懒干饭 | 盘腿干一碗白饭 |
| `lazy_squat` | 假装在练 | 半蹲刷手机 |
| `drink` | 喝水 | 休息时默认就是它 |
| `cheer` | 欢呼 | 练完时用 |
| `stand` | 站好 | |

跟练时大肥鱼自己也会用人设动作：休息开头先弯腰喘一会儿再喝水，暂停时喘气，最后 10 秒冒汗，
20 秒以上的站着练的动作有一半机会中途偷懒一次然后「被发现了！」——只是她偷懒，计时照走；
不想看可以在菜单里关掉「大肥鱼会偷懒」。练完先欢呼再瘫倒。

## 跟练动画

`characters/dafeiyu/workout/clips/` 里每段是一个透明 webm（VP9 + alpha），`clips.json` 记着每段在原画面里的位置和帧数，由
[`tools/make_workout_clips.py`](../../tools/make_workout_clips.py) 生成：

1. **生成**：TeamoRouter 的 Seedance 2.5 图生视频（`seedance-2-5-image-to-video-basic`，720p，1:1），首尾帧模式。
   首帧、尾帧都是同一张「中立图」——角色包的正面立绘（大肥鱼是 `characters/dafeiyu/sprites/正面.png`）原样放大贴在纯绿幕上——所以每段都从原版站姿开始、
   回到原版站姿：中立 → 动作 / 表情 → 中立。角色就是原图动起来，不让模型重画。
   提示词是统一的前缀（固定机位、纯绿幕、保持参考图的 Q 版二头身和服装、动作软萌 Q 弹）加每段按秒分解的动作描述，
   都写在脚本的 `SPECS` 里。
2. **躺着 / 蹲着练的**拆三段：进入（站姿 → 仰躺屈膝 / 靠墙半蹲，不给尾帧）、循环（首尾帧都是进入那段的最后一帧）、
   起身（从那一帧回到站姿）。两种臀桥共用一个躺姿，接着练不用起身。
3. **抠像**：色差抠像（绿色比红蓝多出多少就透明多少），再从半透明像素里减掉绿幕颜色还原前景色——鬼魂、发光、
   鼻涕泡这些半透明的地方不会变成灰黑的雾；裁到整段人物外框的并集，转 VP9 + alpha。

```bash
export TEAMOROUTER_API_KEY=...
python tools/make_workout_clips.py gen  <工作目录> [名字 ...]   # 已经生成过的跳过；一段 4~8 秒，排队时一段要十几分钟
python tools/make_workout_clips.py import <工作目录>
```

播放（`workout.py` 的 `ClipDirector`）：一段播完才挑下一段，这时她一定在站姿（或者躺姿、静蹲姿势）上，所以：
换动作、去休息、偷懒、练完欢呼都在站姿上接；要躺下练先播进入那段，接下来不躺着了先播起身那段；
偷懒到点了也要等手上这一下练完。片段之间（准备、喝完水还没到点）画平时的正面图，只轻轻呼吸不摇晃，和首尾帧对得上。
左边的动作把站着练的片段镜像；躺着的循环段不镜像（翻过来就和进入那段接不上了）。

| 片段 | 内容 |
| --- | --- |
| `squat` `squat_open_close` `curtsy_lunge` `lunge` `deadlift` | 站着练，每段做一两次 |
| `bridge_enter` `bridge_loop` `bridge_single_loop` `bridge_exit` | 躺下 / 臀桥 / 单腿臀桥 / 起身 |
| `wall_sit_enter` `wall_sit_loop` `wall_sit_exit` | 靠墙蹲下 / 坚持发抖 / 站起来 |
| `tired` `drink` `cheer` `collapse` | 喘气、喝水、欢呼、瘫倒（魂飞出来又钻回去，再爬起来） |
| `lazy_doze` `lazy_phone` `lazy_rice` `lazy_think` `lazy_flop` `lazy_fish` `lazy_fake` `lazy_tailnap` | 偷懒：打瞌睡吹鼻涕泡、刷手机、干白饭、深度思考、躺平、偷吃小鱼干、假装在练、抱尾巴打盹 |

没装 PyAV、素材缺段或者解码出错时，退回下面的姿势帧。

macOS 上会用系统的提示音（最后 3 秒滴答、开始、休息、完成）和婷婷的语音报「开始，xxx」「休息 15 秒，下一个，xxx」，
菜单里可以关掉语音；Windows 只有提示音。

## 姿势帧

（旧的一套，没装 PyAV 时用。）`characters/dafeiyu/workout/frames/` 里每张图是一个姿势，`frames.json` 记着脚底锚点和缩放基准，由
[`tools/make_workout_frames.py`](../../tools/make_workout_frames.py) 从原图生成。

原图是用 ChatGPT 的图片生成（Codex CLI 的 `image_gen`）画的，全部照着正面立绘的 Q 版比例：
大约 2.5 头身、头占身高四成、小短腿。提示词是统一的前缀加每个姿势的描述：

> Draw the SAME character in the SAME art style as the reference: a super-deformed Q-version chibi whale-girl maid,
> about 2.5 heads tall — a huge head (roughly 40% of her total height), a small round body, and VERY SHORT, STUBBY
> little legs … (do NOT make the legs long or the body slender) … She wears navy shorts under the dress; the dress
> always modestly covers her. Pose: *<姿势描述>*. … Fully transparent background, no floor, no shadow, no text.

姿势描述举例：`squat_wide` 是宽距深蹲、裙摆盖住大腿和膝盖；`curtsy` 是两手提裙摆的女仆屈膝礼；
`hinge` / `lift` 是侧身拎着一个白色小电饭煲做硬拉。中间姿势（`squat_wide_half`、`squat_narrow_half`、`lunge_half`）
是拿对应的「蹲到底」那张当参考，让它画同一个动作的半程。

## 动画

每个动作是 `workout.py` 里的一条关键帧时间轴（`Key`），思路借鉴火纹战斗动画，只是动作都小：

- **关键帧**：站好、蹲到底这类 pose 停得最久，节奏靠它们在时间轴上的位置
- **过渡帧**：半蹲这类中间姿势一闪而过（0.1~0.16 秒），往下坐越来越快，站起来更快
- **蓄力帧**：下蹲前微微挺高吸口气、跳之前先压低、硬拉前收紧
- **模糊帧**：最快那一拍带上一张图的残影

换姿势默认硬切（叠化会让人变半透明），只有正面 ↔ 侧面这种没有中间帧的才叠化一两帧。
落到新姿势时压一下再弹两下（衣裙头发的余震），停着时有呼吸、咽水、嚼饭、发抖、偶尔腿软往下滑这些小起伏。

加新动作：画好透明 PNG（文件名 = 帧名），在 `tools/make_workout_frames.py` 的 `POSES` 里写上这个姿势相对站直有多高，
跑 `python tools/make_workout_frames.py <原图目录>`，再在 `workout.py` 的 `MOVES` 里加一条。

## 授权

跟练动画和姿势帧（在 `characters/dafeiyu/workout/` 里）都是「大肥鱼」形象的衍生图，适用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans)
（署名、非商业、相同方式共享），**不在本仓库代码的 MIT 范围内**。形象署名见 [`characters/dafeiyu/clips/LICENSE.md`](../../characters/dafeiyu/clips/LICENSE.md)：
社区二创的 DeepSeek「大肥鱼」，非 DeepSeek 官方形象；原型「溟月」出自 B 站 @上善无形，DeepSeek 版（女仆鲸鱼娘）设计出自 B 站 @ZipZipPipe。

Kris 那套动作的编排参考 THENX（Chris Heria）的视频，这里只记了动作名和时长，没有用视频里的画面或声音。
