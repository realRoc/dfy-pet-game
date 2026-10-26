# 大肥鱼 🐋

给 DeepSeek 二创形象「鲸鱼娘·大肥鱼」做的**桌面宠物**，外加一个独立的网页爬塔游戏。

- **桌宠**（仓库根目录，Python + PySide6）：在桌面上散步、互动、做表情、播动作动画
- **爬塔战斗原型**（[`tower/`](tower/README.md)，网页游戏）：仿《杀戮尖塔》的像素卡牌 roguelike，在浏览器里玩

之前的飞行棋已经移除，最后一个完整版本留在标签 `flying-chess-archive` 上（`git checkout flying-chess-archive`）。

## 桌宠

保留了 [dafeiyu-pet](https://github.com/1190fasheqi/dafeiyu-pet) 的全部功能：

- **三视图行走**：自由散步 / 跟随鼠标 / 原地待着；左右走用侧面（自动镜像），向上背面、向下正面
- **互动**：拖拽（会侧身朝拖动方向）；单击蹦一下、回嘴，并弹出功能面板（🗨️ 聊天）；双击喂食（小鱼干 / 蛋糕 / 棒棒糖 / 团子 / 钻石）
- **台词**：日常台词、互动回嘴、思维链心声（灰色斜体括号气泡）
- **AI 对话**：调用 DeepSeek API，Key 在右键「设置 Key」里填，存在本地 `config.json`
- **天气**：右键「查看天气」，城市在「设置城市」里改
- **系统监控**：CPU、内存过高时冒泡提醒（Windows 有 NVIDIA 显卡时还会看显卡温度）
- **右键菜单 / 托盘**（macOS 是菜单栏图标）：模式、大小、显示 / 隐藏、回到屏幕内、鼠标穿透、窗口置顶、开机自启、退出

新增：

- **做个表情**：右键「做个表情」，可以选随机或指定表情；闲着时也会偶尔自己做一个
- **动作动画**：搬来了 [dsh-pet](https://github.com/PC2005-cloud/dsh-pet) 的 92 段透明动画（舞狮头、玩玩具汽车、玩魔方、涮火锅、放烟花、撸猫……），
  在「做个表情」里按 小动作 / 互动 / 玩耍 / 吃什么 / 时节 / 文字 分类挑；闲着时也会自己随机播一段（每段 10 秒，拖一下就停）
- 右键菜单补上了「喂食」「说句话」「设置城市」

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

## 运行

桌宠需要 Python 3.9+。已在 macOS 26（Apple Silicon）+ Python 3.12 / 3.14 上实测；Windows 理论上可以运行，但还没实测。

**macOS 双击启动**：在 Finder 里双击 `启动大肥鱼.command`。
第一次会自动建虚拟环境并安装依赖（约 400 MB，视网速要等几分钟），之后就秒开；以后依赖有更新，它也会自动补装。
桌宠运行时会开着一个终端窗口，关掉它桌宠也会退出。
如果是下载 zip 解压的，系统可能提示"无法验证开发者"：右键这个文件 → 打开 → 再点一次打开即可。

**命令行启动**：

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**爬塔**：`cd tower && npm install && npm run dev`，浏览器打开 http://localhost:5173，详见 [tower/README.md](tower/README.md)。

## 文件

| 文件 | 说明 |
|------|------|
| `main.py` | 入口；托盘、配置保存 |
| `pet.py` | 桌宠本体（移植自 dafeiyu-pet 的 `桌宠.py`） |
| `expressions.py` | 表情动作 |
| `clips.py` | 动作动画播放器（PyAV 解码透明 webm） |
| `content/clips/` | dsh-pet 的动作动画 webm 和 `clips.json`（分类、人物外框） |
| `tools/import_clips.py` | 从 dsh-pet 的 `assets/webm` 导入动作动画，算人物外框、写 `clips.json` |
| `common.py` | 路径、平台差异（字体、窗口标志）、配置、精灵加载 |
| `sprites/` | 精灵图（来自 dafeiyu-pet） |
| `启动大肥鱼.command` | macOS 双击启动脚本 |
| `tower/` | 爬塔战斗原型（Vite + TypeScript），和桌宠不共用代码，见 [tower/README.md](tower/README.md) |
| `build/大肥鱼.app` | macOS 上启动时自动生成：把解释器放进这个壳里运行，程序坞和 ⌘Tab 就显示「大肥鱼」而不是 Python |

## 致谢与引用

- **[1190fasheqi/dafeiyu-pet](https://github.com/1190fasheqi/dafeiyu-pet)**（MIT）：大肥鱼透明桌宠。
  - 精灵图（`sprites/`，取自提交 `5b0e018`）直接沿用。
  - `pet.py` 移植自它的 `桌宠.py`，包括台词、散步 / 跟随逻辑、喂食、AI 对话、天气、系统监控、菜单。其中 AI 对话、天气、系统监控由 [Cpanoe](https://github.com/Cpanoe) 贡献给原项目。
  - 在此基础上的改动：macOS 适配（鼠标穿透改用 Qt 自带标志、开机自启改用 LaunchAgent、字体按平台选、窗口不用 Tool 标志）；天气查询改到后台线程；修复了双击后会多触发一次单击的问题；新增表情系统。
  - 它的原始许可证保留在 [`LICENSE-dafeiyu-pet`](LICENSE-dafeiyu-pet)。
- **[PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)**：DeepSeek Harness 桌宠。它的代码和素材是分开授权的：
  - 代码 MIT，许可证保留在 [`LICENSE-dsh-pet`](LICENSE-dsh-pet)。本项目只沿用了它 `config.jsonc` 里的随机动作分类（`content/clips/clips.json`）。
  - `content/clips/` 的 92 段动作动画取自它的 `dsh-pet/assets/webm`（提交 `dfc0396`），文件原样未改。**这些动画不适用 MIT**：
    素材允许开源使用、**禁止商用**，角色形象另受 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans) 约束；署名和条款详见 [`content/clips/LICENSE.md`](content/clips/LICENSE.md)。
- 「鲸鱼娘·大肥鱼」是 DeepSeek 社区的二创形象（非 DeepSeek 官方形象），角色形象的权利归原作者 / 相关权利人；
  形象作者声明其适用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans)，作者署名见 [`content/clips/LICENSE.md`](content/clips/LICENSE.md)。
  本项目为非商业同人作品，如需商用请先联系素材作者。
- 界面使用 [PySide6](https://doc.qt.io/qtforpython-6/)（Qt for Python，LGPL）。

## 协议

本项目代码采用 [MIT](LICENSE) 协议；`sprites/` 目录和移植自 dafeiyu-pet 的代码同时沿用上游的 MIT 许可，并受上面的角色形象说明约束。
`content/clips/*.webm` 的动作动画**不在 MIT 范围内**：沿用 dsh-pet 的素材条款（开源可用、禁止商用），角色形象适用 CC BY-NC-SA 4.0，见 [`content/clips/LICENSE.md`](content/clips/LICENSE.md)。
