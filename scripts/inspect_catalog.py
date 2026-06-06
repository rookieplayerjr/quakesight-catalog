import json

catalog_path = "/Users/z.li/Documents/Projects/quakesight-catalog/catalog.json"

with open(catalog_path) as f:
    data = json.load(f)

if isinstance(data, dict):
    print("KEYS:", list(data.keys())[:20])
    for k in ["events", "catalog", "data"]:
        if k in data:
            print(f"Found list under '{k}', len=", len(data[k]) if hasattr(data[k], '__len__') else '?')
            sample = data[k][0] if isinstance(data[k], list) and data[k] else None
            if sample:
                print("SAMPLE KEYS:", list(sample.keys()) if isinstance(sample, dict) else sample)
                print("SAMPLE:", json.dumps(sample, indent=2)[:3000])
            break
elif isinstance(data, list):
    print("LIST len=", len(data))
    print("SAMPLE KEYS:", list(data[0].keys()) if isinstance(data[0], dict) else None)
    print("SAMPLE:", json.dumps(data[0], indent=2)[:3000])
