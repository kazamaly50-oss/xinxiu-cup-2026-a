"""把 M1 步长收敛用的三大塔布局（仓库里已有的固定测试布局）按 A1 流程过一遍合法性+两档复跑，只作审核对照。"""
import sys, json
sys.path.insert(0, r"D:\Hermes\cache\scratch\rev27\align")
import verify_a1, validate_t12
ct = validate_t12._convergence_towers()
r = verify_a1.verify_layout(ct)
print("合法性:", r["合法性"]["通过"], r["合法性"]["问题"], "花费", r["合法性"]["总花费元"], "剩余", r["合法性"]["剩余资金元"], "| 状态:", r["状态"])
for run in r["复跑"]:
    print(f"dt={run['步长秒']}: 漏怪 {run['漏怪数']} 击杀 {[e['编号'] for e in run['逐敌结果'] if e['结果']=='击杀']} 剩余 {[round(e['剩余血量'],2) for e in run['逐敌结果']]}")
print("比较:", json.dumps(r["比较"], ensure_ascii=False))
import geometry, math
for x, y, k in ct: print(f"  ({x:.4f},{y:.4f}) {k} 距中心线 {geometry.dist_to_path(x,y):.6f}")
print("  塔间最小距:", min(math.hypot(a[0]-b[0], a[1]-b[1]) for i, a in enumerate(ct) for b in ct[i+1:]))
