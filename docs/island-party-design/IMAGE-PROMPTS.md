# GPT Image 参考图生成记录

生成日期：2026-10-25。使用 Codex 内置 GPT Image，通过 imagegen 技能的 built-in 模式生成，没有使用外部 CLI 或 API key。

这些图片是美术与交互参考，不是运行时完整背景或可直接切分的精灵图集。图片中的路线、图标和按钮是概念表达；精确规则以 CLAUDE-PROMPT.md 为准。正式素材需按图层、摄像机与锚点重新制作；正式文字与骰子点数由代码绘制。

前两张以用户提供的原型截图作为角色参考；第三张按同一材质方向独立生成。三张最终图已复制到本目录 references/。

## 01-island-board

文件：references/01-island-board.png

```text
Use case: ui-mockup
Asset type: polished game art-direction reference, wide desktop game screen, 1536x1024 landscape.
Primary request: Reimagine the attached extremely plain board-game screenshot as an original adorable Chinese desktop pet adventure-party board game called “大肥鱼环岛日记”. The screenshot is a character identity reference ONLY, not a layout to preserve. Keep the same tiny chibi blue-haired whale-maid companion: blue hair, small whale-tail side ornaments, navy-and-white maid dress, round face. This is a new original island scene.
Style: premium hand-painted 2.5D toy diorama, orthographic elevated three-quarter camera, soft rounded geometry, coherent painterly edges, tactile ceramic stepping stones, restrained lovely blue/cream/seafoam palette with peach accents. Beautiful cozy indie game screenshot, readable playable board rather than wallpaper.
Composition: Map fills 80 percent of screen, no big empty center. A SINGLE continuous winding roughly 28-space loop follows natural terrain around a compact whale-shaped island, with one clear short alternate path across a small wooden bridge. Flat stone spaces are large, spaced, readable, carry one embossed pictogram each, arrows show direction. Foreground start is a tiny seaside cottage and mailbox, left side an azure fishing lake and wooden fishing pier exactly adjacent to a fishing tile, upper left a shady mushroom forest with chests, upper right a small whimsical lavender voxel meadow of blocky trees and one vivid pixel-event tile, right lower side a small cream clinic marked with a teal medical bag pictogram next to a clinic tile, lower center a little market stall with fish snacks. Important readable route and miniature terrain changes, gentle cliffs, bridge, water reflections, flower patches, no decorative clutter blocking spaces. Chibi whale-maid stands visibly on one foreground stone with soft ground shadow. Small arrow marker over her, no additional human characters.
UI: slim cream top bar, title “大肥鱼环岛日记” left, fish-snack icon + “12” right, “第 8 回合”. Upper left small three-slot travel-stamp card. Bottom floating cream control tray contains small item slots on left, a large beautiful ivory-and-navy three-quarter-view physical cube die with round indented pips near right and a navy primary action button “掷骰子”. Small in-world route preview dots. Text is minimal, clear and correctly typeset, never label every tile. Slight translucent HUD, ample breathing room. All text and icons crisp.
Materials: milky white ceramic die with blue recessed circular pips, subtle bevel, convincing contact shadow, island turf is soft textured green, clear blue water with lily pads. Gentle sunlight from top left.
Avoid: Mario characters, pipes, question-mark blocks, copyrighted Mario set pieces, screenshot's rectangular emoji grid, giant blank central area, aggressive neon, glossy mobile casino UI, photorealism, tiny unreadable multi-line text, giant dice occluding map, watermark.
This is a concept image only; route counts are illustrative, implementation will use a separate deterministic map.
```

## 02-fishing-and-pixel

文件：references/02-fishing-and-pixel.png

```text
Use case: ui-mockup
Asset type: cohesive two-panel high-fidelity game interaction reference, 1536x1024 landscape.
Primary request: Show two polished gameplay screens side by side of an original cozy Chinese whale-maid desktop pet board game. Reference image is the character identity reference only: preserve tiny chibi blue-haired girl with whale-tail side ornaments in navy-and-white maid dress. Brand is original, not Mario.
Style: sophisticated illustrated 2.5D toy-diorama indie game, creamy UI with deep navy typography, soft natural lighting, seafoam blue and lavender, tactile painterly materials. The two panels are full rectangular screen mockups on a soft cream presentation background, equal size, generous spacing. Place the short heading “湖边钓鱼” over left screen and “像素化奇遇” over right screen. Minimal legible Chinese text.
LEFT: a real playable fishing minigame at the tiny wooden dock of an azure lake. Large inviting detailed water surface with lily pads, visible fish silhouette, bobber and circular expanding timing ripple. The blue-haired whale-maid is sitting on the dock holding a rod; no additional human characters. Bottom overlay contains a simple horizontal timing bar with a wide mint green target window, a white moving cursor, one large navy “收竿” button, an unobtrusive “跳过” button. Top compact goal text “等浮漂下沉，再收竿”, small progress “1 / 3”. Keep the lake visible, no huge dialog obscuring it. Charming splash and fish sparkle.
RIGHT: same game's board with a lavender pixel grove and clinic, showing a whimsical pixel-status effect. Apply intentional crisp 8-bit chunky pixel rendering to the whale-maid sprite, the immediately adjacent purple grass patch, and a small decorative portrait frame. Rest of game UI stays smooth and text remains crisp, readable, non-pixelated. A discreet violet status chip says “像素化 · 还需经过起点 3 次”. Show a small cream non-blocking bottom choice panel with title “变成像素鱼了！” and three clearly separated buttons: “去医院 · 3”, “解像素糖 · 2”, “先这样玩”. Tiny fish-snack pictogram beside amounts. Show a discoverable special blue pixel fish silhouette in a small purple badge as the upside of the status. Clinic is an adorable cream building with teal medical-bag sign, not a red cross. A small funny readable speech bubble “这下真成纸片鱼了”.
Avoid: blurry whole UI, illegible pixel text, scanline covering all controls, scary glitch horror, green code matrix, casino style, Mario characters, duplicated limbs, watermark, excessive microcopy. Concept mockups, not production sprites.
```

## 03-dice-and-tiles

文件：references/03-dice-and-tiles.png

```text
Use case: ui-mockup
Asset type: game art direction component sheet, landscape 1536x1024.
Primary request: A polished reference sheet for a cozy Chinese whale-island desktop board game, focusing on a tactile dice roll and board spaces. Original indie game visuals. Cream parchment background, quiet navy type, generous whitespace, 3 organized horizontal sections with tiny Chinese headings.
Style: hand-painted 2.5D toy-like game illustration with soft bevels, ivory ceramic, navy blue recessed circular pips, subtle seafoam accents, very cohesive premium illustration, no emoji.
Top section heading “骰子手感”. Three equal sequential panels showing same rounded cube ivory-and-navy die: 1) “蓄力” — compact tilted die with a soft elliptical shadow; 2) “弹跳” — die airborne at three-quarter view with restrained curved motion trails and larger softer shadow; 3) “落定” — die settled, top face cleanly shows five circular navy pips (one at each corner and one center), side faces logically have distinct counts, a small soft landing dust ring. No blobs pretending to be pips. Gentle material highlights, bevels, die has physical volume.
Middle section heading “地形与事件格”. Four detailed miniature vignette samples spaced equally: azure lake tile with embossed fishhook pictogram and wooden dock beside it; lavender voxel tile with white 8-bit fish pictogram next to 3 blocky lavender trees; cream clinic tile with a small teal medical bag pictogram and cute clinic beside it; warm golden chest tile with treasure chest resting behind it amid rounded woodland mushrooms. Each sample shows a flat readable rounded ceramic stepping stone connected to a small patch of terrain. No raised blocks blocking character traversal, terrain physically explains event. Short labels only “钓鱼”, “像素”, “医院”, “宝箱”.
Bottom section heading “路径与反馈”. A horizontal 6-space grassy stone path with clear small directional arrows and 3 highlighted mint stepping stones leading to an azure fishing tile, a small ghosted destination marker over the final fishing tile, and tiny fish-snack +2 reward particles floating nearby. To the right, show three small cream UI item cards with distinctive illustrated icons and short labels: “步数 ±1” with a little blue fin, “解像素糖” with a lavender wrapped candy, “护身泡泡” with a translucent bubble shield. Professional game design presentation, consistent soft shadows and lighting. No character required.
Avoid: Mario cubes, Mario question marks, neon casino glows, photographs, random text, giant title, clutter, watermark. Concept art components, not a production sprite atlas; no promise of exact crop or six-face die atlas.
```

