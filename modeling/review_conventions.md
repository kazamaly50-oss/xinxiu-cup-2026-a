# 建模岗审核惯例与下游接口契约

## 惯例 R1：审核运行环境（2026-11-25 Muse 定）
- T0.1 是纯 numpy 几何代码，审核时用的是 Python 3.14.8 + numpy 2.5.3（`py` 启动器）。这不是队规要求的环境，但结果与环境无关，本次放行。
- **从 T2.2 起，凡涉及 pulp 的单子**，审核必须在 anaconda3 + pulp 2.8 环境下运行，并在审核报告开头写明实际使用的解释器路径以及 Python、numpy、pulp 的版本号。
- 本机现状（2026-11-25 实测）：队规写的路径 `C:\Users\LENOVO\anaconda3\python.exe` 在本机**不存在**，因为本机用户名是 `123`。本机 Anaconda 位于 `D:\AnacondaDownload\Anaconda Navigator\python.exe`，版本为 Python 3.14.6 + numpy 2.4.6，**未安装 pulp**。T2.2 开审前需要队长确认：用哪个解释器作为队规环境，以及是否在其中安装 pulp==2.8。

## 契约 C1：simulate.py 与 pos(s) 的越界约定（来源：T0.1 审核问题 #4，Muse 定为不改代码）
- `geometry.pos(s)` 只接受 0 ≤ s ≤ `path_length()`。越界、NaN、inf 一律抛 `ValueError`，且不设浮点容差。
- simulate.py 每推进一次敌人位置，**必须先判断 s ≥ `path_length()`**。条件成立时按“到达 D”处理：未被消灭则计一次漏怪，并立即移除该敌人。
- **永远不许把越界的 s 传给 `pos`。**
- 审核 simulate.py 时的检查方法：
  1. 静态检查所有 `pos(` 调用点，确认调用前都有到达判定；
  2. 构造一个恰好到达终点的场景和一个越过终点的场景运行，确认程序不抛 `ValueError`，且漏怪计数正确。

## 接口基准：geometry.py（T0.1，提交 c304a08，以实测签名为准）
- `path_length() -> float`
- `pos(s) -> tuple[float, float]`
- `dist_to_path(x, y) -> float`
- 三个函数都只接受标量；不接受数组批量输入。
