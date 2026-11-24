#!/usr/bin/env python3
"""CrimeScope data builder — pulls street-level crime from data.police.uk
into static JSON snapshots the site can serve (the public API rate-limits
live browser scanning hard).  OGL v3 data.

Usage: python3 build_data.py                # all areas in AREAS below
       python3 build_data.py "Slug" lat lng [radius_km]   # one area
Output: data/<slug>.json + data/areas.json manifest.
"""
import json, math, os, sys, time, urllib.request, urllib.error, datetime, re

# label, lat, lng, radius_km
AREAS = [
    ("Orpington", 51.3717,  0.0919, 5.0),
    ("Bromley",   51.4030, -0.0090, 5.0),
    ("Beckenham", 51.4110,  0.0090, 5.0),
    ("Chislehurst", 51.4010, 0.0750, 4.0),
    ("Petts Wood", 51.3780, 0.0990, 3.5),
]
N_MONTHS = 13                     # months of history (2-month lag applied)
CATEGORY = "all-crime"            # street-level endpoint includes every category
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def slug(label): return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")

# ~1.2 km spaced sample points, capped so total requests stay polite
def sample_grid(lat, lng, radius, spacing=1.2, cap=10):
    pts = [(lat, lng)]
    d_lat = spacing / 111.32
    d_lng = spacing / (69.5 * math.cos(math.radians(lat)))
    ring = 1
    while len(pts) < cap:
        r = ring * spacing
        if r > radius:
            break
        n = max(6, int(2 * math.pi * r / spacing))
        for i in range(n):
            if len(pts) >= cap:
                break
            a = 2 * math.pi * i / n
            pts.append((lat + r * d_lat * math.sin(a), lng + r * d_lng * math.cos(a)))
        ring += 1
    return pts

def recent_months(n):
    out, d = [], datetime.date.today().replace(day=1)
    d = (d - datetime.timedelta(days=1)).replace(day=1)   # 2-month lag start
    for _ in range(n):
        out.append(d.isoformat()[:7])
        d = (d - datetime.timedelta(days=1)).replace(day=1)
    return out

def fetch(url, tries=6):
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "CrimeScope/1.0 (personal dashboard)"}), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 3 * (t + 1)
                print(f"  429, backing off {wait}s", flush=True)
                time.sleep(wait)
                continue
            if e.code == 404:
                return []           # month not published yet
            print(f"  HTTP {e.code}", flush=True)
        except Exception as e:
            print(f"  err {e}", flush=True)
        time.sleep(2)
    return []

def build_area(label, lat, lng, radius):
    CENTER = (lat, lng)
    grid = sample_grid(lat, lng, radius)
    months = recent_months(N_MONTHS)
    print(f"{label}: {len(grid)} points x {len(months)} months = {len(grid)*len(months)} requests", flush=True)
    seen, recs = set(), []
    done = 0
    total = len(grid) * len(months)
    for m in months:
        for glat, glng in grid:
            url = f"https://data.police.uk/api/crimes-street/{CATEGORY}?lat={glat:.5f}&lng={glng:.5f}&date={m}"
            rows = fetch(url)
            for c in rows:
                loc = c.get("location") or {}
                if not loc.get("latitude"):
                    continue
                la, lo = float(loc["latitude"]), float(loc["longitude"])
                d = math.hypot((la - CENTER[0]) * 111.32,
                               (lo - CENTER[1]) * 69.5 * math.cos(math.radians(CENTER[0])))
                if d > radius:
                    continue
                key = c.get("persistent_id") or c.get("id") or f"{c['month']}|{c['category']}|{loc.get('street',{}).get('name')}"
                if key in seen:
                    continue
                seen.add(key)
                oc = c.get("outcome_status") or {}
                recs.append({
                    "id": key, "month": c["month"], "cat": c["category"],
                    "street": (loc.get("street") or {}).get("name", ""),
                    "lat": la, "lng": lo, "d": round(d, 2),
                    "out": oc.get("category"), "odate": oc.get("date"),
                })
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{total} · {len(recs)} unique", flush=True)
            time.sleep(1.2)   # stay under the rate limiter
    out = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
           "place": label, "center": [round(CENTER[0], 5), round(CENTER[1], 5)],
           "radius": radius, "months": sorted({r["month"] for r in recs}, reverse=True),
           "count": len(recs), "records": recs}
    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, slug(label) + ".json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Wrote {path}: {len(recs)} records, {out['months'][-1]} → {out['months'][0]}", flush=True)
    return out

def main():
    if len(sys.argv) >= 4:                      # single area: label lat lng [radius]
        areas = [(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]),
                  float(sys.argv[4]) if len(sys.argv) > 4 else 5.0)]
    else:
        areas = AREAS
    manifest = []
    for label, lat, lng, radius in areas:
        out = build_area(label, lat, lng, radius)
        manifest.append({"label": out["place"], "file": slug(out["place"]) + ".json",
                         "generated": out["generated"], "count": out["count"]})
        time.sleep(3)
    with open(os.path.join(OUTDIR, "areas.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("Wrote areas.json:", ", ".join(a["label"] for a in manifest), flush=True)

if __name__ == "__main__":
    main()
