# 大肥鱼飞行棋 🎲🐋

给 DeepSeek 二创形象「鲸鱼娘·大肥鱼」做的**桌宠 + 飞行棋**。

- **棋盘展开**：大肥鱼在透明小棋盘上掷骰子、一格一格蹦过去，踩到格子触发事件
- **棋盘收起**：大肥鱼从当前格子跳回桌面，变回完整的桌宠，可以散步、互动、做表情

![棋盘](docs/screenshot.png)

## 桌宠（棋盘收起时）

保留了 [dafeiyu-pet](https://github.com/1190fasheqi/dafeiyu-pet) 的全部功能：

- **三视图行走**：自由散步 / 跟随鼠标 / 原地待着；左右走用侧面（自动镜像），向上背面、向下正面
- **互动**：拖拽（会侧身朝拖动方向）；单击蹦一下、回嘴，并弹出功能面板（🗨️ 聊天 / 🎲 飞行棋）；双击喂食（小鱼干 / 蛋糕 / 棒棒糖 / 团子 / 钻石）
- **台词**：日常台词、互动回嘴、思维链心声（灰色斜体括号气泡）
- **AI 对话**：调用 DeepSeek API，Key 在右键「设置 Key」里填，存在本地 `config.json`
- **天气**：右键「查看天气」，城市在「设置城市」里改
- **系统监控**：CPU、内存过高时冒泡提醒（Windows 有 NVIDIA 显卡时还会看显卡温度）
- **右键菜单 / 托盘**（macOS 是菜单栏图标）：模式、大小、显示 / 隐藏、回到屏幕内、鼠标穿透、窗口置顶、开机自启、退出

新增：

- **做个表情**：右键「做个表情」，可以选随机或指定表情；闲着时也会偶尔自己做一个
- **动作动画**：搬来了 [dsh-pet](https://github.com/PC2005-cloud/dsh-pet) 的 92 段透明动画（舞狮头、玩玩具汽车、玩魔方、涮火锅、放烟花、撸猫……），
  在「做个表情」里按 小动作 / 互动 / 玩耍 / 吃什么 / 时节 / 文字 分类挑；闲着时也会自己随机播一段（每段 10 秒，拖一下就停）
- 右键菜单补上了「喂食」「说句话」「设置城市」「🎲 打开飞行棋」

### 表情

素材只有正面、侧面、背面三张图，所以表情用「身体动作 + 头顶符号」来表现。共 10 种：

![表情](docs/expressions.png)

开心（蹦跳 + ✨🎵）· 生气（发抖 + 💢）· 害羞（扭捏 + 💗）· 晕乎乎（原地转一圈半 + 💫）· 犯困（歪头 + 💤）·
震惊（跳起 + ❗）· 疑惑（歪头 + ❓）· 得意（鼓起来 + ✨）· 委屈（发抖 + 💧）· 比心（❤️）。
另外还有喂食时的吃东西动作。

### 动作动画

dsh-pet 的动画是同一个大肥鱼形象的完整视频（640×360、24 帧、VP9 透明 webm），放在 `content/clips/`。
播的时候人物按待机动画的身高缩放到桌宠大小、脚底对齐，开头结尾和正面图淡入淡出；
吹气球、放风筝这类比人宽的，桌宠窗口会临时撑大，播完缩回来。
用 [PyAV](https://github.com/PyAV-Org/PyAV) 边播边解码（自带 libvpx，不用另装 ffmpeg），没装 PyAV 时这些动作不出现，其他功能照常。

## 飞行棋（棋盘展开时）

- 默认地图 **中世纪小岛**（大红鹅岛）：按 B 站 UP 主「自由人家的大红鹅」的动森岛建俯瞰图还原，97 格，镜头跟着大肥鱼走。
  主城在正中台地上，四周环河；北边港口、薰衣草田、古城遗迹、螺旋花园；东北紫霓湖和湖心岛；湖与东河之间是陶俑小路；东边女巫森林；南边沙滩和彩虹沙滩；西边社区和田野。
  设计说明（参考视频、借鉴的动森风格、地点事件）见 [docs/medieval-map-design/](docs/medieval-map-design/README.md)
- **三个岔路口**：北门（薰衣草田与港口 / 螺旋花园近路）、左上角港口（沿北岸去古城遗迹 / 往南穿过社区和田野回城）、湖边（过桥上**湖心岛** / 陶俑小路）。走到路口还有步数时停下来，点选项或方向键 + 空格选
- **地点事件**：主城、港口、薰衣草田、古城遗迹、湖心岛、陶俑小路、女巫森林、田野各有一组专属事件（还没想好的格子先放空白格），
  比如女巫借扫帚飞 3 格、遗迹踩到机关退 2 格、港口搭船直接去湖心岛、薰衣草田睡着下回合歇着
- **镜头**：从斜上方看（地图配置里的 `tilt`），建筑、树和角色立着，前后互相遮挡，走进森林就是从树林里穿过去
- **看地图**：拖动地图四处看，滚轮或 +/- 缩放，左下角小地图点一下跳过去；按 C 或点「📍 回到大肥鱼」镜头回来。拖窗口用左上角标题栏
- 建筑、树、石板、地面纹理都是用 Codex 的 image_gen 生成的素材（见下面「美术素材」），建筑挡住大肥鱼时会自动变半透明
- 还有 **环岛日记**（65 格，手绘风小岛）和 **经典外圈**（8×6 方格），右键「换地图」切换；右键「换骰子」换皮肤
- 右下角托盘里点骰子或「掷骰子」按钮（或按空格）：奶油立方骰子按下压缩 → 弹起旋转 → 落地回弹 → 读点数，最终朝前的点数就是本回合步数
- 经过起点发 3 个小鱼干；**问号格**随机做一个表情或动作动画（主城舞狮、田野放风筝、女巫变鸽子、湖心岛放河灯这些地点事件也会播）；补给格 +1 小鱼干；宝箱随机 1~3
- 钓鱼、森林、商店、像素、医院的玩法还没做，现在落地只说一句话，不发奖励；经典地图的恶作剧格下回合暂停
- 点「收起」或按 Esc 收起棋盘，右键菜单里也有；在桌宠上单击后点 🎲，或右键「🎲 打开飞行棋」重新展开
- 棋盘进度（位置、小鱼干、回合）会保存在 `config.json`，下次打开接着玩

## 运行

需要 Python 3.9+。已在 macOS 26（Apple Silicon）+ Python 3.12 / 3.14 上实测；Windows 理论上可以运行，但还没实测。

**macOS 双击启动**：在 Finder 里双击 `启动大肥鱼飞行棋.command`。
第一次会自动建虚拟环境并安装依赖（约 400 MB，视网速要等几分钟），之后就秒开；以后依赖有更新，它也会自动补装。
游戏运行时会开着一个终端窗口，关掉它游戏也会退出。
如果是下载 zip 解压的，系统可能提示"无法验证开发者"：右键这个文件 → 打开 → 再点一次打开即可。

**命令行启动**：

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 文件

| 文件 | 说明 |
|------|------|
| `main.py` | 入口；管理桌宠和棋盘两个窗口的切换、托盘、配置保存 |
| `pet.py` | 桌宠本体（移植自 dafeiyu-pet 的 `桌宠.py`） |
| `board_game.py` | 飞行棋盘窗口：动画、绘制调度、输入 |
| `game/core/` | 纯规则（不依赖 Qt）：地图图结构、骰子、回合与起点工资、存档兼容 |
| `game/content/` | 读取并校验 `content/` 下的配置 |
| `game/render/` | 绘制器：地面层（海、地形、河、道路，分块缓存）、建筑贴图、石板、平面 / 立方骰子 |
| `content/art/<地图>/` | 地图用的贴图和纹理（WebP） |
| `tools/gen_art.sh`、`tools/art_prompts/` | 用 Codex image_gen 批量生成美术原图 |
| `tools/import_art.py` | 把原图裁边、缩放、切图集、做无缝纹理，存进 `content/art/` |
| `content/tiles.toml` | 格子类型：名字、图标、符号、颜色、悬停说明、落地事件 |
| `content/maps/<地图>/map.toml` | 地图：节点、连线、坐标、窗口尺寸、地形、装饰、色板 |
| `content/dice/<皮肤>/dice.toml` | 骰子皮肤：平面或立方、颜色、点位、动画时长，可选贴图 |
| `expressions.py` | 表情动作，桌宠和棋盘共用 |
| `clips.py` | 动作动画播放器（PyAV 解码透明 webm），桌宠和棋盘共用 |
| `content/clips/` | dsh-pet 的动作动画 webm 和 `clips.json`（分类、人物外框） |
| `tools/import_clips.py` | 从 dsh-pet 的 `assets/webm` 导入动作动画，算人物外框、写 `clips.json` |
| `common.py` | 路径、平台差异（字体、窗口标志）、配置、精灵加载 |
| `sprites/` | 精灵图（来自 dafeiyu-pet） |
| `启动大肥鱼飞行棋.command` | macOS 双击启动脚本 |
| `build/大肥鱼.app` | macOS 上启动时自动生成：把解释器放进这个壳里运行，程序坞和 ⌘Tab 就显示「大肥鱼」而不是 Python |

## 换地图 / 换骰子皮肤

- 新地图：复制 `content/maps/island/` 改名后编辑 `map.toml`，重启后右键「换地图」就能选到。
  路线用 `[[road]]` 写：给一串道路控制点和格子类型列表，格子会沿路自动等距排开；
  `from` / `to` 把道路接到别的节点上，多条道路 `from` 同一个节点就是岔路。
  地形 `[[terrain]]` 可用 island / plateau / sand / lake / river / patch，
  建筑和树在 `[sprites]` 里登记贴图，再用 `[[decor]]` 的 `sprite` + `at`（脚底坐标）摆放。
  高的贴图要放在道路北边（y 更小），否则会挡住路上的格子。
- 新骰子：复制 `content/dice/cream/`（立方）或 `content/dice/classic/`（平面）改颜色和时序；
  平面骰子也可以放 `1.png`~`6.png` 并写 `face_dir`。右键「换骰子」选择，「跟随地图」用地图的默认骰子。
- 改完先校验，配置写错时会指出是哪个文件哪一项：

```bash
python -m game.content check
python -m unittest discover -s tests
```

## 美术素材

地图的建筑、树木、石板和地面纹理都由 Codex 内置的 image_gen 生成（走 ChatGPT 订阅，不需要 API key），
清单第一张图生成后作为后续每张的风格锚点，所以一套素材画风统一。重新生成或给新地图出图：

```bash
tools/gen_art.sh tools/art_prompts/island.tsv /tmp/island-raw
python tools/import_art.py /tmp/island-raw content/art/island
```

中世纪小岛模仿《集合啦！动物森友会》的画风：画风描述在 `tools/art_prompts/medieval.style`，脚本会自动读取；
另外要附一张动森截图当风格参考（截图不进仓库，用自己的）：

```bash
STYLE_REF=/path/to/动森截图.png tools/gen_art.sh tools/art_prompts/medieval.tsv /tmp/medieval-raw
```

清单每行是 `名字<TAB>sprite|sheet|texture<TAB>英文描述`，只想重画某几张就在命令末尾写上名字（先删掉旧的原图）。
原图每张 1~2MB 不进仓库，`import_art.py` 会裁掉透明边、缩小并转成 WebP，整套约 3MB。

## 后续计划

1. 每种格子接一个轻量小游戏（钓鱼、接糖果、猜谜……），输了也给安慰小鱼干
2. 心情值 / 装饰兑换
3. 让大肥鱼用 DeepSeek 对掷骰结果吐槽

## 致谢与引用

- **[1190fasheqi/dafeiyu-pet](https://github.com/1190fasheqi/dafeiyu-pet)**（MIT）：大肥鱼透明桌宠。
  - 精灵图（`sprites/`，取自提交 `5b0e018`）直接沿用。
  - `pet.py` 移植自它的 `桌宠.py`，包括台词、散步 / 跟随逻辑、喂食、AI 对话、天气、系统监控、菜单。其中 AI 对话、天气、系统监控由 [Cpanoe](https://github.com/Cpanoe) 贡献给原项目。
  - 在此基础上的改动：macOS 适配（鼠标穿透改用 Qt 自带标志、开机自启改用 LaunchAgent、字体按平台选、窗口不用 Tool 标志）；天气查询改到后台线程；修复了双击后会多触发一次单击的问题；新增表情系统和飞行棋切换。
  - 它的原始许可证保留在 [`LICENSE-dafeiyu-pet`](LICENSE-dafeiyu-pet)。
- **[PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)**：DeepSeek Harness 桌宠。它的代码和素材是分开授权的：
  - 代码 MIT，许可证保留在 [`LICENSE-dsh-pet`](LICENSE-dsh-pet)。本项目只沿用了它 `config.jsonc` 里的随机动作分类（`content/clips/clips.json`）。
  - `content/clips/` 的 92 段动作动画取自它的 `dsh-pet/assets/webm`（提交 `dfc0396`），文件原样未改。**这些动画不适用 MIT**：
    素材允许开源使用、**禁止商用**，角色形象另受 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans) 约束；署名和条款详见 [`content/clips/LICENSE.md`](content/clips/LICENSE.md)。
- 「鲸鱼娘·大肥鱼」是 DeepSeek 社区的二创形象（非 DeepSeek 官方形象），角色形象的权利归原作者 / 相关权利人；
  形象作者声明其适用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans)，作者署名见 [`content/clips/LICENSE.md`](content/clips/LICENSE.md)。
  本项目为非商业同人作品，如需商用请先联系素材作者。
- 格子玩法灵感来自飞行棋和大富翁。
- 界面使用 [PySide6](https://doc.qt.io/qtforpython-6/)（Qt for Python，LGPL）。

## 协议

本项目代码采用 [MIT](LICENSE) 协议；`sprites/` 目录和移植自 dafeiyu-pet 的代码同时沿用上游的 MIT 许可，并受上面的角色形象说明约束。
`content/clips/*.webm` 的动作动画**不在 MIT 范围内**：沿用 dsh-pet 的素材条款（开源可用、禁止商用），角色形象适用 CC BY-NC-SA 4.0，见 [`content/clips/LICENSE.md`](content/clips/LICENSE.md)。
