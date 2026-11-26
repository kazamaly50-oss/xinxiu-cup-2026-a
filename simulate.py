"""T1.1：固定塔布局、单波敌人的固定时间步仿真（论文节号待论文岗确认）。

每个步首按欧氏距离选目标，汇总多塔 DPS，再在该步内结算伤害。
到达 D 后不再受伤；恰好在 D 血量归零时计击杀，见 modeling/rules.md。
只计算战斗；预算、塔基合法性、动态建造和升级由后续模块负责。
"""

import numpy as np

import geometry


# (射程：米，每秒伤害：血量/秒)。价格不参与本单战斗计算。
TOWER_STATS = {"小塔": (75.0, 10.0), "中塔": (125.0, 20.0),
               "大塔": (200.0, 40.0)}


def _real(value, name):
    """校验有限实数标量 value，返回 float；name 用于 ValueError 提示。"""
    # 拒绝布尔、字符串、复数及数组，避免把配置错误静默转成有效数值。
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        raise ValueError(f"{name} 必须是有限实数标量")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} 超出浮点表示范围") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} 必须是有限实数标量")
    return result


def simulate(towers, wave, dt=0.05):
    """返回一波敌人的漏怪数、逐敌结局、累计承伤曲线及游戏耗时。

    参数：
        towers：列表，每项为 (x, y, 类型)，坐标单位米；类型为
            '小塔'、'中塔' 或 '大塔'。允许空列表。此函数不检查建塔合法性。
        wave：字典，必须含 '数量'（非负整数）、'血量'（正实数）、
            '速度'（正实数，米/秒）、'出发间隔'（非负实数，秒）。
            敌人编号从 1 开始，第 i 只在 (i-1)*出发间隔 时出发。
        dt：正有限实数，固定选目标步长，单位秒，默认 0.05。
    返回：
        dict，均为可直接序列化为 JSON 的 Python 内置类型：
        '漏怪数'：int；
        '每只敌人结果'：按编号排序的列表，每项含编号、出发时刻、
            结果（击杀/漏怪）、死亡时刻、漏怪时刻、剩余血量、累计承伤；
            未发生的死亡/漏怪时刻为 None；
        '累计承伤曲线'：按编号排序，每项为 {'编号': int, '采样':
            [(游戏时刻秒, 累计实际伤害), ...]}，从出生到死亡或漏怪；
        '总耗时'：最后一只敌人的结局时刻，float，单位秒，非程序运行时间。
    异常：配置缺项、非法数值、未知塔型或时间无法用 float 表示时 ValueError。

    数值约定：步首选射程内最近的存活敌人，等距时选较小编号；该步
    不重新分配溢出伤害。非网格出生在下一个步首首次参与选敌，位置仍按
    真实出发时刻计算。伤害积分截到到达 D 的时刻，步内死亡用 hp/DPS
    插值。射程穿越和最近目标交换仅在步首采样，必须通过缩步检验误差。
    """
    # 1. 统一输入，防止负速度导致永不离场或 NaN 破坏距离比较。
    dt = _real(dt, "dt")
    if dt <= 0:
        raise ValueError("dt 必须大于 0")
    keys = ("数量", "血量", "速度", "出发间隔")
    if not isinstance(wave, dict) or any(key not in wave for key in keys):
        raise ValueError("wave 必须含数量、血量、速度、出发间隔")
    count = _real(wave["数量"], "数量")
    initial_hp = _real(wave["血量"], "血量")
    speed = _real(wave["速度"], "速度")
    interval = _real(wave["出发间隔"], "出发间隔")
    if count < 0 or not count.is_integer():
        raise ValueError("数量必须是非负整数")
    if initial_hp <= 0 or speed <= 0 or interval < 0:
        raise ValueError("血量和速度须大于 0，出发间隔须非负")
    count = int(count)
    if not isinstance(towers, (list, tuple)):
        raise ValueError("towers 必须是塔列表")
    tower_rows = []
    for tower in towers:
        if not isinstance(tower, (list, tuple)) or len(tower) != 3:
            raise ValueError("每座塔必须为 (x, y, 类型)")
        x, y, kind = tower
        if not isinstance(kind, str) or kind not in TOWER_STATS:
            raise ValueError("塔类型必须是小塔、中塔或大塔")
        tower_rows.append((_real(x, "塔 x"), _real(y, "塔 y"),
                           *TOWER_STATS[kind]))
    tower_data = np.asarray(tower_rows, dtype=float).reshape(-1, 4)
    length = geometry.path_length()
    travel_time = length / speed
    if not np.isfinite(travel_time) or travel_time <= 0:
        raise ValueError("行程时间超出浮点表示范围")
    if count == 0:
        return {"漏怪数": 0, "每只敌人结果": [], "累计承伤曲线": [], "总耗时": 0.0}

    # 2. 每个敌人独立保存出发/出口时刻与血量；结果非 None 即永久离场。
    with np.errstate(over="ignore", invalid="ignore"):
        births = np.arange(count, dtype=float) * interval
        exits = births + travel_time
    if (not np.all(np.isfinite(exits)) or np.any(exits <= births)
            or not np.isfinite(exits[-1] / dt)
            or exits[-1] / dt >= 2**52):
        raise ValueError("时间尺度过大，无法可靠表示步长或行程")
    # 0.1*3 与 0.3 可能相差一位尾数；只把机器精度内的网格时刻视为相同，
    # 防止本该在步首出生的敌人被推迟整整一格。真正的步间出生仍向上取整。
    grid_births = births / dt
    nearest_grid = np.rint(grid_births)
    grid_tol = 8 * np.finfo(float).eps * np.maximum(1.0, np.abs(grid_births))
    grid_births = np.where(abs(grid_births - nearest_grid) <= grid_tol,
                           nearest_grid, grid_births)
    birth_ticks = np.ceil(grid_births).astype(np.int64)
    hp = np.full(count, initial_hp)
    results = [None] * count
    curves = [[(float(birth), 0.0)] for birth in births]

    def finish(enemy, killed, when):
        """登记 enemy 的唯一结局；killed 为击杀布尔量，when 为游戏秒数。"""
        damage = float(initial_hp - hp[enemy])
        if curves[enemy][-1][0] != when:
            curves[enemy].append((float(when), damage))
        results[enemy] = {
            "编号": int(enemy + 1), "出发时刻": float(births[enemy]),
            "结果": "击杀" if killed else "漏怪",
            "死亡时刻": float(when) if killed else None,
            "漏怪时刻": None if killed else float(when),
            "剩余血量": float(hp[enemy]), "累计承伤": damage,
        }

    tick = 0
    remaining = count
    while remaining:
        # 3. 整数步号乘 dt，避免反复 t += dt 的累计时间漂移。
        t, next_t = tick * dt, (tick + 1) * dt
        if next_t <= t or not np.isfinite(next_t):
            raise ValueError("当前时间尺度无法可靠推进 dt")
        active = []
        for enemy in range(count):
            if results[enemy] is not None or birth_ticks[enemy] > tick:
                continue
            # 大步长可能跳过某敌人的整个行程；必须先判离场，再查询 pos。
            if exits[enemy] <= t:
                finish(enemy, False, float(exits[enemy]))
                remaining -= 1
            else:
                active.append(enemy)

        if active:
            # 4. 距离为塔心到敌人中心的欧氏距离，不是弧长差或距出口距离。
            s = np.clip((t - births[active]) * speed, 0.0, length)
            points = np.asarray([geometry.pos(float(value)) for value in s])
            rates = np.zeros(len(active))
            for x, y, radius, dps in tower_data:
                distances = np.hypot(points[:, 0] - x, points[:, 1] - y)
                target = int(np.argmin(distances))
                # active 升序且 argmin 返回首个最小值，故等距选择较小编号。
                if distances[target] <= radius:
                    rates[target] += dps

            # 5. 先选完所有塔，再统一扣血，结果不依赖塔列表的结算先后。
            for local, enemy in enumerate(active):
                # 网格对齐最多有机器尾数差，仍禁止在真实出生时刻前计伤害。
                start = max(t, float(births[enemy]))
                if curves[enemy][-1][0] < start:
                    curves[enemy].append((float(start), float(initial_hp - hp[enemy])))
                stop = min(next_t, float(exits[enemy]))
                duration = max(0.0, stop - start)
                rate = float(rates[local])
                possible = rate * duration
                # 只消除浮点累计舍入误差，不使用 dt 大小来放宽击杀条件。
                hp_tol = 64 * np.finfo(float).eps * max(initial_hp, possible)
                if rate > 0 and hp[enemy] <= possible + hp_tol:
                    # hp/rate 是本步内击杀用时。相等时先登记击杀；出口后的
                    # 剩余时间不补伤害，也不把溢出伤害转给其他敌人。
                    death = min(stop, start + float(hp[enemy]) / rate)
                    hp[enemy] = 0.0
                    finish(enemy, True, death)
                    remaining -= 1
                else:
                    hp[enemy] = max(0.0, float(hp[enemy]) - possible)
                    curves[enemy].append((float(stop), float(initial_hp - hp[enemy])))
                    if exits[enemy] <= next_t:
                        finish(enemy, False, float(exits[enemy]))
                        remaining -= 1

        tick += 1
        # 无人在场时直接跳到下一次出兵后的网格步，避免遍历长空闲期。
        if remaining and not any(
            results[i] is None and birth_ticks[i] <= tick for i in range(count)
        ):
            tick = max(tick, min(int(birth_ticks[i]) for i in range(count)
                                 if results[i] is None))

    return {
        "漏怪数": sum(item["结果"] == "漏怪" for item in results),
        "每只敌人结果": results,
        "累计承伤曲线": [{"编号": i + 1, "采样": samples}
                         for i, samples in enumerate(curves)],
        "总耗时": float(max(item["死亡时刻"] if item["结果"] == "击杀"
                          else item["漏怪时刻"] for item in results)),
    }


def _self_checks():
    """执行 T1.1 断言并返回可序列化摘要；合成短路仅在测试上下文中替换。"""
    from unittest.mock import patch
    from coverage import cover_intervals, exposure

    checks = []
    # 手算：100 m / 40 m/s = 2.5 s；小塔最多打 25 血。
    # 用 patch 临时替换几何函数，退出 with 自动恢复，生产接口不接受假地图。
    with patch.object(geometry, "path_length", return_value=100.0), patch.object(
        geometry, "pos", side_effect=lambda s: (s, 0.0)
    ):
        boundary = []
        for health, expected, when in [(24, "击杀", 2.4), (25, "击杀", 2.5),
                                      (26, "漏怪", 2.5)]:
            result = simulate([(50, 20, "小塔")],
                              {"数量": 1, "血量": health, "速度": 40, "出发间隔": 0}, 1)
            enemy = result["每只敌人结果"][0]
            assert enemy["结果"] == expected
            assert abs(result["总耗时"] - when) < 1e-12
            assert enemy["累计承伤"] == min(health, 25)
            boundary.append(enemy)
        checks.append({"名称": "出口前击杀/同刻击杀/出口剩1血漏怪", "通过": True,
                       "实际": boundary})

        # 等距同时出生，多塔集火只消耗一只敌人的血；下一步才重新选目标。
        wave = {"数量": 2, "血量": 5, "速度": 10, "出发间隔": 0}
        result = simulate([(50, 20, "小塔"), (50, -20, "中塔")], wave, 1)
        deaths = [item["死亡时刻"] for item in result["每只敌人结果"]]
        assert np.allclose(deaths, [1/6, 1 + 1/6], rtol=0, atol=1e-12)
        reverse = simulate([(50, -20, "中塔"), (50, 20, "小塔")], wave, 1)
        assert result == reverse
        checks.append({"名称": "等距选编号/多塔同时结算/不转移溢伤/下步重选", "通过": True,
                       "死亡时刻": deaths})

        # 第二只在步间出生，下一步时更靠近 O；应优先打它而非领头敌人。
        nearest = simulate([(0, 20, "小塔")],
                           {"数量": 2, "血量": 1000, "速度": 40, "出发间隔": 0.5}, 1)
        assert nearest["累计承伤曲线"][1]["采样"][:3] == [(0.5, 0.0), (1.0, 0.0), (2.0, 10.0)]
        assert [item["累计承伤"] for item in nearest["每只敌人结果"]] == [10.0, 20.0]
        skipped = simulate([], {"数量": 2, "血量": 1, "速度": 400, "出发间隔": 0.3}, 1)
        assert [item["漏怪时刻"] for item in skipped["每只敌人结果"]] == [0.25, 0.55]
        checks.append({"名称": "欧氏最近目标/步间出生/整段行程被步长跨过", "通过": True})

        rounding = simulate([(0, 20, "小塔")],
                            {"数量": 4, "血量": 1, "速度": 40, "出发间隔": 0.1}, 0.3)
        assert abs(rounding["每只敌人结果"][3]["死亡时刻"] - 0.4) < 1e-12
        checks.append({"名称": "出生时刻0.1*3与网格0.3的浮点对齐", "通过": True})

        # 足量 DPS 覆盖合成整路的极端检查，仅验证程序，不代表正式 A1 布局。
        result = simulate([(50, 20, "小塔")],
                          {"数量": 3, "血量": 20, "速度": 40, "出发间隔": 3})
        assert result["漏怪数"] == 0
        checks.append({"名称": "合成整路覆盖且伤害充足", "通过": True, "漏怪数": 0})

    # 在正式折线路径独立用解析覆盖时长核对单敌伤害，血量足够大以免提前死亡。
    wave = {"数量": 1, "血量": 10000, "速度": 20, "出发间隔": 0}
    actual = simulate([(190, 120, "中塔")], wave)["每只敌人结果"][0]["累计承伤"]
    expected = exposure(190, 120, 125, 20) * 20
    error = abs(actual - expected) / expected
    assert error < 0.01
    checks.append({"名称": "正式路径单塔单敌解析伤害预检", "通过": True,
                   "仿真伤害": actual, "解析伤害": expected, "相对误差": error})

    # 固定布局缩步对照是预检，不据此声明 M1 或 A1 通过人工验收。
    wave = {"数量": 3, "血量": 200, "速度": 20, "出发间隔": 10}
    leaks = [simulate([(190, 120, "中塔")], wave, step)["漏怪数"] for step in [0.1, 0.05]]
    # 此项验收的是同一输入缩步后的漏怪数稳定性；不把任意漏怪数硬写成预期。
    assert leaks[0] == leaks[1]
    checks.append({"名称": "同布局dt=0.1/0.05预检", "通过": True, "漏怪数": leaks})
    a1 = {"数量": 10, "血量": 1700, "速度": 20, "出发间隔": 10}
    empty = simulate([], a1)
    assert empty["漏怪数"] == 10
    assert abs(empty["总耗时"] - (90 + geometry.path_length()/20)) < 1e-10
    assert all(item["累计承伤"] == 0 for item in empty["每只敌人结果"])
    checks.append({"名称": "正式A1输入无塔全漏", "通过": True,
                   "漏怪数": empty["漏怪数"], "游戏耗时": empty["总耗时"]})

    invalid = [( [], {**a1, "数量": -1}, 0.05), ([], {**a1, "数量": 1.5}, 0.05),
               ([], {**a1, "速度": 0}, 0.05), ([], {**a1, "血量": np.nan}, 0.05),
               ([], {**a1, "出发间隔": -1}, 0.05), ([], a1, 0), ([], a1, True),
               ([(0, 0, "未知塔")], a1, 0.05), ([(np.inf, 0, "小塔")], a1, 0.05),
               ([], {}, 0.05), ([], {**a1, "血量": "1700"}, 0.05)]
    for towers, wave, step in invalid:
        try:
            simulate(towers, wave, step)
        except ValueError:
            continue
        raise AssertionError("非法输入未抛出 ValueError")
    assert simulate([], {**a1, "数量": 0})["总耗时"] == 0.0
    checks.append({"名称": "非法输入与空波", "通过": True, "非法输入数": len(invalid)})

    # 独立参考：由 coverage 的弧长区间判断各步首是否处于射程内，再对
    # 区间指示函数作左端点求和。这不调用仿真器内部选敌/扣血逻辑。
    # 用高血量单敌保证全程存活，随机塔靠近路径，以免多数案例无覆盖。
    rng = np.random.default_rng(42)
    max_error = 0.0
    for _ in range(20):
        point = np.asarray(geometry.pos(float(rng.uniform(0, geometry.path_length()))))
        x, y = point + rng.uniform(-60, 60, size=2)
        kind = str(rng.choice(list(TOWER_STATS)))
        radius, dps = TOWER_STATS[kind]
        speed = float(rng.uniform(10, 50))
        step = float(rng.choice([0.05, 0.1, 0.2]))
        end = geometry.path_length() / speed
        times = np.arange(int(np.ceil(end / step))) * step
        covered = np.zeros(len(times), dtype=bool)
        for low, high in cover_intervals(float(x), float(y), radius):
            covered |= (times * speed >= low) & (times * speed <= high)
        reference = float(np.sum(np.minimum(step, end - times)[covered]) * dps)
        result = simulate([(float(x), float(y), kind)],
                          {"数量": 1, "血量": 10000, "速度": speed, "出发间隔": 0}, step)
        enemy = result["每只敌人结果"][0]
        error = abs(enemy["累计承伤"] - reference)
        max_error = max(max_error, error)
        assert error < 1e-7
        samples = np.asarray(result["累计承伤曲线"][0]["采样"])
        assert np.all(np.diff(samples[:, 0]) > 0)
        assert np.all(np.diff(samples[:, 1]) >= 0)
        assert samples[-1, 0] == enemy["漏怪时刻"] == end
        assert samples[-1, 1] == enemy["累计承伤"]
        assert abs(enemy["剩余血量"] + enemy["累计承伤"] - 10000) < 1e-10
    checks.append({"名称": "独立覆盖区间离散积分/逐敌日志守恒", "通过": True,
                   "种子": 42, "样本数": 20, "最大绝对伤害误差": max_error})
    return checks


if __name__ == "__main__":
    import json

    # stdout 输出完整摘要，供外部进程计时及 JSON 交接收集；不生成假验收状态。
    print(json.dumps({"模块": "simulate.py", "校验": _self_checks()},
                     ensure_ascii=False, indent=2, allow_nan=False))
