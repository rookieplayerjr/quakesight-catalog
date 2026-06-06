import json, os, math

catalog_path = "/Users/z.li/Documents/Projects/quakesight-catalog/catalog.json"
base = "/Users/z.li/Documents/Projects/Quakesight"

with open(catalog_path) as f:
    data = json.load(f)

events = data["events"]

def peak_est(Mw, depth_km):
    try:
        L_km = 10**(0.59*Mw - 2.44)
        W_km = 10**(0.32*Mw - 1.01)
        slip_cm = (10**(1.5*Mw + 9.1)) / (3e10 * L_km * W_km * 1e6) * 100
        d_top = max(0.1, depth_km - 0.5*W_km*math.sin(math.radians(70)))
        r = d_top / W_km
        if r <= 0.3:
            factor = 0.55
        elif r <= 0.7:
            factor = 0.45 - 0.3*(r - 0.3)
        elif r <= 1.5:
            factor = 0.30 * math.exp(-(r - 0.7))
        else:
            factor = 0.13 * math.exp(-0.5*(r - 1.5))
        return slip_cm * factor * 0.55
    except Exception:
        return None

out = []
for ev in events:
    eid = ev["event_id"]
    rpt = os.path.join(base, eid, "REPORT.html")
    dia = os.path.join(base, eid, "diagnostics_for_agent.json")
    if not (os.path.isfile(rpt) and os.path.isfile(dia)):
        continue
    Mw = ev.get("Mw")
    depth = ev.get("depth_km")
    zone = (ev.get("diagnostics") or {}).get("zone", "UNKNOWN")
    if zone is None:
        zone = "UNKNOWN"
    pk = peak_est(Mw, depth) if (Mw is not None and depth is not None) else None
    out.append({
        "event_id": eid,
        "zone": zone,
        "Mw": Mw,
        "depth_km": depth,
        "peak_est_cm": round(pk, 3) if pk is not None else None,
        "has_report": True,
        "has_diag": True,
    })

# Cap at 250 (by Mw desc)
if len(out) > 250:
    out_sorted = sorted(out, key=lambda x: (x["Mw"] if x["Mw"] is not None else -999), reverse=True)
    out = out_sorted[:250]

counts = {}
for ev in out:
    counts[ev["zone"]] = counts.get(ev["zone"], 0) + 1

print("TOTAL:", len(out))
print("COUNTS:", counts)

result = {"events": out, "counts_by_zone": counts}
with open("/Users/z.li/Documents/Projects/quakesight-catalog/scripts/inventory.json", "w") as f:
    json.dump(result, f)
