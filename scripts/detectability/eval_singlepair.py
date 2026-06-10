#!/usr/bin/env python3
"""eval_singlepair.py — per-event single-pair InSAR detectability assessment.

For each sar_only event, estimate the THEORETICAL peak surface LOS displacement
using:
  - Wells-Coppersmith (1994) L/W scaling from Mw
  - Moment balance for average slip: M0 = mu * L * W * u
  - Okada (1992) rectangular dislocation forward, fault CENTER at catalog depth
  - Peak |LOS| over a grid above the source

Then compare peak vs single-pair noise floor (sigma_atm ~0.5 cm typical S1 C-band).
SNR = peak / sigma. SNR>=3 → detectable single-pair; 1.5-3 marginal; <1.5 buried.

The faulting_class field sets rake (SS=0, RV=90, NM=-90). Strike fixed at 0,
dip 60 for dip-slip / 90 for strike-slip — peak amplitude is what matters, not
orientation. We take the WORST (deepest detectability) over a few dip choices.
"""
import json, math
from pathlib import Path
import numpy as np
from okada_wrapper import dc3dwrapper

MU = 3.3e10       # shear modulus Pa
LAMBDA = 3.3e10   # Lame
ALPHA = (LAMBDA + MU) / (LAMBDA + 2*MU)
SIGMA_ATM = 0.5   # cm, single-pair C-band noise floor (good conditions)

# LOS unit vector (S1, inc~39deg, asc heading) — generic; peak is dominated by
# vertical so exact look vector matters little for an order-of-mag estimate.
INC = math.radians(39.0)
LOS = np.array([-math.sin(INC)*math.cos(math.radians(-12)),  # E
                -math.sin(INC)*math.sin(math.radians(-12)),  # N
                 math.cos(INC)])                              # U

def wc_dims(Mw):
    L = 10**(-2.44 + 0.59*Mw)   # km
    W = 10**(-1.01 + 0.32*Mw)   # km
    return L, W

def avg_slip(Mw, L_km, W_km):
    M0 = 10**(1.5*Mw + 9.1)     # N·m
    A = (L_km*1e3)*(W_km*1e3)   # m^2
    return M0 / (MU * A)        # m

def peak_los(Mw, depth_km, rake_deg, dip_deg):
    """Peak |LOS| (cm) on surface for fault centered at depth_km."""
    L, W = wc_dims(Mw)
    u = avg_slip(Mw, L, W)
    # Okada: fault center depth = depth_km. dc3d uses fault reference at lower
    # edge depth via DEPTH param + dip. We place observation grid above source.
    dip = math.radians(dip_deg)
    # depth of fault CENTROID
    cd = depth_km
    # grid (km) spanning +-2*L around epicenter
    span = max(2*L, 4*W, 10.0)
    xs = np.linspace(-span, span, 81)
    ys = np.linspace(-span, span, 81)
    rake = math.radians(rake_deg)
    ss = u*math.cos(rake)   # strike-slip comp
    ds = u*math.sin(rake)   # dip-slip comp
    half_L = L/2.0
    half_W = W/2.0
    peak = 0.0
    for x in xs:
        for y in ys:
            # dc3dwrapper(alpha, [x,y,z], depth, dip, [al1,al2],[aw1,aw2],[disl1,disl2,disl3])
            try:
                success, uu, grad = dc3dwrapper(
                    ALPHA, [x, y, 0.0], cd, dip_deg,
                    [-half_L, half_L], [-half_W, half_W],
                    [ss, ds, 0.0])
            except Exception:
                continue
            if success != 0:
                continue
            los = abs(np.dot(uu, LOS))  # m
            if los > peak:
                peak = los
    return peak*100.0  # cm

def main():
    cat = Path('/Users/z.li/Documents/Projects/quakesight-catalog/catalog.json')
    events = json.loads(cat.read_text())
    events = events.get('events', events) if isinstance(events, dict) else events

    # rebuild sar_only bucket (same logic as before)
    sar_only = []
    for e in events:
        du = e.get('data_used') or []
        has_ready = any(d.get('status')=='ready' for d in du) if du else False
        has_result = bool(e.get('result'))
        if has_result and du: continue
        if has_ready: continue
        if not du or all(d.get('status') in ('skipped','failed','no_coverage',None) for d in du):
            sar_only.append(e)

    rake_by_class = {'SS':0.0,'strike-slip':0.0,'RV':90.0,'reverse':90.0,
                     'thrust':90.0,'NM':-90.0,'normal':-90.0}
    out = []
    for e in sar_only:
        Mw = e.get('Mw'); dep = e.get('depth_km')
        if Mw is None or dep is None: continue
        fc = (e.get('faulting_class') or '').lower()
        rake = next((v for k,v in rake_by_class.items() if k.lower() in fc), 90.0)
        dip = 90.0 if abs(rake) < 1 else 60.0
        pk = peak_los(Mw, dep, rake, dip)
        out.append({'id':e['event_id'],'Mw':Mw,'depth_km':dep,'fc':fc or '?',
                    'peak_cm':round(pk,2),'snr':round(pk/SIGMA_ATM,1)})
    out.sort(key=lambda r:-r['peak_cm'])

    # bins
    det = [r for r in out if r['snr']>=3]
    mar = [r for r in out if 1.5<=r['snr']<3]
    bur = [r for r in out if r['snr']<1.5]
    print(f"=== Single-pair detectability ({len(out)} sar_only events, sigma={SIGMA_ATM} cm) ===\n")
    print(f"DETECTABLE  (SNR>=3, peak>={3*SIGMA_ATM:.1f} cm): {len(det):3d}  ({100*len(det)/len(out):.0f}%)")
    print(f"MARGINAL    (1.5<=SNR<3):                        {len(mar):3d}  ({100*len(mar)/len(out):.0f}%)")
    print(f"BURIED      (SNR<1.5, needs stacking):           {len(bur):3d}  ({100*len(bur)/len(out):.0f}%)")

    # peak distribution
    pks = np.array([r['peak_cm'] for r in out])
    print(f"\npeak_cm: min={pks.min():.2f} p25={np.percentile(pks,25):.2f} "
          f"median={np.median(pks):.2f} p75={np.percentile(pks,75):.2f} max={pks.max():.2f}")

    # cross-tab: detectable by Mw band
    print("\nDETECTABLE breakdown by Mw:")
    from collections import Counter
    cb = Counter()
    for r in det:
        mw=r['Mw']
        b = '<5.5' if mw<5.5 else '5.5-6.0' if mw<6.0 else '6.0-6.5' if mw<6.5 else '>=6.5'
        cb[b]+=1
    for k in ['<5.5','5.5-6.0','6.0-6.5','>=6.5']:
        print(f"  {k}: {cb.get(k,0)}")

    print("\nTop 20 most-detectable:")
    for r in out[:20]:
        print(f"  {r['id']:14s} Mw{r['Mw']:.1f} {r['depth_km']:5.1f}km {r['fc']:12s} "
              f"peak={r['peak_cm']:5.2f}cm SNR={r['snr']:4.1f}")

    # save
    op = Path('/Users/z.li/Documents/Projects/quakesight-catalog/scripts/detectability/singlepair_eval.json')
    op.write_text(json.dumps(out, indent=1))
    print(f"\nsaved {op}")

if __name__=='__main__':
    main()
