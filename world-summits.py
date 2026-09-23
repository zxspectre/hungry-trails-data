#!/usr/bin/env python3
"""
Every named summit on Earth, as one gzipped TSV, fetched from Overpass box by
box.

    tools/world-summits.py <work dir>            # fetch, resumable
    tools/world-summits.py <work dir> --merge    # write <work dir>/summits.tsv.gz

Why box by box: one global query was refused by overpass-api.de ("too busy")
and returned nothing after eight minutes from kumi.systems (2026-09-23). 
10-degree box is asked for; a box the server refuses or times out on is split
into four and those are asked for instead, down to 1.25 degrees. Each box that
answers is written to its own file, so a run that dies resumes where it
stopped, and the server is asked one box at a time with a pause between —
this is run once, by hand, not by every phone.

The CSV header is asked for, so an answer that is truly empty (open ocean) has
one line and an answer the server cut short has none. Without that the two
look the same, and a busy afternoon would pass for an empty continent.

Columns: id, lat, lon, name, ele, prominence, name:en, int_name, alt_name.
Data © OpenStreetMap contributors, ODbL 1.0.
"""
import gzip
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Three public instances, taken in turn when one is busy: on 2026-09-23 the
# main one answered 504 to most requests, and waiting a minute each time put
# the world days away.
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
AGENT = "HungryTrails/Android (world summits, one-off build)"
COLUMNS = '::id,::lat,::lon,name,ele,prominence,"name:en",int_name,alt_name'
START_DEG = 30.0
MIN_DEG = 0.9375
PAUSE_S = 3
BUSY_PAUSE_S = 10
turn = 0


def query(s, w, n, e):
    box = f"{s},{w},{n},{e}"
    return (f"[out:csv({COLUMNS};true)][timeout:180];"
            f"(node[natural=peak][name]({box});node[natural=volcano][name]({box}););out;")


def fetch(s, w, n, e):
    """The lines for one box, header first, or None when it must be split."""
    global turn
    body = urllib.parse.urlencode({"data": query(s, w, n, e)}).encode()
    for attempt in range(2 * len(ENDPOINTS)):
        endpoint = ENDPOINTS[turn % len(ENDPOINTS)]
        request = urllib.request.Request(endpoint, data=body, headers={"User-Agent": AGENT})
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as err:
            if err.code in (429, 504):
                print(f"  {endpoint.split('/')[2]} busy ({err.code})", flush=True)
                turn += 1
                time.sleep(BUSY_PAUSE_S)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as err:
            print(f"  {endpoint.split('/')[2]}: {err}", flush=True)
            turn += 1
            time.sleep(BUSY_PAUSE_S)
            continue
        if not text.startswith("@id\t"):
            # No header: cut short, or an error page in place of CSV.
            print(f"  {endpoint.split('/')[2]}: no header ({text[:60]!r})", flush=True)
            turn += 1
            time.sleep(BUSY_PAUSE_S)
            continue
        return text.splitlines()
    return None


def boxes(size):
    lat = -90.0
    while lat < 90.0:
        lon = -180.0
        while lon < 180.0:
            yield lat, lon, min(lat + size, 90.0), min(lon + size, 180.0)
            lon += size
        lat += size


def name(s, w, n, e):
    return f"{s:+08.3f}_{w:+09.3f}_{n:+08.3f}_{e:+09.3f}.tsv"


def run(work):
    os.makedirs(work, exist_ok=True)
    pending = list(boxes(START_DEG))
    while pending:
        s, w, n, e = pending.pop(0)
        path = os.path.join(work, name(s, w, n, e))
        if os.path.exists(path):
            continue
        print(f"{time.strftime('%H:%M:%S')} {s},{w},{n},{e} ({len(pending)} left)", flush=True)
        lines = fetch(s, w, n, e)
        if lines is None:
            if n - s <= MIN_DEG:
                sys.exit(f"{s},{w},{n},{e} will not answer even at {MIN_DEG} degrees")
            mid_lat, mid_lon = (s + n) / 2, (w + e) / 2
            pending[:0] = [(s, w, mid_lat, mid_lon), (s, mid_lon, mid_lat, e),
                           (mid_lat, w, n, mid_lon), (mid_lat, mid_lon, n, e)]
            print("  split", flush=True)
            continue
        with open(path + ".part", "w", encoding="utf-8") as out:
            out.write("\n".join(lines[1:]) + ("\n" if len(lines) > 1 else ""))
        os.rename(path + ".part", path)
        print(f"  {len(lines) - 1} summits", flush=True)
        time.sleep(PAUSE_S)


def merge(work):
    seen = set()
    count = 0
    target = os.path.join(work, "summits.tsv.gz")
    with gzip.open(target, "wt", encoding="utf-8", compresslevel=9) as out:
        for file in sorted(f for f in os.listdir(work) if f.endswith(".tsv")):
            with open(os.path.join(work, file), encoding="utf-8") as src:
                for line in src:
                    node = line.split("\t", 1)[0]
                    if not node.isdigit() or node in seen:
                        continue  # a node on a box edge is in both
                    seen.add(node)
                    out.write(line if line.endswith("\n") else line + "\n")
                    count += 1
    print(f"{count} summits, {os.path.getsize(target)} bytes -> {target}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if "--merge" in sys.argv:
        merge(sys.argv[1])
    else:
        run(sys.argv[1])
