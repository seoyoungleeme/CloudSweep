import json
for path in ["sample/season1/L1-004/cost_report.json", "sample/season1/L2-019/cost_report.json"]:
    print(f"=== {path} ===")
    with open(path, encoding="utf-8-sig") as f:
        d = json.load(f)
    months = d.get("monthly_data") or d.get("months") or []
    for m in months:
        for s in m.get("services", []):
            print(f"  {s.get('service')}: ${s.get('spend_usd')}")
