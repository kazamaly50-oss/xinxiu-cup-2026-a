"""计算圆形射程与道路中心折线的覆盖区间及匀速暴露时间。

逻辑顺序：逐段求圆内参数区间，裁剪到有限线段，换算为全路径弧长，
最后合并相接或重叠的区间。长度单位为米，时间单位为秒。
"""

import numpy as np

from geometry import _CUMULATIVE, _LENGTHS, _SEGMENTS, _VERTICES, path_length, pos


# 复用 T0.1 的路径数组，避免两份坐标发生漂移。这里只读取这些数组。
_MERGE_TOLERANCE = 1e-8
_ROUNDING_FACTOR = 64 * np.finfo(float).eps


def _finite_scalar(value, name):
    """将有限实数标量转为 Python float，统一拒绝数组、复数和非数值输入。"""
    array = np.asarray(value)
    if array.ndim != 0 or array.dtype.kind not in "iuf":
        raise ValueError(f"{name} must be a finite real scalar")
    number = float(array)
    if not np.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def cover_intervals(tx, ty, R) -> list[tuple[float, float]]:
    """返回塔的圆形射程与道路中心线相交的闭弧长区间。

    参数：tx、ty 为塔心坐标，R 为非负射程，均为有限实数标量（米）。
    返回：按弧长递增、已合并的 [(s1, s2), ...]，端点为 Python float。
          无覆盖时返回 []；相切保留 (s, s)，对应覆盖长度为零。
    异常：非实数标量、非有限输入或负半径抛出 ValueError。

    允许测试塔心位于道路上或地图外。相接区间的合并容差为 1e-8 米。
    """
    tx = _finite_scalar(tx, "tx")
    ty = _finite_scalar(ty, "ty")
    radius = _finite_scalar(R, "R")
    if radius < 0:
        raise ValueError("R must be nonnegative")

    center = np.array([tx, ty])
    intervals = []
    for index, direction in enumerate(_SEGMENTS):
        # 1. 线段参数为 P(u)=A+u*d，u∈[0,1]；设 f=A-塔心。
        # 圆内条件为 a*u²+b*u+c≤0，其中 a=d·d，b=2*f·d，c=f·f-R²。
        offset = _VERTICES[index] - center
        a = float(np.dot(direction, direction))
        b = float(2 * np.dot(offset, direction))

        # 二维恒等式给出 Δ=b²-4ac=4*(a*R²-cross(f,d)²)。
        # 用叉积形式避免 b² 与 4ac 相减造成的消去误差，尤其是 R=0 时。
        cross = float(offset[0] * direction[1] - offset[1] * direction[0])
        # pos(s) 生成的共线点也可能有最后几位舍入误差，零半径时同样要处理。
        cross_tolerance = _ROUNDING_FACTOR * (
            (abs(_VERTICES[index, 0]) + abs(tx)) * abs(direction[1])
            + (abs(_VERTICES[index, 1]) + abs(ty)) * abs(direction[0]))
        if abs(cross) <= cross_tolerance:
            cross = 0.0
        radius_term = a * radius**2
        cross_term = cross**2
        discriminant = 4 * (radius_term - cross_term)
        tolerance = 4 * _ROUNDING_FACTOR * (abs(radius_term) + abs(cross_term))

        # 2. 明显负判别式表示圆与该段所在直线无交点，跳过此段。
        if discriminant < -tolerance:
            continue
        # 相切时两根相同；容差内的正负误差都收敛到一个点。
        if abs(discriminant) <= tolerance:
            discriminant = 0.0
        root = np.sqrt(discriminant)
        lower = max(0.0, (-b - root) / (2 * a))
        upper = min(1.0, (-b + root) / (2 * a))

        # 3. 两根界定的是整条直线上的圆内部分，必须与 [0,1] 求交。
        # 交集为空表示交点均在段外且本段不在圆内。
        # 若两根分别小于0、大于1，裁剪后得到 [0,1]，保留整段覆盖。
        if lower > upper:
            # 端点相切可能因舍入刚好落到 [0,1] 外，只吸收米级容差内偏差。
            if (lower - upper) * _LENGTHS[index] > _MERGE_TOLERANCE:
                continue
            lower = upper = float(np.clip((lower + upper) / 2, 0.0, 1.0))

        # 4. 段内比例乘段长，再加本段起点的累计里程，得到全路径弧长。
        start = float(_CUMULATIVE[index] + lower * _LENGTHS[index])
        end = float(_CUMULATIVE[index] + upper * _LENGTHS[index])
        # 使用既有累计端点，避免最后一段末端因重复加法略超出路径总长。
        start = min(start, path_length())
        end = min(end, path_length())
        if intervals and start <= intervals[-1][1] + _MERGE_TOLERANCE:
            intervals[-1] = (intervals[-1][0], max(intervals[-1][1], end))
        else:
            intervals.append((start, end))
    return intervals


def exposure(tx, ty, R, speed) -> float:
    """返回匀速敌人穿过该塔全部覆盖区间所需的时间。

    参数：tx、ty、R 的含义同 cover_intervals；speed 为有限正实数（m/s）。
    返回：覆盖总弧长÷speed，Python float，单位秒；相切与无覆盖均为0秒。
    异常：非法坐标、半径或速度抛出 ValueError。

    该值表示几何暴露时间，战斗中的实际攻击时间还取决于目标选择和存活状态。
    """
    speed = _finite_scalar(speed, "speed")
    if speed <= 0:
        raise ValueError("speed must be positive")
    intervals = cover_intervals(tx, ty, R)
    covered_length = sum(end - start for start, end in intervals)
    return float(covered_length / speed)


def _check_boundaries():
    """运行可复跑的解析边界检查；只有直接运行模块时才会调用。"""
    # OA 中点为 (200,100)，沿单位法向偏移75米，构造射程75米的相切圆。
    normal = np.array([-1.0, 2.0]) / np.sqrt(5.0)
    tangent_center = np.array([200.0, 100.0]) + 75 * normal
    tangent = cover_intervals(*tangent_center, 75)
    np.testing.assert_allclose(tangent, [[_LENGTHS[0] / 2] * 2], rtol=0, atol=1e-8)
    assert exposure(*tangent_center, 75, 20) == 0.0

    # 圆心在 OA 的反向延长线上，两个交点均在起点前，因此折线无覆盖。
    assert cover_intervals(-200, -100, 75) == []
    # 圆心在 O，第一段只有一部分在圆内；长度恰好等于半径。
    np.testing.assert_allclose(cover_intervals(0, 0, 75), [[0, 75]], rtol=0, atol=1e-8)

    # 以拐点 A 为圆心，两侧分别覆盖50米，应合并成一个100米的区间。
    corner = _CUMULATIVE[1]
    np.testing.assert_allclose(cover_intervals(400, 200, 50),
                               [[corner - 50, corner + 50]], rtol=0, atol=1e-8)
    # OA 两端都在圆内，即使两交点均在段外，也必须覆盖整个 OA。
    contained = cover_intervals(200, 100, 300)
    assert contained[0][0] == 0.0 and contained[0][1] >= _LENGTHS[0]
    np.testing.assert_allclose(cover_intervals(1000, 1000, 2000),
                               [[0, path_length()]], rtol=0, atol=1e-8)

    # 半径为零时，只保留路径上的一个点；拐点不能重复返回两个零区间。
    np.testing.assert_allclose(cover_intervals(200, 100, 0),
                               [[_LENGTHS[0] / 2] * 2], rtol=0, atol=1e-8)
    np.testing.assert_allclose(cover_intervals(400, 200, 0), [[corner, corner]], rtol=0, atol=1e-8)
    assert cover_intervals(200, 101, 0) == []
    assert cover_intervals(2000, 2000, 0) == [(path_length(), path_length())]
    # 特别覆盖拐点附近的插值坐标，防止零半径时放大坐标减法的舍入误差。
    for distance in np.linspace(0, path_length(), 101):
        np.testing.assert_allclose(cover_intervals(*pos(float(distance)), 0),
                                   [[distance, distance]], rtol=0, atol=1e-8)
    assert abs(exposure(200, 100, 75, 20) - 7.5) <= 1e-10

    # 非法输入均须以 ValueError 明确拒绝，不能返回貌似有效的覆盖时间。
    invalid = [lambda: cover_intervals(0, 0, -1),
               lambda: cover_intervals(np.nan, 0, 75),
               lambda: cover_intervals(0, np.inf, 75),
               lambda: cover_intervals([0], 0, 75),
               lambda: cover_intervals(0, 0, 1j)]
    for speed in (0, -1, np.nan, np.inf):
        invalid.append(lambda speed=speed: exposure(200, 100, 75, speed))
    for call in invalid:
        try:
            call()
        except ValueError:
            continue
        raise AssertionError("invalid input was accepted")


if __name__ == "__main__":
    # 先完成所有边界断言，再打印题目指定的两项校验值。
    _check_boundaries()
    intervals = cover_intervals(200, 100, 75)
    total = sum(end - start for start, end in intervals)
    empty = cover_intervals(0, 2000, 75)
    assert abs(total - 150.0) <= 1e-8
    assert empty == []
    print(f"straight coverage = {total:.12f} m; expected 150 m; PASS")
    print(f"outside coverage = {empty}; expected []; PASS")
