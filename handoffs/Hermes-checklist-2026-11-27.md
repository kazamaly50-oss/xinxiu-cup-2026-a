# 给Hermes的核对清单（待转发，未代发）

请先fetch并核对原始建模分支，不修改历史审核报告，也不以AI复核代替真人验收。

1. `git fetch origin` 后确认 `origin/modeling/rules-v1` 为 `0563c1d721bd807e9976ae7698a4fd40fdbb0b13`。原4个提交没有改写；摘要作为单独历史材料保存。
2. 按 [PR #2](https://github.com/kazamaly50-oss/xinxiu-cup-2026-a/pull/2) → [PR #3](https://github.com/kazamaly50-oss/xinxiu-cup-2026-a/pull/3) → [PR #4](https://github.com/kazamaly50-oss/xinxiu-cup-2026-a/pull/4) 核对代码、交接和已有审核记录，明确哪些已由真人复核。
3. 审 [A1 PR #5](https://github.com/kazamaly50-oss/xinxiu-cup-2026-a/pull/5)：实际合法性实现、库存/预算、整数向外取整与连续域覆盖上界、171个数量组合。不要把历史网格验算视为证明，不把1850元候选视为已证最优。
4. 审 [M1 PR #6](https://github.com/kazamaly50-oss/xinxiu-cup-2026-a/pull/6) 及对齐分支的新复跑报告。全覆盖极端布局为非问题一可行方案，数字不进入正式A1结果汇总。
5. 审 [逐条差异清单](rules-alignment-diff.md)、来源核验与原样归档证明，核对三个核心模块和验证门槛未变。统一规则采用完整塔基入界、允许相切、中心线5m缓冲带，均按来源分类标记。
6. 审1850元候选dt=0.05/0.01逐敌日志；明确区分约0.6HP步长差与击杀裕度。正文必须点名已执行0.01临界复跑及实际结论。
7. 更新 `modeling/ai_ledger.md`，分别填写AI已运行、Hermes审核报告已收到、真人复核、队长验收。审核报告若有新发现，应新增记录，不覆盖旧报告。

执行环境：队长本机 `C:/Users/LENOVO/anaconda3/python.exe`，PuLP2.8.0，种子42，无新增安装。Hermes复核时写明自己机器的真实环境，不把队长路径当成本机路径；缺依赖先报告，不自动安装。

周五选题门槛先复核证据再由队长裁定。此清单未发送给队群或队员。
