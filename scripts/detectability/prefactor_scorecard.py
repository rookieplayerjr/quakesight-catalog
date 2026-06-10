#!/usr/bin/env python3
"""prefactor_scorecard.py — full per-event InSAR quality pre-factor checking.

Two independent axes:
  SIGNAL  = peak LOS SNR (Okada, from singlepair_eval.json)
  COHER   = koppen_base x terrain x snow  (will the phase be coherent at all)

Decision (2-D):
  GO            SNR>=3   AND COHER>=0.55      single-pair should resolve
  MARGINAL      SNR>=1.5 AND COHER>=0.35      try single-pair, lower expectation
  STACK_ONLY    SNR<1.5  AND COHER>=0.55      signal buried but ground coherent -> stacking viable
  NO_GO         COHER<0.35  OR (SNR<1.5 AND COHER<0.55)   decorrelated / hopeless

Reason codes flag the dominant limiter per event.
"""
import json, math
from datetime import datetime
from pathlib import Path
import numpy as np, rasterio, pygmt

BASE = Path('/Users/z.li/Documents/Projects/quakesight-catalog')
HERE = BASE/'scripts'/'detectability'

# Koppen 30-class -> InSAR coherence base (temporal-decorrelation prior)
KOPPEN_BASE = {
 1:0.10,2:0.12,3:0.22,        # A tropical (Af,Am,Aw)
 4:0.95,5:0.93,6:0.82,7:0.80, # B arid (BWh,BWk,BSh,BSk) - BEST
 8:0.70,9:0.68,10:0.62,       # Cs mediterranean
 11:0.48,12:0.46,13:0.42,     # Cw
 14:0.40,15:0.38,16:0.36,     # Cf humid temperate
 17:0.58,18:0.56,19:0.50,20:0.48, # Ds
 21:0.52,22:0.50,23:0.46,24:0.44, # Dw
 25:0.46,26:0.44,27:0.40,28:0.38, # Df
 29:0.30,30:0.05,             # ET, EF
}
KOPPEN_LETTER = {**{i:'A' for i in (1,2,3)},**{i:'B' for i in (4,5,6,7)},
 **{i:'C' for i in range(8,17)},**{i:'D' for i in range(17,29)},29:'E',30:'E'}

def terrain_factor(relief_m, ocean_frac):
    if relief_m is None: return 0.7, 'unknown'
    if relief_m<300: tf,tag=1.00,'flat'
    elif relief_m<1000: tf,tag=0.85,'hilly'
    elif relief_m<2000: tf,tag=0.62,'mountainous'
    else: tf,tag=0.42,'very_rugged'
    if ocean_frac and ocean_frac>0.6:
        tf*=max(0.15,1-ocean_frac); tag='offshore'
    return tf, tag

def snow_factor(koppen_letter, lat, month):
    """Snow penalty for D/E zones during local cold season (pair spans event)."""
    if koppen_letter not in ('D','E') or month is None:
        return 1.0, None
    # cold season months by hemisphere
    nh_cold = month in (11,12,1,2,3)
    sh_cold = month in (5,6,7,8,9)
    cold = nh_cold if lat>=0 else sh_cold
    if koppen_letter=='E':
        return (0.25 if cold else 0.55), ('snow_season' if cold else 'cold_zone')
    # D zone
    if cold:
        return 0.35, 'snow_season'
    return 0.90, None

def main():
    cat = json.loads((BASE/'catalog.json').read_text())
    events = cat.get('events',cat) if isinstance(cat,dict) else cat
    snr = {r['id']:r for r in json.loads((HERE/'singlepair_eval.json').read_text())}

    # sar_only bucket
    sar_ids=set()
    for e in events:
        du=e.get('data_used') or []
        if e.get('result') and du: continue
        if any(d.get('status')=='ready' for d in du): continue
        if not du or all(d.get('status') in ('skipped','failed','no_coverage',None) for d in du):
            sar_ids.add(e['event_id'])

    kr = rasterio.open(HERE/'1991_2020'/'koppen_geiger_0p1.tif')
    kz = kr.read(1)
    def koppen_at(lat,lon):
        col,row = ~kr.transform*(lon,lat)
        r,c=int(row),int(col)
        if 0<=r<kz.shape[0] and 0<=c<kz.shape[1]:
            v=int(kz[r,c])
            if v==0:  # nodata (water) - sample 3x3 for nearest land
                w=kz[max(0,r-2):r+3,max(0,c-2):c+3]; w=w[w>0]
                v=int(np.bincount(w).argmax()) if w.size else 0
            return v
        return 0

    out=[]
    for e in events:
        eid=e['event_id']; Mw=e.get('Mw'); lat=e.get('epi_lat'); lon=e.get('epi_lon')
        if Mw is None or lat is None: continue
        if lon>180: lon-=360
        # month
        month=None
        ts=e.get('origin_utc')
        if ts:
            try: month=datetime.fromisoformat(ts.replace('Z','+00:00')).month
            except Exception: pass
        # terrain (15s region)
        half=max(1.5*10**(-2.44+0.59*Mw),15.0)
        dlat=half/111.0; dlon=half/(111.0*math.cos(math.radians(lat)))
        try:
            g=pygmt.datasets.load_earth_relief(resolution="15s",
                  region=[lon-dlon,lon+dlon,lat-dlat,lat+dlat])
            z=g.values.astype(float); fin=z[np.isfinite(z)]
            ocean_frac=float(np.mean(z<0)) if fin.size else 0.0
            land=z[(z>=-5)&np.isfinite(z)]
            relief=float(np.percentile(land,95)-np.percentile(land,5)) if land.size>3 else 0.0
        except Exception:
            relief=None; ocean_frac=0.0
        # koppen
        kc=koppen_at(lat,lon); kl=KOPPEN_LETTER.get(kc,'?')
        kbase=KOPPEN_BASE.get(kc,0.4)
        tf,ttag=terrain_factor(relief,ocean_frac)
        sf,stag=snow_factor(kl,lat,month)
        coher=round(kbase*tf*sf,3)
        s=snr.get(eid,{}); SNR=s.get('snr'); peak=s.get('peak_cm')
        # decision
        reasons=[]
        if kl=='A': reasons.append('tropical_veg')
        if stag=='snow_season': reasons.append('snow_season')
        if ttag in ('mountainous','very_rugged'): reasons.append('rugged_layover')
        if ttag=='offshore': reasons.append('offshore')
        if SNR is not None and SNR<1.5: reasons.append('weak_signal')
        if SNR is None:
            decision='UNKNOWN'
        elif coher<0.35:
            decision='NO_GO'
        elif SNR>=3 and coher>=0.55:
            decision='GO'
        elif SNR>=1.5 and coher>=0.35:
            decision='MARGINAL'
        elif SNR<1.5 and coher>=0.55:
            decision='STACK_ONLY'
        else:
            decision='NO_GO'
        out.append({'id':eid,'Mw':Mw,'depth_km':e.get('depth_km'),'lat':round(lat,2),'lon':round(lon,2),
                    'month':month,'koppen':kc,'kletter':kl,'kbase':kbase,
                    'relief_m':round(relief) if relief is not None else None,'ocean_frac':round(ocean_frac,2),
                    'terrain':ttag,'snow':stag,'coher':coher,
                    'peak_cm':peak,'snr':SNR,'decision':decision,
                    'reasons':reasons,'sar_only':eid in sar_ids})
    kr.close()
    (HERE/'prefactor_scorecard.json').write_text(json.dumps(out,indent=1))

    # report on sar_only
    so=[r for r in out if r['sar_only']]
    from collections import Counter
    dec=Counter(r['decision'] for r in so)
    print(f"=== sar_only ({len(so)}) pre-factor decisions ===")
    for k in ['GO','MARGINAL','STACK_ONLY','NO_GO','UNKNOWN']:
        print(f"  {k:11s}: {dec.get(k,0)}")
    print("\nNO_GO reason tally (sar_only):")
    rc=Counter()
    for r in so:
        if r['decision']=='NO_GO':
            for x in r['reasons']: rc[x]+=1
    for k,v in rc.most_common(): print(f"  {k}: {v}")
    print("\nClimate (Köppen letter) of sar_only:")
    for k,v in Counter(r['kletter'] for r in so).most_common():
        print(f"  {k}: {v}")
    print(f"\nsaved prefactor_scorecard.json ({len(out)} total events)")

if __name__=='__main__':
    main()
