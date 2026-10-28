# 喝水提醒素材

`clips/` 里每段是一个透明 webm（VP9 + alpha），`clips.json` 记着每段在原画面里的位置和帧数，由
[`tools/make_water_clips.py`](../../tools/make_water_clips.py) 生成。生成和抠像和跟练动画是同一套
（[`content/workout/README.md`](../workout/README.md#跟练动画)）：TeamoRouter 的 Seedance 2.5 图生视频，首尾帧模式，
绿幕色差抠像。

| 片段 | 首帧 → 尾帧 | 内容 |
| --- | --- | --- |
| `water_offer` `water_offer_b` `water_offer_b2` | 正面 → 正面 | 到点：递水壶晃一晃 / 像拍广告一样推荐喝水（同一段提示词留了两版，随机挑） |
| `water_knock` | 正面 → 正面 | +10 分钟：隔着屏幕敲玻璃，搬出一瓶 1.5L 大水 |
| `water_throw` | 正面 → 正面 | +15 分钟：拖出比她还高的大水朝镜头扔过来（约 3.9 秒飞到镜头前，见 `water.THROW_AT`），叉腰哼 |
| `water_leave` | 正面 → **侧面** | 气鼓鼓转身，停在侧面站姿，接着用平时的侧面图走出屏幕 |
| `water_return_sulk` | **侧面** → 正面 | 回来时你还没喝：别别扭扭把水递过来又收回去 |
| `water_return_makeup` | **侧面** → 正面 | 回来时你喝了：挠头、比心 |
| `water_cheers` | 正面 → 正面 | 喝了：干杯，头顶喷出小水柱挂彩虹 |

「侧面」是 `sprites/侧面.png` 按和正面图一样的大小、脚底位置贴绿幕（脸朝左）；往右边跑 / 从左边回来时整段镜像。
+5 分钟的「示范喝水」直接用跟练动画的 `drink`。

扔过来的大水、碎屏、水花是 `water.py` 里用代码画的（`ShatterOverlay`），不是素材。

```bash
export TEAMOROUTER_API_KEY=...
python tools/make_water_clips.py gen  <工作目录> [名字 ...]   # 已经生成过的跳过
python tools/make_water_clips.py import <工作目录>
```

## 授权

这些动画是「大肥鱼」形象的衍生图，适用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh-hans)
（署名、非商业、相同方式共享），**不在本仓库代码的 MIT 范围内**。形象署名见 [`content/clips/LICENSE.md`](../clips/LICENSE.md)。
