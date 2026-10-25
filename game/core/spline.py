"""道路曲线：Catmull-Rom 采样 + 按弧长等距取点。纯 Python，加载地图和绘制共用。"""
import math


def sample(points, per_segment=24):
    """过所有控制点的平滑折线（开口曲线，两端点复制一次当邻点）。"""
    if len(points) < 2:
        return [tuple(p) for p in points]
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(per_segment):
            t = s / per_segment
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t
                                    + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    out.append(tuple(points[-1]))
    return out


def length(poly):
    return sum(math.dist(a, b) for a, b in zip(poly, poly[1:]))


def at(poly, t):
    """折线上按弧长比例 t（0~1）取点。"""
    total = length(poly)
    if total == 0:
        return tuple(poly[0])
    want = total * min(1.0, max(0.0, t))
    for a, b in zip(poly, poly[1:]):
        d = math.dist(a, b)
        if want <= d and d > 0:
            u = want / d
            return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        want -= d
    return tuple(poly[-1])
