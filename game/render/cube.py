"""骰子立方体的三维数学：四元数旋转、骰面朝向。纯 Python，不依赖 Qt。

骰子坐标系：x 向右、y 向上、z 朝向镜头。对面点数和为 7。
"""
import math

# 骰子本地坐标里每个点数所在面的法线
FACE_NORMALS = {1: (0, 0, 1), 6: (0, 0, -1), 3: (1, 0, 0), 4: (-1, 0, 0), 2: (0, 1, 0), 5: (0, -1, 0)}


def q_axis(axis, angle):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    s = math.sin(angle / 2) / n
    return (math.cos(angle / 2), x * s, y * s, z * s)


def q_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def q_slerp(a, b, t):
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-x for x in b), -dot
    if dot > 0.9995:
        out = tuple(x + (y - x) * t for x, y in zip(a, b))
    else:
        th = math.acos(dot)
        s = math.sin(th)
        wa, wb = math.sin((1 - t) * th) / s, math.sin(t * th) / s
        out = tuple(wa * x + wb * y for x, y in zip(a, b))
    n = math.sqrt(sum(x * x for x in out))
    return tuple(x / n for x in out)


def q_rotate(q, v):
    w, x, y, z = q
    vx, vy, vz = v
    # v' = q v q*
    tx = 2 * (y * vz - z * vy)
    ty = 2 * (z * vx - x * vz)
    tz = 2 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


# 把每个点数转到正前方 (+z) 的旋转
FACE_TO_FRONT = {
    1: (1.0, 0.0, 0.0, 0.0),
    6: q_axis((0, 1, 0), math.pi),
    3: q_axis((0, 1, 0), -math.pi / 2),
    4: q_axis((0, 1, 0), math.pi / 2),
    2: q_axis((1, 0, 0), math.pi / 2),
    5: q_axis((1, 0, 0), -math.pi / 2),
}

# 固定的观察角度：略从右上方看，能看到顶面和右侧面
VIEW = q_mul(q_axis((0, 1, 0), math.radians(-24)), q_axis((1, 0, 0), math.radians(22)))


def orientation(from_face, to_face, e, spin_axis=(1, 0.4, 0.2), turns=2):
    """e 从 0 到 1：从 from_face 朝前平滑转到 to_face 朝前，中间绕 spin_axis 多转 turns 圈。
    两端的额外旋转都是整圈，所以 e=1 时朝前的面一定是 to_face。"""
    base = q_slerp(FACE_TO_FRONT[from_face], FACE_TO_FRONT[to_face], e)
    spin = q_axis(spin_axis, turns * 2 * math.pi * e)
    return q_mul(VIEW, q_mul(spin, base))


def front_face(q):
    """当前最朝向镜头的点数（测试用）。"""
    return max(FACE_NORMALS, key=lambda f: q_rotate(q, FACE_NORMALS[f])[2])
