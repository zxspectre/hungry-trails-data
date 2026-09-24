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

**Every answer must end in its own count.** The query closes with `out count`,
which Overpass writes as a last row — id 0, the total in a final `::count`
column — only once the query has run to the end, and the total must equal the
rows above it. The header alone is not enough, and that was learned the hard
way (2026-09-23): the 30-degree box over Europe came back as a header and no
rows, a query too big to finish reported as a continent with no mountains,
and the Caucasus beside it the same. A box without its count is split at
once rather than retried: it did not fail for being busy.

Columns: id, lat, lon, name, ele, prominence, name:en, int_name, alt_name.
Data © OpenStreetMap contributors, ODbL 1.0.
"""
import gzip
import http.client
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
COLUMNS = '::id,::lat,::lon,name,ele,prominence,"name:en",int_name,alt_name,::count'
START_DEG = 30.0
MIN_DEG = 0.9375
PAUSE_S = 3
BUSY_PAUSE_S = 10
LONG_WAIT_S = 120
turn = 0


def query(s, w, n, e):
    box = f"{s},{w},{n},{e}"
    return (f"[out:csv({COLUMNS};true)][timeout:180];"
            f"(node[natural=peak][name]({box});node[natural=volcano][name]({box}););out;out count;")


TOO_BIG = "too big"


# Below this a timeout is an overloaded server, not a box too big to finish:
# a degree near Frankfurt timed out at midnight on a server that had answered
# boxes twenty times its size that afternoon.
TIMEOUT_MEANS_BIG_DEG = 4.0


def fetch(s, w, n, e):
    """
    The lines for one box, header first; TOO_BIG when it must be split; None
    when every server was busy, which is a reason to wait, not to split —
    splitting a box the servers were merely too busy for once ran it down to
    the smallest size and stopped the whole build (2026-09-23, near Frankfurt).
    """
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
        except TimeoutError as err:
            # Four minutes without an answer, on a big box, is a box too big
            # to finish — counted as busy, the 30-degree box over Europe was
            # retried for most of an hour. On a small one it is a server
            # having a bad night; see TIMEOUT_MEANS_BIG_DEG.
            print(f"  {endpoint.split('/')[2]}: {err}", flush=True)
            if n - s > TIMEOUT_MEANS_BIG_DEG:
                return TOO_BIG
            turn += 1
            time.sleep(BUSY_PAUSE_S)
            continue
        except (ConnectionError, http.client.HTTPException) as err:
            # A connection reset half way through an answer — the build died
            # of one at 09:52 on 2026-09-24. Busy, not big.
            print(f"  {endpoint.split('/')[2]}: {err!r}", flush=True)
            turn += 1
            time.sleep(BUSY_PAUSE_S)
            continue
        except urllib.error.URLError as err:
            if isinstance(err.reason, TimeoutError):
                print(f"  {endpoint.split('/')[2]}: {err}", flush=True)
                if n - s > TIMEOUT_MEANS_BIG_DEG:
                    return TOO_BIG
                turn += 1
                time.sleep(BUSY_PAUSE_S)
                continue
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
        lines = text.splitlines()
        last = lines[-1].split("\t") if len(lines) > 1 else []
        if not last or last[0] != "0" or last[-1] != str(len(lines) - 2):
            # The header and no count: the query did not finish. Too big,
            # not busy — split it.
            print(f"  {endpoint.split('/')[2]}: no count at the end ({len(lines) - 1} rows)", flush=True)
            return TOO_BIG
        # Header and count off, and the count column off every row.
        return [lines[0]] + ["\t".join(row.split("\t")[:9]) for row in lines[1:-1]]
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


def stored_boxes(work):
    """The boxes already fetched, read back from their file names."""
    out = []
    for f in os.listdir(work):
        if f.endswith(".tsv") and f.count("_") == 3:
            try:
                out.append(tuple(float(x) for x in f[:-4].split("_")))
            except ValueError:
                pass
    return out


def inside(small, big):
    return (small != big and small[0] >= big[0] and small[1] >= big[1]
            and small[2] <= big[2] and small[3] <= big[3])


def run(work):
    os.makedirs(work, exist_ok=True)
    pending = list(boxes(START_DEG))
    while pending:
        s, w, n, e = pending.pop(0)
        path = os.path.join(work, name(s, w, n, e))
        if os.path.exists(path):
            continue
        # Split before, on an earlier run: go straight to its pieces rather
        # than asking the whole of it again, which is what it could not answer.
        if any(inside(b, (s, w, n, e)) for b in stored_boxes(work)):
            mid_lat, mid_lon = (s + n) / 2, (w + e) / 2
            pending[:0] = [(s, w, mid_lat, mid_lon), (s, mid_lon, mid_lat, e),
                           (mid_lat, w, n, mid_lon), (mid_lat, mid_lon, n, e)]
            continue
        print(f"{time.strftime('%H:%M:%S')} {s},{w},{n},{e} ({len(pending)} left)", flush=True)
        lines = fetch(s, w, n, e)
        if lines is None:
            print(f"  every server busy, waiting {LONG_WAIT_S} s", flush=True)
            time.sleep(LONG_WAIT_S)
            pending.insert(0, (s, w, n, e))
            continue
        if lines == TOO_BIG:
            if n - s <= MIN_DEG:
                # Never the end of the build: to the back of the queue, and
                # asked again when everything else is done.
                print(f"  will not answer even at {MIN_DEG} degrees; later", flush=True)
                pending.append((s, w, n, e))
                time.sleep(LONG_WAIT_S)
                continue
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
