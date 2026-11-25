"""塔防题的道路中心线几何，所有长度与坐标均以米为单位。"""

import numpy as np


_VERTICES = np.array([
    [0.0, 0.0],
    [400.0, 200.0],
    [700.0, 800.0],
    [1200.0, 900.0],
    [1500.0, 1400.0],
    [1800.0, 1700.0],
    [2000.0, 2000.0],
])
_SEGMENTS = np.diff(_VERTICES, axis=0)
_LENGTHS = np.linalg.norm(_SEGMENTS, axis=1)
_CUMULATIVE = np.concatenate(([0.0], np.cumsum(_LENGTHS)))


def path_length() -> float:
    """返回 O→A→B→C→E→F→D 的道路中心线总长（米）。

    参数：无。
    返回：Python float，六条线段长度之和。
    """
    return float(_CUMULATIVE[-1])


def pos(s: float) -> tuple[float, float]:
    """返回从 O 沿道路中心线前进 s 米时的坐标。

    参数：s 为有限实数标量，范围为 [0, path_length()]，单位为米。
    返回：(x, y) 浮点元组，坐标单位为米。
    异常：s 非标量、非有限或越界时抛出 ValueError。

    仿真调用方应先处理 s 达到或超过总长的到达出口事件。
    """
    if np.ndim(s) != 0:
        raise ValueError("s must be a scalar")
    s = float(s)
    if not np.isfinite(s) or not 0.0 <= s <= path_length():
        raise ValueError("s must be finite and within [0, path_length()]")
    if s == path_length():
        return (2000.0, 2000.0)

    segment_index = int(np.searchsorted(_CUMULATIVE, s, side="right") - 1)
    fraction = (s - _CUMULATIVE[segment_index]) / _LENGTHS[segment_index]
    point = _VERTICES[segment_index] + fraction * _SEGMENTS[segment_index]
    return (float(point[0]), float(point[1]))


def dist_to_path(x: float, y: float) -> float:
    """返回点 (x, y) 到道路中心折线的最短欧氏距离。

    参数：x、y 为有限实数标量，单位为米，允许位于地图范围外。
    返回：Python float，点到六条有限线段的最小距离，单位为米。
    异常：任一坐标非标量或非有限时抛出 ValueError。
    """
    if np.ndim(x) != 0 or np.ndim(y) != 0:
        raise ValueError("x and y must be scalars")
    point = np.array([float(x), float(y)])
    if not np.all(np.isfinite(point)):
        raise ValueError("x and y must be finite")

    offsets = point - _VERTICES[:-1]
    fractions = np.sum(offsets * _SEGMENTS, axis=1) / (_LENGTHS ** 2)
    fractions = np.clip(fractions, 0.0, 1.0)
    nearest_points = _VERTICES[:-1] + fractions[:, None] * _SEGMENTS
    return float(np.min(np.linalg.norm(point - nearest_points, axis=1)))


if __name__ == "__main__":
    total = path_length()
    start = pos(0.0)
    end = pos(total)
    print(f"path_length() = {total:.12f} m")
    print(f"pos(0) = {start}")
    print(f"pos(path_length()) = {end}")
    assert abs(total - 2995.9) <= 0.5, "path length check failed"
    assert start == (0.0, 0.0), "start position check failed"
    assert end == (2000.0, 2000.0), "end position check failed"
