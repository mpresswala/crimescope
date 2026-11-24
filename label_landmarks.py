#!/usr/bin/env python3
"""Label generic police.uk snap points ("On or near Supermarket", "Parking Area", ...)
by clustering their coordinates across all snapshots and reverse-geocoding each
cluster centre with OSM Nominatim. Writes data/landmark_labels.json:
  { "<lat4>,<lng4>": {"label": "...", "kind": "..."} }
Nominatim usage policy: 1 req/s + honest User-Agent. Clusters are few (~dozens).
"""
import json, glob, os, time, urllib.request, urllib.parse, math

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data", "landmark_labels.json")
GENERIC_WORDS = ["Supermarket", "Parking Area", "Petrol Station", "Shopping Area",
                 "Restaurant/Cafe", "Bank", "Public House", "Hotel", "Leisure Centre",
                 "Hospital", "University/College", "Bus or train station", "Park",
                 "Retail Park", "Speed Camera", "Bike Shop"]

def is_generic(street):
    return street.startswith("On or near ") and street[len("On or near "):] in GENERIC_WORDS

def collect():
    pts = {}   # rounded-key -> {lat/lng sums, n, street}
    for f in glob.glob(os.path.join(BASE, "data", "*.json")):
        if f.endswith(("areas.json", "landmark_labels.json")): continue
        d = json.load(open(f))
        for r in d["records"]:
            if not is_generic(r["street"]): continue
            # cluster grid ~100 m (0.001 deg lat ≈ 111 m; 0.0015 deg lng ≈ 104 m at lat 51)
            key = (round(r["lat"] * 1000), round(r["lng"] * 1500))
            p = pts.setdefault(key, {"lat": 0.0, "lng": 0.0, "n": 0, "streets": {}})
            p["lat"] += r["lat"]; p["lng"] += r["lng"]; p["n"] += 1
            p["streets"][r["street"]] = p["streets"].get(r["street"], 0) + 1
    return pts

def nominatim(lat, lng):
    q = urllib.parse.urlencode({
        "format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lng:.5f}",
        "zoom": 17, "addressdetails": 1,
    })
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/reverse?{q}",
        headers={"User-Agent": "CrimeScope/1.0 (personal crime dashboard; contact: mpresswala)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except Exception as e:
            print(f"  retry {attempt+1}: {e}", flush=True)
            time.sleep(3 * (attempt + 1))
    return None

def humanise(j, generic_word):
    """Pick the most informative name from a Nominatim reverse result."""
    if not j or j.get("error"): return None, None
    a = j.get("address", {}) or {}
    name = j.get("name") or ""
    kind = j.get("type", "") or ""
    suburb = a.get("suburb") or a.get("city_district") or a.get("town") or a.get("village") or a.get("hamlet") or a.get("city")
    if kind in ("residential","unclassified","tertiary","secondary","primary","service",
                "footway","pedestrian","road","living_street","residential,"):
        # nearest feature was a road -> keep the generic POI type for context
        lbl = f"{generic_word} — {name}" + (f", {suburb}" if suburb else "")
        return lbl, "road"
    if name:
        return name + (f", {suburb}" if suburb and name.lower() not in (suburb or '').lower() else ""), kind
    rd = a.get("road") or a.get("pedestrian")
    if rd and suburb:
        return f"{generic_word} — {rd}, {suburb}", kind
    if rd:  return f"{generic_word} — {rd}", kind
    if suburb: return f"{generic_word} — {suburb}", kind
    return None, None

def main():
    pts = collect()
    print(f"{len(pts)} generic snap-point clusters to label", flush=True)
    labels = {}
    for i, ((rlat, rlng), p) in enumerate(sorted(pts.items(), key=lambda kv: -kv[1]["n"])):
        lat, lng = p["lat"] / p["n"], p["lng"] / p["n"]
        word = max(p["streets"], key=p["streets"].get)[len("On or near "):]
        j = nominatim(lat, lng)
        lbl, kind = humanise(j, word)
        if not lbl:
            lbl = f"{word} (near {lat:.3f},{lng:.3f})"
        key = f"{round(lat,4)},{round(lng,4)}"
        labels[key] = {"label": lbl, "kind": kind or word.lower(), "n": p["n"], "word": word}
        print(f"  [{i+1}/{len(pts)}] {p['n']:4}x {word:15s} -> {lbl}", flush=True)
        time.sleep(1.1)   # Nominatim policy
    with open(OUT, "w") as f:
        json.dump(labels, f, indent=1)
    print(f"Wrote {OUT} ({len(labels)} labels)", flush=True)

if __name__ == "__main__":
    main()
