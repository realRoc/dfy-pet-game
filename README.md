# 大肥鱼飞行棋 🎲🐋

给 DeepSeek 二创形象「鲸鱼娘·大肥鱼」做的桌宠飞行棋 **原型**：
透明置顶的小棋盘，掷骰子后大肥鱼一格一格蹦过去，落地触发格子事件。

![screenshot](docs/screenshot.png)

## 现在有什么

- **棋盘**：8×6 外圈共 24 格，起点 / 钓鱼 / 套圈 / 接糖果 / 猜谜 / 宝箱 / 休息 / 恶作剧
- **骰子**：点击骰子或按空格，滚动约 0.8 秒后定格，再弹一下
- **逐格跳动**：抛物线小跳 + 落地挤压 + 影子缩放；按前进方向切三视图
  （向右走时侧面图镜像，向上背面、向下正面），转向时交叉淡化
- **格子事件**：落地说句话、加小鱼干；经过起点发 3 个小鱼干；恶作剧格下回合暂停
- **桌宠窗口**：无边框、透明、置顶；拖动空白处移动，右键菜单（掷骰子 / 重新开始 / 退出），Esc 退出

各格子的小游戏还没做，目前只有台词和奖励。

## 运行

需要 Python 3.10+，macOS / Windows 都可以。

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python board_game.py
```

## 后续计划

1. 每种格子接一个轻量小游戏（钓鱼、接糖果、猜谜……），输了也给安慰小鱼干
2. 心情值 / 装饰兑换
3. 接 DeepSeek API，让大肥鱼对掷骰结果吐槽
4. 和桌宠本体合并：平时在桌面散步，点一下展开棋盘

## 致谢与引用

- **[1190fasheqi/dafeiyu-pet](https://github.com/1190fasheqi/dafeiyu-pet)**（MIT）：大肥鱼透明桌宠。
  本项目直接使用了它的精灵图（`sprites/`，取自提交 `5b0e018`）。三视图按方向切换、
  侧面镜像、呼吸 / 摇摆 / 转向淡化的画法也参考了它的 `桌宠.py`。
  它的原始许可证保留在 [`LICENSE-dafeiyu-pet`](LICENSE-dafeiyu-pet)。
- 「鲸鱼娘·大肥鱼」是 DeepSeek 社区的二创形象，角色形象的权利归原作者 / 相关权利人。
  本项目为非商业同人作品，如需商用请先联系素材作者。
- 格子玩法灵感来自飞行棋和大富翁。
- 界面使用 [PySide6](https://doc.qt.io/qtforpython-6/)（Qt for Python，LGPL）。

## 协议

本项目代码采用 [MIT](LICENSE) 协议；`sprites/` 目录沿用上游 dafeiyu-pet 的 MIT 许可，并受上面的角色形象说明约束。
