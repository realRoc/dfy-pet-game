"""配置里允许出现的美术种类。加载时用来查错，绘制层必须为每一种提供画法。"""

TILE_STYLES = {"card", "stone", "sprite"}

# [[terrain]] kind
TERRAIN_KINDS = {
    "island",     # 主岛：points 轮廓，自动画悬崖、沙边和草地
    "plateau",    # 抬高的台地：points 轮廓 + 自己的草色
    "sand",       # 沙滩：points 轮廓
    "lake",       # 湖：center + radius
    "river",      # 河：points 折线 + width
    "patch",      # 地面色块：points 轮廓 + texture / color，比如林下、广场、花田
}

# [[decor]] kind
DECOR_KINDS = {
    "tree", "palm", "mushroom", "bush", "flowers", "rock",
    "pixel_tree", "pixel_block", "ruin_arch",
    "house", "shop", "hospital", "stall",
    "dock", "lily", "signpost", "boat", "whale", "lamp",
}

# tiles.toml 里的 symbol
SYMBOLS = {
    "flag", "fish", "hook", "chest", "bench", "sign", "fork", "leaf",
    "shop", "pixel", "cross", "question",
}

DICE_STYLES = {"flat", "cube"}
