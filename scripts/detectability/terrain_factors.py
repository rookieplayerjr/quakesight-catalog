#!/usr/bin/env python3
"""terrain_factors.py — per-event terrain/water/relief coherence pre-factors.

Uses GMT earth_relief (cached) at 02m (~3.7 km) global, sampled in each event's
AOI box (R_signal-scaled). Derives:
  mean_elev_m, relief_m (p95-p5 within box), ocean_frac (elev<0),
  rugged_flag (relief proxy for layover/shadow + tropo turbulence),
  coastal_flag (ocean_frac in 0.05..0.6).

S1 incidence ~39deg: foreslopes > 39deg layover, backslopes > 51deg shadow.
At 3.7 km posting we can't resolve true slope, so relief_m is a regional
ruggedness proxy: <300 m flat (good), 300-1000 hilly (ok), >1000 m mountainous
(layover + strong tropo gradients -> coherence + atm penalty).
"""
import json, math
from pathlib import Path
import numpy as np
import pygmt

def main():
    cat = Path('/Users/z.li/Documents/Projects/quakesight-catalog/catalog.json')
    events = json.loads(cat.read_text())
    events = events.get('events', events) if isinstance(events,dict) else events
    # all events with Mw/depth (we want factors for everything, not just sar_only,
    # so the scorecard is reusable)
    evs = [e for e in events if e.get('Mw') is not None and e.get('epi_lat') is not None]

    print(f"loading earth_relief 02m global ...")
    grid = pygmt.datasets.load_earth_relief(resolution="02m", registration="gridline")
    lats = grid['lat'].values; lons = grid['lon'].values
    Z = grid.values  # (nlat, nlon)
    print(f"  grid {Z.shape}, lon[{lons.min():.1f},{lons.max():.1f}] lat[{lats.min():.1f},{lats.max():.1f}]")

    out=[]
    for e in evs:
        Mw=e['Mw']; lat=e['epi_lat']; lon=e['epi_lon']
        if lon>180: lon-=360
        R_sig=1.5*10**(-2.44+0.59*Mw)            # km
        half=max(R_sig,15.0)                      # AOI half-width km
        dlat=half/111.0
        dlon=half/(111.0*math.cos(math.radians(lat)))
        ila=np.where((lats>=lat-dlat)&(lats<=lat+dlat))[0]
        ilo=np.where((lons>=lon-dlon)&(lons<=lon+dlon))[0]
        if len(ila)<2 or len(ilo)<2:
            # too small box at this res; take nearest 3x3
            ia=np.argmin(np.abs(lats-lat)); io=np.argmin(np.abs(lons-lon))
            ila=np.arange(max(0,ia-1),ia+2); ilo=np.arange(max(0,io-1),io+2)
        box=Z[np.ix_(ila,ilo)].astype(float)
        box=box[np.isfinite(box)]
        if box.size==0:
            out.append({'id':e['event_id'],'mean_elev_m':None}); continue
        ocean_frac=float(np.mean(box<0))
        land=box[box>=-5]
        if land.size>=3:
            relief=float(np.percentile(land,95)-np.percentile(land,5))
            mean_elev=float(np.mean(land))
        else:
            relief=0.0; mean_elev=float(np.mean(box))
        rugged='flat' if relief<300 else 'hilly' if relief<1000 else 'mountainous'
        coastal = 0.05<ocean_frac<0.6
        out.append({'id':e['event_id'],'Mw':Mw,'lat':lat,'lon':lon,
                    'mean_elev_m':round(mean_elev),'relief_m':round(relief),
                    'ocean_frac':round(ocean_frac,2),'rugged':rugged,
                    'coastal':bool(coastal)})
    op=Path('terrain_factors.json'); op.write_text(json.dumps(out,indent=1))
    # summary
    from collections import Counter
    rc=Counter(r.get('rugged') for r in out if r.get('rugged'))
    print(f"\n{len(out)} events. rugged: {dict(rc)}")
    print(f"ocean_frac>0.6 (mostly water): {sum(1 for r in out if (r.get('ocean_frac') or 0)>0.6)}")
    print(f"coastal: {sum(1 for r in out if r.get('coastal'))}")
    print(f"saved {op}")

if __name__=='__main__':
    main()
