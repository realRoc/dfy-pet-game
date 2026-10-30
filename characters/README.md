# 角色包

桌宠的引擎（散步、表情动作、动作动画播放、跟练、喝水提醒、聊天）和角色是分开的：一个角色的立绘、动画、台词、人设和授权
都放在 `characters/<id>/` 里，由 `character.json` 描述。换角色只换包，不改代码。

用哪个包看环境变量 `DFY_CHARACTER`：填包名（`characters/` 下的目录名）或包目录的绝对路径，不设就是 `dafeiyu`。

```bash
DFY_CHARACTER=my_char python main.py
```

| 包 | 说明 | 商用 |
| --- | --- | --- |
| [`dafeiyu/`](dafeiyu/) | 大肥鱼，功能最全的参考包 | ❌ 见 [`dafeiyu/LICENSE.md`](dafeiyu/LICENSE.md) |

## 目录

```
characters/<id>/
├── character.json        清单（下面）
├── LICENSE.md            授权和署名
├── sprites/              三视图立绘 + 图标（透明 PNG）
├── clips/                动作动画：clips.json + 透明 webm（tools/import_clips.py 的格式）
├── workout/clips/        跟练动画：clips.json + 透明 webm（tools/make_workout_clips.py）
├── workout/frames/       跟练姿势帧：frames.json + PNG（tools/make_workout_frames.py），没装 PyAV 时用
└── water/clips/          喝水提醒动画：clips.json + 透明 webm（tools/make_water_clips.py）
```

目录名和位置都由清单决定，上面只是大肥鱼包的放法。

## character.json

```jsonc
{
  "format": 1,                       // 清单格式版本，引擎目前只认 1
  "id": "dafeiyu",                   // 和目录名一致
  "name": "大肥鱼",                  // 显示名：托盘、程序坞、窗口标题、菜单里的「单击 xx 也行」
  "license": {
    "spdx": "CC-BY-NC-SA-4.0",       // 或 LicenseRef-xxx
    "commercial": false,             // 能不能用在商业版里，商业版打包时只收 true 的包
    "attribution": ["..."],          // 署名，一条一行
    "notes": "LICENSE.md"            // 详细条款
  },
  "sprites": {
    "height": 340,                   // 立绘原图高度（像素），桌宠大小按它缩放
    "front": "sprites/正面.png",     // 正面：站着、向下走、所有动画的首尾帧
    "side": "sprites/侧面.png",      // 侧面：左右走
    "back": "sprites/背面.png",      // 背面：向上走
    "side_faces": "left",            // 侧面图脸朝哪边；right 时引擎加载时翻过来
    "icon": "sprites/icon.png"       // 托盘 / 程序坞图标
  },
  "animations": {                    // 都可以不写，缺哪类哪类功能降级（下面）
    "actions": "clips",
    "workout": "workout/clips",
    "workout_frames": "workout/frames",
    "water": "water/clips"
  },
  "timing": {
    "water_throw_at": 3.9            // water_throw 片段里水瓶飞到镜头前的秒数（碎屏的时刻）
  },
  "persona": {
    "chat_system": "你是桌面宠物……", // AI 聊天的系统提示词
    "chat_placeholder": "给大肥鱼发送消息",
    "im_system": "你是……",          // 可选：QQ / Discord 机器人（im/）用的人设，写「通过 QQ 和大家聊天」，换平台时自动替换；
                                     // 不写就用 cordis.patch.yml 里 dfy-qq preset 的人设
    "self": "本鲸"                   // 自称（给以后的模板台词用）
  },
  "lines": { ... }                   // 台词，下面
}
```

必需字段：`format id name license.{spdx,commercial,attribution} sprites.{height,front,side,back,side_faces,icon}
persona.chat_system`。`character.validate()` 会检查这些字段和清单里引用的每个文件，
`tests/test_character.py` 对 `characters/` 下所有包跑一遍。

### 台词 lines

缺哪类就用引擎的默认台词（很素，只保证不报错），`validate()` 会给出提醒。

| 键 | 类型 | 用在哪 |
| --- | --- | --- |
| `idle` | 字符串数组 | 闲着时自己说的话、右键「说句话」 |
| `react` | 字符串数组 | 单击回嘴 |
| `inner` | 字符串数组 | 思维链心声（灰色斜体括号气泡） |
| `drag` | 字符串数组 | 被拖起来放下 |
| `food` | `{emoji: [台词]}` | 喂食，emoji 是 🐟 🍰 🍭 🍡 💎 |
| `system` | `{cpu, memory, gpu_hot}` | 系统监控提醒 |
| `expressions` | `{表情键: [台词]}` | 表情：happy angry shy dizzy sleepy shocked confused smug cry love thirsty |
| `water` | `{级别: [台词]}` | 喝水提醒。`1`–`4` 是四级提醒（`1` 里可以用 `{m}` 分钟数），另有 `welcome leave away_drank busy sulk makeup cheers goal late cold cold_end cold_badge snooze`；`cheers` / `goal` 可以用 `{n}` `{goal}`；`busy` 两句分别是托盘提示和「叫她回来」的回复 |
| `workout.cues` | `{动作键: 台词}` | 每个跟练动作开始时说的话（括号包起来就是心声），动作键见 `content/workout/README.md` |
| `workout.slack` `caught` `last` `rest` | 字符串数组 | 偷懒心声、被发现、最后 10 秒、休息（`rest` 可以用 `{s}` `{next}`） |
| `workout.lazy` | `{片段名: {thought, caught, caught_at}}` | 偷懒片段：开始时的心声、被发现时说的话、片段第几秒被发现。片段名必须是 `workout/clips` 里有的 |

## 动画约定

动画都是「中立 → 动作 → 中立」：首帧尾帧就是 `front` 立绘原样贴绿幕，所以动作之间、动作和平时的立绘之间怎么接都不跳。
生成和抠像的流程见 [`content/workout/README.md`](../content/workout/README.md#跟练动画)，提示词在 `tools/make_*_clips.py` 里
（提示词描述的是大肥鱼，换角色要改）。工具脚本也按 `DFY_CHARACTER` 把产物写进当前包。

引擎按名字找片段，下面这些名字是约定：

| 类别 | 必须有的片段 | 缺了怎么办 |
| --- | --- | --- |
| `actions` | 随便，`clips.json` 的 `categories` 决定菜单分类；`ref` 是待机那段的人物外框 | 「做个表情」里没有动作动画，闲着只做表情 |
| `workout` | `squat squat_open_close curtsy_lunge lunge deadlift bridge_enter bridge_loop bridge_single_loop bridge_exit wall_sit_enter wall_sit_loop wall_sit_exit tired drink cheer collapse lazy_rice lazy_fake` + `lines.workout.lazy` 里的每段 | 缺任何一段就整套不用，退回姿势帧 |
| `workout_frames` | `content/workout/README.md` 里 MOVES 用到的每个帧名 | 姿势帧也没有：跟练菜单显示「素材缺失」 |
| `water` | `water_offer`（`_b` `_b2` 可选）`water_knock water_throw water_leave water_return_sulk water_return_makeup water_cheers`；「示范喝水」用 `workout` 的 `drink` | 缺的那段换成表情，流程照走 |

`water_leave` 停在侧面站姿，`water_return_*` 从侧面站姿开始，侧面朝向要和 `side_faces` 一致。

## 做一个新角色

1. 画三视图（正面、侧面、背面）和图标，透明 PNG，三张同高、脚底对齐。**商用的角色要签著作权转让或独占授权**。
2. 建 `characters/<id>/character.json`，`license.commercial` 按合同写。
3. 先只放立绘跑起来（`DFY_CHARACTER=<id> python main.py`）：散步、表情、喂食、聊天、喝水提醒（用表情代替动画）都能用。
4. 用 `tools/make_workout_clips.py`、`tools/make_water_clips.py` 生成动画（改提示词里的角色描述），再补台词。
5. `python -m unittest tests.test_character` 检查清单。
