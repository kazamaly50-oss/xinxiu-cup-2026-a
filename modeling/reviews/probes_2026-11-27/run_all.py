"""Hermes 审核复跑器：在抽出的对齐分支副本里跑 Codex 的全部入口，输出另存到 out/，不碰仓库。"""
import json, subprocess, sys, time, platform, datetime, os
PY = sys.executable
ROOT = r"D:\Hermes\cache\scratch\rev27\align"
OUT = r"D:\Hermes\cache\scratch\rev27\out"
jobs = {
 "geometry":  ["geometry.py"],
 "coverage":  ["coverage.py"],
 "simulate":  ["simulate.py"],
 "a1_tests":  ["-m", "unittest", "-v", "test_a1_verification"],
 "a1_bounds": ["a1_bounds.py"],
 "a1_candidate": ["verify_a1.py", "results/a1-candidate.json"],
 "a1_candidate_center_edge": ["verify_a1.py", "results/a1-candidate.json", "--map-boundary", "center_in_map", "--distance-basis", "edge"],
 "m1": ["validate_t12.py", "--output", os.path.join(OUT, "T1.2-hermes.json")],
}
import numpy
env = {"解释器": PY, "Python": platform.python_version(), "numpy": numpy.__version__, "系统": platform.platform()}
try:
    import pulp; env["pulp"] = pulp.__version__
except Exception as e:
    env["pulp"] = f"未安装（{e}）"
rec = {"时间": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "环境": env, "执行": {}}
for name, args in jobs.items():
    t0 = time.perf_counter()
    p = subprocess.run([PY, "-X", "utf8", "-B", *args], cwd=ROOT, capture_output=True)
    dt = time.perf_counter() - t0
    so, se = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    open(os.path.join(OUT, name + ".stdout.txt"), "w", encoding="utf-8", newline="\n").write(so.replace("\r\n", "\n"))
    open(os.path.join(OUT, name + ".stderr.txt"), "w", encoding="utf-8", newline="\n").write(se.replace("\r\n", "\n"))
    rec["执行"][name] = {"argv": args, "退出码": p.returncode, "秒": round(dt, 3), "stdout字节": len(p.stdout), "stderr尾": se.replace("\r\n", "\n")[-400:]}
    print(name, "exit", p.returncode, f"{dt:.2f}s")
json.dump(rec, open(os.path.join(OUT, "run_receipt.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(env, ensure_ascii=False))
