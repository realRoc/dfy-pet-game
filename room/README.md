# 后宅

桌宠的房间：一个 8×8 的等距视角小屋，摆家具、换墙纸地板、凑套装。舒适度越高，桌面上的角色闲着时越常做开心的表情；
角色也会住进来，在房间里走来走去，走到家具上坐着、躺着、睡觉、看书、锻炼、喝水。

家具都是免费的，没有货币。

## 怎么打开

桌宠单击面板里的 🏠，或者右键「🏠 后宅」。桌宠在 127.0.0.1 上起一个小服务，用系统浏览器打开这个网页。

```
桌宠（Python）                                    网页（这个目录，打包成 content/room/index.html）
  room.RoomStore   ← room.json（布局存档）
  room.RoomAPI     catalog() / state() / put_layout()
  room.RoomServer  127.0.0.1:随机端口  ⇄  HTTP  ⇄  src/api.ts → src/main.ts（Pixi 画房间、编辑）
```

数据都在桌宠那边：网页每改一次就把整份布局发回去，`room.py` 校验（不出界、不重叠）、算舒适度、写盘，网页这边的同一套规则只是用来预判（红绿格子）。

## 操作

- 左边点家具 → 鼠标移到房间里 → 左键放下；R 旋转，右键或 Esc 取消
- 点房间里的家具：移动 / 旋转（R）/ 收起（Delete）
- 墙纸、地板在左边的标签页里换
- 右上角是舒适度、等级和三个套装的进度，鼠标停在没集齐的套装上能看到还差什么

## 家具目录

[`content/room/catalog.json`](../content/room/catalog.json)：

| 字段 | 说明 |
| --- | --- |
| `room` | 房间多少格 |
| `poses` | **官方姿势库**：sit 坐、lie 躺、sleep 睡、read 看书、exercise 锻炼、drink 喝水。角色的姿势动画按这个库做 |
| `items[].size` | 占地（格），`layer` 是 `object`（家具，互相不能叠）或 `rug`（地毯，可以垫在家具下面） |
| `items[].boxes` | 怎么画：一组等距长方体 `{at: [x, y, z], size: [宽, 深, 高], color}`，单位是格 |
| `items[].slots` | 姿势槽位：`{pose, at: [x, y], z?}`，角色站 / 坐 / 躺在这个点上做这个姿势。家具只能挂姿势库里有的姿势 |
| `items[].comfort` `stack` | 舒适度；同一件摆多份只算前 `stack` 份（默认 1） |
| `items[].set` / `sets` | 套装：每件都摆上了加 `bonus` |
| `comfort_levels` | 舒适度等级（空荡荡 → 超温馨），等级决定桌宠心情加成 |
| `wallpapers` `floors` | 墙纸、地板 |

家具全是代码画的原创图（`license.commercial: true`），商业版可以直接带。以后换成美术画的图时，在家具上加图片字段、
网页里换画法即可，`size`、`slots`、`comfort` 这些不用动。

**姿势槽位**是家具和角色之间唯一的约定：家具只说「这里能坐」，不带任何角色动画。角色包现在还没有房间里的姿势动画，
`src/resident.ts` 用立绘加变换代替（坐 = 压扁一点，躺 / 睡 = 转过来平放，再加 💤 📖 💪 💧 这些符号）。
以后角色包里加上 sit / lie / … 的片段，只换 `Resident` 的画法，家具一件都不用改；UGC 家具也只能挂这些标准槽位。

## 开发

```bash
npm install
npm test           # 几何、旋转、摆放规则（vitest）
npm run release    # 类型检查 + 打包，复制到 ../content/room/ 并写 SOURCE_HASH；改完代码记得跑一次再提交
```

本地调网页：先起桌宠、打开一次后宅，记下浏览器地址里的端口和 `t=`，然后

```bash
ROOM_API=http://127.0.0.1:<端口> npm run dev    # 打开 http://localhost:5173/?t=<token>
```

`content/room/SOURCE_HASH` 记着打包时的源码哈希，`tests/test_room.py` 会比对，CI 也会重新打包一次确认一致。

## 迁到 Electron

网页本身不用改。要换的只有传输：

- `src/api.ts` 的三个调用换成 `ipcRenderer.invoke('room:catalog' | 'room:state' | 'room:putLayout')`；
- 主进程里实现同样三个处理函数：把 `room.py` 的 `validate_layout` / `comfort` / 存档翻成 TS（规则和 `src/model.ts` 已经是一份），
  或者先让主进程转发给 Python 子进程；
- 角色立绘从 `/character/<view>.png` 换成 `app://` 协议或打包进资源目录。
