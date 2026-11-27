# 建模岗交接摘要（2026-11-26 21:xx，Hermes）

## 目标
- 2026 新秀杯 A 题（塔防布局与资源调度）。建模岗负责：题意拆解、规则口径、审核 Codex 每一层代码（只审不改），并独立提出建模方案。
- 当前阶段：T0.1–T1.1 已审完。下一步是 T1.2（M1 仿真器可信度验收）、T2.x（候选点 / 覆盖 ILP），周五（11/27）验收 M1 和 A1 可达性。

## 约束（铁律与已定版规则）
- 只审不改：审核时不修改 Codex 代码，问题列成清单，由队长裁定。
- 数字单向流动：进论文的数字只能来自 simulate.py 或求解器的实际输出。审核方算出的数只能标“验算值”，用于核对。
- 环境如实申报：每份审核报告开头写明实际解释器和版本。涉及 pulp 的单（T2.2 起）不复跑全量 ILP，改为核对约束覆盖清单、审查字典序实现、用小算例独立验算。
- 规则以原题为准。认为规则有问题时，单独列“规则质疑”上报队长，不得自行更改。
- 已定版规则：
  1. 每步打射程内最近的敌人，集火伤害叠加，超杀不转移；
  2. 血量归零与到达 D 同时发生时，记击杀（归零优先）；
  3. 契约 C1：先判断 s ≥ L，绝不把越界的 s 传给 pos；
  4. 路径总长 2995.850325852031 m；
  5. 塔参数：75/10/100、125/20/250、200/40/600，塔心距路 ≥ 15 m，塔间距 ≥ 20 m；
  6. 问题一口径：N=10，H=1700，v=20，间隔 10 s，M=2000，b=0；
  7. 问题二口径：见审核提示词（原文截断，不完整）。

## 已完成
| 项 | 结论 | 文件 |
|---|---|---|
| 题目拆解（Q1 拆成 7 个子任务）+ 分类 | 完成 | `modeling/planning/parse/problem_parse.json` |
| 规则口径 v1 + 一塔两敌训练例 | 草稿，待复核 | `modeling/rules.md`、`toy_check*.md` |
| T0.1 geometry.py 审核 | 有条件通过，Muse 终验通过；欠账已由 Codex 补齐 | `modeling/reviews/T0.1_geometry_review.md` |
| 审核惯例 R1 / 契约 C1 / 台账 | 完成 | `modeling/review_conventions.md`、`modeling/ai_ledger.md` |
| T0.2 coverage.py + T1.1 simulate.py 审核 | 通过，致命 0、一般 3、建议 3 | `modeling/reviews/T0.2_T1.1_review.md` |
| Git bundle（完整历史） | 已生成并 verify | `C:\Users\123\Desktop\modeling-rules-v1.bundle`（sha256 73f5573d…961f6e） |

## 待办
1. 用户推送 `modeling/rules-v1`（本机无 GitHub 凭据）。推送后执行 `git fetch`，确认 4 个提交已入仓。
2. 队长裁定以下事项：
   - 周五门槛：原约定“0 漏怪”，建议改为“可行最优布局 + 漏怪下界”（规则质疑 Q-1）；
   - Codex 写入 `modeling/rules.md` 造成的目录冲突（一般 #1）；
   - 是否登记契约 C2：布局合法性必须前置检查；
   - 固定步长误差：剩余血量裕度 < 5 HP 时用 dt=0.01 复跑。
3. 索取完整版《A题-Hermes审核提示词-全层通用版》：PDF 在规则 7 处截断，缺约 3396 字。另需《A题-Codex协作提示词模板》和 T1.2 M1 三件套明细入仓。
4. T1.1 终验后补台账。台账目前只记了 T0.1。
5. 下界 16697.9（验算值）需 Codex 用 coverage.py 正式出界并验收，才能进论文。
6. 环境：队规路径 `C:\Users\LENOVO\anaconda3` 在本机不存在；本机 Anaconda 没有 pulp。T2.2 前需确认环境并安装 pulp==2.8。

## 关键文件路径
- 本地仓库：`C:\Users\123\xinxiu-repo`，当前分支 `modeling/rules-v1`，HEAD 为 `0563c1d`。
- 远端被审分支：
  - `origin/codex/t0-1-geometry` @ `c304a08`
  - `origin/codex/t0-2-coverage` @ `167dc62`
  - `origin/codex/t1-1-simulator` @ `09577be`
- 题面：`C:\Users\123\Desktop\A题：守关-塔防游戏中的防御布局与资源调度.pdf`
- 审核提示词（截断）：`C:\Users\123\Desktop\A题-Hermes审核提示词-全层通用版.pdf`；提取文本为 `...\Desktop\A题-Hermes审核提示词-提取文本.txt`
- 审核环境：`D:\AnacondaDownload\Anaconda Navigator\python.exe`（Python 3.14.6，numpy 2.4.6）
- 审核草稿区：`D:\Hermes\cache\scratch\rev11\`。正式探针已复制到 `modeling/reviews/probes_T1.1/`。

## diff 摘要（main..modeling/rules-v1，4 个提交，20 个文件，+1072 行，0 删除）
- `dd5eed0`：rules.md、toy_check、toy_check_answer、planning/、handoff_rules_v1.json
- `0d4961d`：reviews/T0.1_geometry_review.md
- `697b570`：review_conventions.md、ai_ledger.md
- `0563c1d`：reviews/T0.2_T1.1_review.md、probes_T1.1/（ref.py、probe_c1.py、probe_phys.py、probe2.py、bound.py 及其输出）
- 冲突风险：`codex/t1-1-simulator` 也新建了 `modeling/rules.md`，合并时必冲突。

## 报错记录
| 报错 | 原因 | 处理 |
|---|---|---|
| `git push`：could not read Username | 本机无 GitHub 凭据 | 交给用户推送或使用 bundle |
| 早期 clone 404 / Connection reset | 仓库当时为私有；直连 GitHub 被重置 | 仓库已公开；使用代理 `http://127.0.0.1:7897` |
| execute_code NameError（dpath） | 内核重启，跨 cell 的全局变量丢失 | 改用磁盘上的自包含脚本（如 bound.py）；规则已写入审核 skill |
| probe_phys AssertionError | 审核方自己的测试组合超预算（2100 > 2000） | 已修正为 4 小 + 4 中 + 1 大 |
| browser_exec 超时 | 浏览器守护进程无响应 | 未依赖浏览器 |
| 审核提示词截断 | PDF 原文自带 `...[truncated 3396 chars]` | 待重发完整版 |

## 测试命令（在本机审核环境，仓库根目录或抽出的副本目录中运行）
```bash
PY="/d/AnacondaDownload/Anaconda Navigator/python.exe"
git show origin/codex/t1-1-simulator:simulate.py > simulate.py   # geometry.py、coverage.py 同理
"$PY" -X utf8 -B geometry.py      # 期望 2995.850325852031 / (0.0, 0.0) / (2000.0, 2000.0)
"$PY" -X utf8 -B coverage.py      # 期望 straight 150 PASS、outside [] PASS
"$PY" -X utf8 -B simulate.py      # 期望 10 组全部 "通过": true，stdout 与 handoffs/T1.1.json 一致
"$PY" -X utf8 -B probe_c1.py      # C1：恰达终点 / 越过终点，pos 零越界
"$PY" -X utf8 -B probe_phys.py    # toy_check 收敛 + 21 布局与参考比对（约 5 分钟）
"$PY" -X utf8 -B probe2.py        # coverage 独立对照 + 漏怪阈值扫描
"$PY" -X utf8 -B bound.py         # 漏怪下界验算（约 6 秒）
git bundle verify C:/Users/123/Desktop/modeling-rules-v1.bundle
```

## 不要做什么
- 不要修改 Codex 的代码（geometry.py、coverage.py、simulate.py 等）。
- 不要把验算值（16697.9、覆盖长、阈值 1274 等）当作论文数字。
- 不要自行更改已定版规则或周五门槛；只能上报规则质疑。
- 不要拼补审核提示词缺失的 3396 字。
- 不要代输 GitHub 密码或 token，也不要未经用户同意强推。
- 不要依赖跨 execute_code cell 的全局变量。
- 不要把 `C:\Users\LENOVO\...` 当成本机路径，也不要用其他解释器默默替代队规环境；涉及 pulp 的单必须先确认环境。
- 不要把个人身份信息、凭据写进仓库。
