import json
d = json.load(open(r"D:\Hermes\cache\scratch\rev27\align\results\a1-verification-aligned.json", encoding="utf-8-sig"))
for k in ["日期", "执行代码提交", "环境", "假设及来源", "临界复跑说明", "指标区分", "原候选与原报告保留", "历史逐敌结果完全一致", "逐敌血量差", "四种状态"]:
    print(k, "=>", json.dumps(d[k], ensure_ascii=False)[:900])
r = {x["步长秒"]: x for x in d["layout_check"]["复跑"]}
for dt, x in r.items():
    tot = sum(e["累计承伤"] for e in x["逐敌结果"]); print(f"dt={dt}: 总伤害 {tot:.2f} HP, 漏怪 {x['漏怪数']}, 击杀 {[e['编号'] for e in x['逐敌结果'] if e['结果']=='击杀']}, 漏怪者最小剩余 {min(e['剩余血量'] for e in x['逐敌结果'] if e['结果']=='漏怪')}")
h = json.load(open(r"D:\Hermes\cache\scratch\rev27\align\results\a1-verification.json", encoding="utf-8-sig"))
print("历史报告 date/python/numpy:", h["date"], h["python"], h["numpy"]); print("历史 damage_bound == aligned damage_bound:", h["damage_bound"] == d["damage_bound"])
