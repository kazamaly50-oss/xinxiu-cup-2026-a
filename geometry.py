"""塔防题的道路中心线几何，所有长度与坐标均以米为单位。

计算流程：先由七个顶点预计算六段道路及累计里程；位置查询用
累计里程定位线段并插值；距离查询对六条线段分别投影后取最小值。
"""

import numpy as np


# 每行是一个顶点的 (x, y)，行顺序就是敌人的行进顺序 O、A、B、C、E、F、D。
_VERTICES = np.array([
    [0.0, 0.0],
    [400.0, 200.0],
    [700.0, 800.0],
    [1200.0, 900.0],
    [1500.0, 1400.0],
    [1800.0, 1700.0],
    [2000.0, 2000.0],
])
# 相邻行相减得到六个方向向量，每行保存该段的 (dx, dy)。
_SEGMENTS = np.diff(_VERTICES, axis=0)
# 对每行求欧氏范数，即 sqrt(dx**2 + dy**2)，得到六个段长。
_LENGTHS = np.linalg.norm(_SEGMENTS, axis=1)
# 在段长累加结果前补上起点里程 0，得到七个顶点各自的累计里程。
_CUMULATIVE = np.concatenate(([0.0], np.cumsum(_LENGTHS)))


def path_length() -> float:
    """返回 O→A→B→C→E→F→D 的道路中心线总长（米）。

    参数：无。
    返回：Python float，六条线段长度之和。
    """
    # 最后一个顶点的累计里程就是总长；转为 Python float 便于其他模块调用。
    return float(_CUMULATIVE[-1])


def pos(s: float) -> tuple[float, float]:
    """返回从 O 沿道路中心线前进 s 米时的坐标。

    参数：s 为有限实数标量，范围为 [0, path_length()]，单位为米。
    返回：(x, y) 浮点元组，坐标单位为米。
    异常：s 非标量、非有限或越界时抛出 ValueError。

    仿真调用方应先处理 s 达到或超过总长的到达出口事件。
    """
    # 1. 检查单个弧长的合法性，避免数组、无穷大或越界值进入插值过程。
    if np.ndim(s) != 0:
        raise ValueError("s must be a scalar")
    s = float(s)
    if not np.isfinite(s) or not 0.0 <= s <= path_length():
        raise ValueError("s must be finite and within [0, path_length()]")
    # 2. 终点没有下一条线段，单独返回以防后面的索引超出六段道路范围。
    if s == path_length():
        return (2000.0, 2000.0)

    # 3. 查找 s 所在线段。right 让恰好位于拐点的 s 归到下一段的起点。
    segment_index = int(np.searchsorted(_CUMULATIVE, s, side="right") - 1)
    # 4. 段内已走距离除以段长，得到 0～1 的比例，再沿该段方向向量插值。
    fraction = (s - _CUMULATIVE[segment_index]) / _LENGTHS[segment_index]
    point = _VERTICES[segment_index] + fraction * _SEGMENTS[segment_index]
    return (float(point[0]), float(point[1]))


def dist_to_path(x: float, y: float) -> float:
    """返回点 (x, y) 到道路中心折线的最短欧氏距离。

    参数：x、y 为有限实数标量，单位为米，允许位于地图范围外。
    返回：Python float，点到六条有限线段的最小距离，单位为米。
    异常：任一坐标非标量或非有限时抛出 ValueError。
    """
    # 1. 将两个有限标量组成待查询点 P。
    if np.ndim(x) != 0 or np.ndim(y) != 0:
        raise ValueError("x and y must be scalars")
    point = np.array([float(x), float(y)])
    if not np.all(np.isfinite(point)):
        raise ValueError("x and y must be finite")

    # 2. 对每段起点 A 构造 AP。六行对应六条线段，最后的 D 不作为段起点。
    offsets = point - _VERTICES[:-1]
    # 投影比例 t = (AP·AB) / |AB|²；axis=1 表示逐行对两个坐标分量求和。
    fractions = np.sum(offsets * _SEGMENTS, axis=1) / (_LENGTHS ** 2)
    # 3. t<0 时最近点是 A，t>1 时是 B；截到 [0,1] 可处理有限线段的端点。
    fractions = np.clip(fractions, 0.0, 1.0)
    # 将六个比例变成六行一列，使每段的 x、y 分量乘上同一个比例。
    nearest_points = _VERTICES[:-1] + fractions[:, None] * _SEGMENTS
    # 4. 计算 P 到六个最近点的距离，最小值就是到整条折线的距离。
    return float(np.min(np.linalg.norm(point - nearest_points, axis=1)))


if __name__ == "__main__":
    # 直接运行文件时打印并检查题目要求的三项结果；导入模块时不会执行。
    total = path_length()
    start = pos(0.0)
    end = pos(total)
    print(f"path_length() = {total:.12f} m")
    print(f"pos(0) = {start}")
    print(f"pos(path_length()) = {end}")
    assert abs(total - 2995.9) <= 0.5, "path length check failed"
    assert start == (0.0, 0.0), "start position check failed"
    assert end == (2000.0, 2000.0), "end position check failed"
