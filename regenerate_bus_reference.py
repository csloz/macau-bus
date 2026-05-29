#!/usr/bin/env python3
"""
Regenerate bus reference data files in ~/macau-bus/data/.

Sources:
  DSAT (bis.dsat.gov.mo)     -> route stop sequences, live route list
  motransportinfo.com         -> stop names, coordinates, service hours (JS-rendered, needs Playwright)
  OpenStreetMap/Overpass      -> bridge geometry (rarely changes)
  hand-maintained             -> bridge_routes.json (which routes use which bridge)

Data directory: ~/macau-bus/data/

Step 1: DSAT stop sequences — always works via plain HTTP
Step 2: motransportinfo data — try Playwright first, fall back to keeping existing files
Step 3: Bridge geometry — skip unless explicitly requested (changes very rarely)

USAGE:
  # Quick update: DSAT stop sequences only (safe, no dependencies beyond requests)
  python3 ~/.hermes/regenerate_bus_reference.py --dsat-only

  # Full update: DSAT + motransportinfo (requires playwright installed)
  python3 ~/.hermes/regenerate_bus_reference.py

  # Full update with bridge geometry re-fetch
  python3 ~/.hermes/regenerate_bus_reference.py --bridges

OPTIONS:
  --dsat-only         Only re-fetch DSAT stop sequences (fast, no extra deps)
  --bridges           Also re-fetch Macau-Taipa Bridge geometry from Overpass
  --force-re-scape    Force re-scrape motransportinfo even if existing data is fresh
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Configuration ──────────────────────────────────────────────────────────

REFERENCE_DIR = Path(__file__).resolve().parent / "data"

# DSAT API Endpoints
# 1. SuperMap station endpoint — returns stationName in requested language with coordinates
#    https://bis.dsat.gov.mo/ddbus/common/supermap/point/station?device=web&HUID={route}&keywords=&lang={lang}
#    Returns: data = [{stationCode, stationName, latitude, longitude}, ...]
#    lang=en → English (Portuguese-style names), lang=zh-tw → Chinese
# 2. Routestation bus endpoint — returns stop sequences with live bus info
#    https://bis.dsat.gov.mo/macauweb/routestation/bus?routeName={route}&dir={0|1}
#    Returns: data.routeInfo = [{staCode, busInfo, busColor, ...}, ...]
#    NOTE: This endpoint does NOT return stop names — only codes and live telemetry
# 3. Passenger route endpoint (API discovered in JS, not fully documented)
#    https://bis.dsat.gov.mo/ddbus/app/passenger/route?routeName={route}&lang={lang}
# 4. Passenger station endpoint (API discovered in JS, not fully documented)
#    https://bis.dsat.gov.mo/ddbus/app/passenger/station?stopCode={code}&lang={lang}
#    NOTE: These return empty data with status 1000 when queried directly
# 5. GetRouteAndCompanyList.html (JS-tracked endpoint, returns 403 forbidden to requests)
#    https://bis.dsat.gov.mo/getRouteAndCompanyList.html?lang={lang}
#    NOTE: Requires specific headers/token from DSAT frontend JS flow
DSAT_STATION_ENDPOINT = "https://bis.dsat.gov.mo/ddbus/common/supermap/point/station"
DSAT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://bis.dsat.gov.mo/macauweb/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en",
}
DSAT_TIMEOUT = 15
DSAT_DELAY = 0.2  # seconds between requests
DSAT_RETRIES = 2

# motransportinfo.com
MT_BASE = "https://motransportinfo.com/zh"
MT_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MT_TIMEOUT = 20
MT_DELAY = 1.0  # polite delay between page fetches

# Bridge geometry
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
MACAU_APPROACH = [113.545, 22.1888]
TAIPA_APPROACH = [113.5497, 22.1638]

# Bridge route IDs (hand-maintained — rarely changes)
BRIDGE_ROUTE_IDS = [
    "11", "21A", "22", "25", "25AX", "25B", "28A", "33", "39",
    "50", "50B", "52", "71", "73", "102", "H3", "MT1", "MT2",
    "MT5", "N5",
]

EXISTING_FILES = ["route_list.json", "routes.json", "stops.json"]


# ── DSAT SuperMap Bilingual Stops Fetcher ──────────────────────────────────

def fetch_bilingual_stops_from_dsat() -> tuple[dict, dict, dict]:
    """Fetch all stop names in both languages from the SuperMap endpoint.

    Uses the DSAT SuperMap station endpoint which returns stationName in the
    requested language:
      - lang=en → English (Portuguese-style) names like "AL. DA HARMONIA / EDF. LOK KUAN"
      - lang=zh-tw → Chinese names like "和諧廣場/樂群樓"

    Returns:
        (bilingual_stops, lat_lng_map, en_stops_map) where:
        - bilingual_stops: {stop_code: {id, nameCn, nameEn, lat, lng, route_ids}}
        - lat_lng_map: {stop_code: (lat, lng)} for all stops seen
        - en_stops_map: {stop_code: nameEn} for quick lookup
    """
    print("\n" + "=" * 60)
    print("STEP 1.5: Fetching bilingual stop names from DSAT SuperMap")
    print("=" * 60)

    # Need route_list.json to know which routes to fetch
    route_list_path = REFERENCE_DIR / "route_list.json"
    if not route_list_path.exists():
        print(f"WARNING: {route_list_path} missing. Skipping bilingual names.", file=sys.stderr)
        return {}, {}, {}

    route_list = json.loads(route_list_path.read_text(encoding="utf-8"))
    route_ids = [r["id"] for r in route_list]
    print(f"Found {len(route_ids)} routes in route_list.json")

    all_stops: dict[str, dict] = {}
    all_route_codes: set[str] = set()

    # Fetch English names first
    print("Fetching English names...")
    en_stops = fetch_dsat_stops_bilingual(route_ids, "en")
    # Fetch Chinese names
    print("Fetching Chinese names...")
    zh_stops = fetch_dsat_stops_bilingual(route_ids, "zh-tw")

    # Merge: Chinese names have priority as primary, English as secondary
    for code, info in zh_stops.items():
        all_stops[code] = {
            "id": code,
            "nameCn": info.get("stationName", ""),
            "nameEn": "",  # Will be filled from en_stops
            "lat": info.get("latitude", 0),
            "lng": info.get("longitude", 0),
            "route_ids": [],
        }

    for code, info in en_stops.items():
        if code in all_stops:
            all_stops[code]["nameEn"] = info.get("stationName", "")
            if all_stops[code]["lat"] == 0 and info.get("latitude"):
                all_stops[code]["lat"] = info["latitude"]
            if all_stops[code]["lng"] == 0 and info.get("longitude"):
                all_stops[code]["lng"] = info["longitude"]
        else:
            all_stops[code] = {
                "id": code,
                "nameCn": "",
                "nameEn": info.get("stationName", ""),
                "lat": info.get("latitude", 0),
                "lng": info.get("longitude", 0),
                "route_ids": [],
            }

    # Collect unique route codes for route_ids association
    for rid in route_ids:
        # Parse route code from HUID (could be "33", "51A", "N5", etc.)
        all_route_codes.add(rid)

    # Save bilingual stops data
    stops_path = REFERENCE_DIR / "stops_bilingual.json"
    stops_path.write_text(
        json.dumps(list(all_stops.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Count how many have each language
    cn_count = sum(1 for s in all_stops.values() if s["nameCn"])
    en_count = sum(1 for s in all_stops.values() if s["nameEn"])
    both_count = sum(1 for s in all_stops.values() if s["nameCn"] and s["nameEn"])
    print(f"\nSaved {stops_path}")
    print(f"  {len(all_stops)} unique stops total")
    print(f"  Chinese names: {cn_count}, English names: {en_count}, Both: {both_count}")

    return all_stops, {k: (v["lat"], v["lng"]) for k, v in all_stops.items()}, {k: v["nameEn"] for k, v in all_stops.items()}


def fetch_dsat_stops_bilingual(route_ids: list[str], lang: str) -> dict[str, dict]:
    """Fetch stop names from DSAT SuperMap endpoint for a single language.

    Returns: {stationCode: {stationName, latitude, longitude}}
    """
    result: dict[str, dict] = {}
    seen_codes: set[str] = set()

    for i, rid in enumerate(route_ids):
        url = f"{DSAT_STATION_ENDPOINT}?device=web&HUID={rid}&keywords=&lang={lang}"
        last_err = None
        for attempt in range(DSAT_RETRIES + 1):
            try:
                r = requests.get(url, headers=DSAT_HEADERS, timeout=DSAT_TIMEOUT)
                r.raise_for_status()
                payload = r.json()
                if payload.get("header") != "000":
                    break
                stops = payload.get("data", []) or []
                for s in stops:
                    code = s.get("stationCode", "")
                    if code and code not in seen_codes:
                        seen_codes.add(code)
                        result[code] = {
                            "stationName": s.get("stationName", ""),
                            "latitude": s.get("latitude", 0),
                            "longitude": s.get("longitude", 0),
                        }
                break
            except Exception as e:
                last_err = e
                if attempt < DSAT_RETRIES:
                    time.sleep(0.5 * (attempt + 1))

        if i % 10 == 0:
            print(f"  [{i+1:3d}/{len(route_ids)}] {rid:>6} ({lang}) → {len(seen_codes)} stops so far")

        time.sleep(DSAT_DELAY)

    return result


# ── DSAT Fetchers ──────────────────────────────────────────────────────────

def fetch_dsat_direction(route_id: str, direction: int) -> tuple[list[str], bool]:
    """Return (stop_codes, ok) from DSAT for one direction of one route."""
    url = f"{DSAT_BASE}?routeName={route_id}&dir={direction}"
    last_err = None
    for attempt in range(DSAT_RETRIES + 1):
        try:
            r = requests.get(url, headers=DSAT_HEADERS, timeout=DSAT_TIMEOUT)
            r.raise_for_status()
            payload = r.json()
            if payload.get("header") != "000":
                return [], False
            route_info = payload.get("data", {}).get("routeInfo", []) or []
            stops = [s.get("staCode", "") for s in route_info if s.get("staCode")]
            return stops, True
        except Exception as e:
            last_err = e
            if attempt < DSAT_RETRIES:
                time.sleep(0.5 * (attempt + 1))
    print(f"  !! {route_id} dir={direction} error: {last_err}", file=sys.stderr)
    return [], False


def fetch_dsat_stops() -> int:
    """Re-fetch dsat_stops.json from DSAT.

    This contains per-route forward/backward stop sequences with platform suffixes.
    Fast (~5 minutes for all routes), no extra dependencies needed.
    """
    print("\n" + "=" * 60)
    print("STEP 1: Fetching DSAT stop sequences")
    print("=" * 60)

    # Need route_list.json to know which routes to fetch
    route_list_path = REFERENCE_DIR / "route_list.json"
    if not route_list_path.exists():
        print(f"ERROR: {route_list_path} missing. Cannot fetch DSAT stops.", file=sys.stderr)
        return 1

    route_list = json.loads(route_list_path.read_text(encoding="utf-8"))
    print(f"Found {len(route_list)} routes in route_list.json")

    routes_out: dict[str, dict] = {}
    empty_routes: list[str] = []

    for i, r in enumerate(route_list):
        rid = r["id"]
        time.sleep(DSAT_DELAY)

        fwd, fwd_ok = fetch_dsat_direction(rid, 0)
        time.sleep(DSAT_DELAY)
        bwd, bwd_ok = fetch_dsat_direction(rid, 1)

        tag = "circular" if fwd_ok and bwd_ok and bwd == [] and fwd else \
              "empty" if fwd == [] and bwd == [] else \
              "bidir"
        status = f"fwd={len(fwd):>3}  bwd={len(bwd):>3}  [{tag}]"

        # Only print progress periodically or when notable
        if i % 10 == 0 or tag in ("empty",):
            print(f"  [{i+1:3d}/{len(route_list)}] {rid:>6}  {status}")

        if tag == "empty":
            empty_routes.append(rid)

        routes_out[rid] = {
            "forward": fwd,
            "backward": bwd,
            "forwardOk": fwd_ok,
            "backwardOk": bwd_ok,
        }

    output = {
        "fetchedAtUtc": datetime.now(tz=timezone.utc).isoformat(),
        "totalRoutes": len(route_list),
        "emptyRoutes": empty_routes,
        "routes": routes_out,
    }

    output_path = REFERENCE_DIR / "dsat_stops.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nWrote {output_path}")
    print(f"Empty routes (no service today / outside hours): {len(empty_routes)}")
    if empty_routes:
        print(f"  {', '.join(empty_routes)}")
    return 0


def fetch_route_list_from_dsat() -> list[dict] | None:
    """Try to extract a route list from the DSAT all-positions endpoint.

    This returns ALL 92 routes in one call with zero positions (header only).
    We use it as a fallback if route_list.json is missing or stale.
    """
    url = DSAT_BASE  # no routeName param — returns empty but lists all routes
    try:
        r = requests.get(url, headers=DSAT_HEADERS, timeout=DSAT_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
        if payload.get("header") == "000":
            data = payload.get("data", {})
            route_info = data.get("routeInfo", []) or []
            # This returns stop-level data, not route-level summary
            # We can't get a clean route list from here without querying each route
            return None
    except Exception:
        pass
    return None


# ── motransportinfo Fetchers (Playwright-based) ────────────────────────────

def can_use_playwright() -> tuple[bool, str]:
    """Check if Playwright Python package is available."""
    try:
        from playwright.sync_api import sync_playwright
        return True, "playwright"
    except ImportError:
        pass
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", "from playwright.sync_api import sync_playwright"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True, "playwright (after install)"
    except Exception:
        pass
    return False, "not installed"


def fetch_motransportinfo_with_playwright() -> int:
    """Scrape motransportinfo.com using Playwright for JS-rendered pages.

    Fetches:
      - route_list.json (route IDs + descriptions)
      - routes.json (service hours, frequency, stop sequences with coords)
      - stops.json (stop IDs, Chinese names, coordinates, route associations)

    This replaces the old BeautifulSoup scraper which broke when motransportinfo
    switched to a JS-rendered frontend.
    """
    from playwright.sync_api import sync_playwright

    print("\n" + "=" * 60)
    print("STEP 2: Scraping motransportinfo.com (Playwright)")
    print("=" * 60)

    all_routes = []
    all_stops: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        page = context.new_page()

        # Navigate to search page
        print("Loading search page...")
        page.goto(MT_BASE + "/search", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)  # extra time for data loading

        # Extract route list from page
        route_links = page.query_selector_all('a[href*="/route/"]')
        route_list = []
        seen_ids = set()

        for link in route_links:
            href = link.get_attribute("href") or ""
            m = re.match(r"route/([^/]+)/0/?$", href)
            if m:
                rid = m.group(1)
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    text = link.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    desc = lines[1] if len(lines) >= 2 else ""
                    route_list.append({"id": rid, "description": desc})

        print(f"Found {len(route_list)} routes on search page")
        if not route_list:
            print("No routes found. motransportinfo may have changed their layout.")
            print("Check: /tmp/mini-macau/playwright_screenshot.png for debug.")
            page.screenshot(path="/tmp/mini-macau/playwright_screenshot.png")
            browser.close()
            return 1

        # Save route list
        route_list_path = REFERENCE_DIR / "route_list.json"
        route_list_path.write_text(
            json.dumps(route_list, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Fetch each route page
        for i, r in enumerate(route_list):
            rid = r["id"]
            print(f"  [{i+1}/{len(route_list)}] Route {rid}: {r['description']}", end="", flush=True)

            # Fetch direction 0
            try:
                page.goto(f"{MT_BASE}/route/{rid}/0", wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)
                page0_content = page.content()
                d0 = parse_route_page_js(page0_content, rid, 0)
            except Exception as e:
                print(f" ERROR: {e}")
                all_routes.append({"id": rid, "error": str(e)})
                continue

            if not d0:
                print(" (parse failed)")
                all_routes.append({"id": rid, "error": "parse failed"})
                continue

            # Fetch direction 1 for bilateral routes
            route_type = d0.get("route_type", "")
            d1 = None
            if route_type == "bilateral":
                try:
                    page.goto(f"{MT_BASE}/route/{rid}/1", wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(2000)
                    page1_content = page.content()
                    d1 = parse_route_page_js(page1_content, rid, 1)
                except Exception as e:
                    print(f" (dir1 error: {e})")

            # Compute service summary from schedule
            sched_summary = {}
            for d in [d0, d1]:
                if d and d.get("schedule") and not sched_summary:
                    sched_summary = compute_service_summary(d["schedule"])

            # Build route entry
            route_entry = {
                "id": rid,
                "description": r["description"],
                "route_type": route_type,
                "service_start": sched_summary.get("start_hour", 6),
                "service_end": sched_summary.get("end_hour", 23),
                "avg_freq": sched_summary.get("avg_freq", 12),
                "schedule": d0.get("schedule", []) if d0 else [],
                "directions": [],
            }
            for d in [d0, d1]:
                if d:
                    route_entry["directions"].append({
                        "direction": d["direction"],
                        "direction_name": d.get("direction_name", ""),
                        "stops": d["stops"],
                        "stations": d["stations"],
                        "lats": d["lats"],
                        "lngs": d["lngs"],
                    })
                    # Collect stops
                    for j, stop_id in enumerate(d["stops"]):
                        if stop_id not in all_stops:
                            station_name = d["stations"][j] if j < len(d["stations"]) else ""
                            try:
                                lat = float(d["lats"][j]) if j < len(d["lats"]) else 0
                            except (ValueError, TypeError):
                                lat = 0
                            try:
                                lng = float(d["lngs"][j]) if j < len(d["lngs"]) else 0
                            except (ValueError, TypeError):
                                lng = 0
                            all_stops[stop_id] = {
                                "id": stop_id,
                                "nameCn": station_name,
                                "lat": lat,
                                "lng": lng,
                                "route_ids": [],
                            }
                        if rid not in all_stops[stop_id]["route_ids"]:
                            all_stops[stop_id]["route_ids"].append(rid)

            all_routes.append(route_entry)
            print(f" OK")
            time.sleep(MT_DELAY)

        browser.close()

    # Save outputs
    routes_path = REFERENCE_DIR / "routes.json"
    routes_path.write_text(
        json.dumps(all_routes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stops_path = REFERENCE_DIR / "stops.json"
    stops_path.write_text(
        json.dumps(list(all_stops.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok_count = sum(1 for r in all_routes if "error" not in r)
    print(f"\nDone: {ok_count}/{len(route_list)} routes, {len(all_stops)} unique stops")
    print(f"Saved routes.json: {routes_path}")
    print(f"Saved stops.json: {stops_path}")
    return 0


def parse_route_page_js(html: str, route_no: str, direction: int) -> dict | None:
    """Parse a motransportinfo route page (JS-rendered HTML) for stop/geo/schedule data."""
    # Extract JavaScript variables
    stop_m = re.search(r'var\s+stop\s*=\s*\[(.*?)\];', html, re.DOTALL)
    station_m = re.search(r'var\s+station\s*=\s*\[(.*?)\];', html, re.DOTALL)
    lat_m = re.search(r'var\s+lat\s*=\s*\[(.*?)\];', html, re.DOTALL)
    lng_m = re.search(r'var\s+lng\s*=\s*\[(.*?)\];', html, re.DOTALL)
    dir_m = re.search(r"var\s+direction\s*=\s*['\"](\w+)['\"];", html)
    textnum_m = re.search(r"var\s+textnum\s*=\s*['\"](\d+)['\"];", html)

    if not all([stop_m, lat_m, lng_m]):
        return None

    def parse_js_array(s: str) -> list[str]:
        return [x.strip().strip('"').strip("'") for x in s.split(",") if x.strip()]

    stops = parse_js_array(stop_m.group(1))
    lats = parse_js_array(lat_m.group(1))
    lngs = parse_js_array(lng_m.group(1))

    stations = []
    if station_m:
        stations = parse_js_array(station_m.group(1))

    # Parse schedule from HTML tables
    schedule = parse_schedule(html)

    # Route type from page text
    route_type = ""
    if "雙向" in html or "双向" in html:
        route_type = "bilateral"
    elif "循環" in html or "循环" in html:
        route_type = "circular"

    return {
        "route_no": route_no,
        "direction": direction,
        "direction_name": dir_m.group(1) if dir_m else "",
        "route_type": route_type,
        "stop_count": int(textnum_m.group(1)) if textnum_m else len(stops),
        "stops": stops,
        "stations": stations,
        "lats": lats,
        "lngs": lngs,
        "schedule": schedule,
    }


def parse_schedule(html: str) -> list[dict]:
    """Parse service hours table from HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    schedule = []
    table = None
    for t in soup.find_all("table"):
        if any("服務時間" in (th.get_text() or "") for th in t.find_all("th")):
            table = t
            break
    if not table:
        return schedule

    current_period = ""
    for tr in table.find_all("tr"):
        th = tr.find("th")
        if th:
            period_text = th.get_text(strip=True)
            if period_text and "服務" not in period_text and "班次" not in period_text:
                current_period = period_text
            continue

        tds = tr.find_all("td")
        if len(tds) >= 2:
            time_range = tds[0].get_text(strip=True)
            freq_text = tds[1].get_text(strip=True)
            time_m = re.match(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", time_range)
            freq_m = re.match(r"(\d+)\s*-\s*(\d+)", freq_text)
            if time_m and freq_m:
                schedule.append({
                    "period": current_period,
                    "start": time_m.group(1),
                    "end": time_m.group(2),
                    "freq_min": int(freq_m.group(1)),
                    "freq_max": int(freq_m.group(2)),
                })
    return schedule


def compute_service_summary(schedule: list[dict]) -> dict:
    """Compute representative start hour, end hour, and avg frequency from schedule entries."""
    if not schedule:
        return {"start_hour": 6, "end_hour": 23, "avg_freq": 12}

    all_starts = []
    all_ends = []
    total_freq = 0
    count = 0

    for entry in schedule:
        sh, sm = map(int, entry["start"].split(":"))
        eh, em = map(int, entry["end"].split(":"))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if end_min <= start_min:
            end_min += 1440
        all_starts.append(start_min)
        all_ends.append(end_min)
        avg = (entry["freq_min"] + entry["freq_max"]) / 2
        total_freq += avg
        count += 1

    earliest_start = min(all_starts)
    latest_end = max(all_ends)
    start_hour = earliest_start // 60
    end_hour = latest_end // 60
    if latest_end % 60 > 0:
        end_hour += 1
    if end_hour > 28:
        end_hour = 28

    avg_freq = round(total_freq / count) if count else 12
    return {"start_hour": start_hour, "end_hour": end_hour, "avg_freq": avg_freq}


# ── Bridge Geometry ────────────────────────────────────────────────────────

BRIDGE_QUERY = """
[out:json][timeout:60];
(
  way(22.14,113.53,22.21,113.57)["bridge"="yes"]["name"~"Carvalho"];
  way(22.14,113.53,22.21,113.57)["bridge"="yes"]["name:zh"~"嘉樂庇"];
  way(22.14,113.53,22.21,113.57)["bridge"="yes"]["name"~"嘉樂庇"];
  way(22.186,113.541,22.194,113.549)["bridge"="yes"];
  way(22.159,113.544,22.167,113.555)["bridge"="yes"];
);
(._;>;);
out body;
"""


def fetch_bridge_geometry() -> int:
    """Re-fetch Macau-Taipa Bridge geometry from Overpass API."""
    print("\n" + "=" * 60)
    print("STEP 3: Fetching Macau-Taipa Bridge geometry from Overpass")
    print("=" * 60)

    import math

    last_err = None
    bridge_coords = []
    for url in OVERPASS_MIRRORS:
        try:
            print(f"  Trying {url}...")
            resp = requests.post(url, data={"data": BRIDGE_QUERY}, timeout=90)
            resp.raise_for_status()
            data = resp.json()

            elements = data.get("elements", [])
            print(f"  Got {len(elements)} elements")

            # Stitch bridge geometry
            nodes = {}
            ways = []
            for el in elements:
                if el.get("type") == "node":
                    nodes[el["id"]] = (el["lon"], el["lat"])
                elif el.get("type") == "way":
                    ways.append(el)

            # Find seed ways (the actual bridge)
            def is_seed(w):
                tags = w.get("tags", {})
                name = tags.get("name", "") + " " + tags.get("name:zh", "")
                return "Carvalho" in name or "嘉樂庇" in name

            kept_ids = {w["id"] for w in ways if is_seed(w)}
            if not kept_ids:
                # Try connected component from any bridge way
                kept_ids = {w["id"] for w in ways if w.get("tags", {}).get("bridge") == "yes"}

            # Connected component
            kept_nodes = set()
            for w in ways:
                if w["id"] in kept_ids:
                    kept_nodes.update(w["nodes"])
            changed = True
            while changed:
                changed = False
                for w in ways:
                    if w["id"] in kept_ids:
                        continue
                    if set(w["nodes"]) & kept_nodes:
                        kept_ids.add(w["id"])
                        kept_nodes.update(w["nodes"])
                        changed = True

            pts = [nodes[nid] for nid in kept_nodes if nid in nodes]
            if not pts:
                print("  No bridge geometry extracted from this mirror")
                last_err = "no geometry"
                continue

            # Sort by latitude (north to south = Macau to Taipa)
            pts.sort(key=lambda p: -p[1])

            # Deduplicate near-coincident points
            METERS_PER_DEG_LAT = 111320.0
            deduped = []
            for p in pts:
                if not deduped:
                    deduped.append(p)
                    continue
                last = deduped[-1]
                d_lat_m = (p[1] - last[1]) * METERS_PER_DEG_LAT
                cos_lat = max(0.1, abs(math.cos(math.radians(p[1]))))
                d_lng_m = (p[0] - last[0]) * METERS_PER_DEG_LAT * cos_lat
                if (d_lat_m * d_lat_m + d_lng_m * d_lng_m) ** 0.5 >= 1.5:
                    deduped.append(p)

            bridge_coords = [[lon, lat] for lon, lat in deduped]

            # Ensure Macau-side first (north)
            if bridge_coords and bridge_coords[0][1] < bridge_coords[-1][1]:
                bridge_coords = list(reversed(bridge_coords))

            break  # success

        except Exception as e:
            print(f"    failed: {e}")
            last_err = e

    if not bridge_coords:
        print(f"\nERROR: All Overpass mirrors failed. Last error: {last_err}")
        print("Keeping existing bridges.json.")
        return 1

    output = {
        "macau_taipa_bridge": {
            "name_zh": "嘉樂庇總督大橋",
            "name_pt": "Ponte Governador Nobre de Carvalho",
            "name_en": "Macau-Taipa Bridge",
            "coordinates": bridge_coords,
            "macau_end": bridge_coords[0],
            "taipa_end": bridge_coords[-1],
            "macau_approach": MACAU_APPROACH,
            "taipa_approach": TAIPA_APPROACH,
        }
    }

    output_path = REFERENCE_DIR / "bridges.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nSaved {len(bridge_coords)} points -> {output_path}")
    print(f"  Macau end: {bridge_coords[0]}")
    print(f"  Taipa end: {bridge_coords[-1]}")
    return 0


# ── Bridge Routes (hand-maintained) ────────────────────────────────────────

def ensure_bridge_routes() -> int:
    """Ensure bridge_routes.json exists with known route IDs."""
    output_path = REFERENCE_DIR / "bridge_routes.json"
    if output_path.exists():
        existing = json.loads(output_path.read_text())
        existing_ids = set(existing.get("macau_taipa_bridge", []))
        current_ids = set(BRIDGE_ROUTE_IDS)
        if existing_ids == current_ids:
            print(f"bridge_routes.json already up to date ({len(current_ids)} routes)")
            return 0

    output = {
        "_comment": "Bus route IDs that travel via 嘉樂庇總督大橋 (Macau-Taipa Bridge). "
                     "Sourced from user knowledge of actual Macau bus operations.",
        "macau_taipa_bridge": sorted(BRIDGE_ROUTE_IDS),
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote bridge_routes.json ({len(BRIDGE_ROUTE_IDS)} routes)")
    return 0


# ── Data Freshness Check ───────────────────────────────────────────────────

def check_freshness() -> dict:
    """Check if existing data files are less than 30 days old."""
    results = {}
    for fname in EXISTING_FILES:
        path = REFERENCE_DIR / fname
        if path.exists():
            mtime = path.stat().st_mtime
            age_days = (time.time() - mtime) / 86400
            results[fname] = {
                "exists": True,
                "age_days": round(age_days, 1),
                "stale": age_days > 30,
                "path": str(path),
            }
        else:
            results[fname] = {"exists": False}

    # dsat_stops.json
    dsat_path = REFERENCE_DIR / "dsat_stops.json"
    if dsat_path.exists():
        data = json.loads(dsat_path.read_text())
        fetched = data.get("fetchedAtUtc", "")
        results["dsat_stops.json"] = {
            "exists": True,
            "fetchedAtUtc": fetched,
            "stale": "T" in fetched and datetime.fromisoformat(fetched).replace(tzinfo=timezone.utc)
                     < datetime.now(tz=timezone.utc) - __import__("datetime").timedelta(days=30),
        }

    return results


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Regenerate bus reference data")
    parser.add_argument("--dsat-only", action="store_true",
                        help="Only re-fetch DSAT stop sequences")
    parser.add_argument("--bridges", action="store_true",
                        help="Also re-fetch bridge geometry from Overpass")
    parser.add_argument("--force", action="store_true",
                        help="Force re-scan motransportinfo")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show data status without making changes")
    args = parser.parse_args()

    # Show freshness
    print("=" * 60)
    print("Bus Reference Data — Current Status")
    print("=" * 60)
    status = check_freshness()
    for fname, info in status.items():
        if info.get("exists"):
            stale_marker = " ⚠ STALE" if info.get("stale") else ""
            if fname == "dsat_stops.json":
                print(f"  {fname}: fetched {info.get('fetchedAtUtc', '?')}{stale_marker}")
            else:
                print(f"  {fname}: {info['age_days']} days old{stale_marker}")
        else:
            print(f"  {fname}: MISSING")

    print()

    if args.dry_run:
        print("Dry run — no changes made.")
        return 0

    if args.dsat_only:
        return fetch_dsat_stops()

    # Full update
    results = {}

    # Step 1: DSAT (always do this)
    results["dsat"] = fetch_dsat_stops()

    # Step 1.5: Bilingual stop names from DSAT SuperMap
    results["bilingual_names"] = 0
    bilingual_stops, lat_lng_map, en_stops_map = fetch_bilingual_stops_from_dsat()

    # Step 2: motransportinfo (JS-rendered)
    can_pw, pw_note = can_use_playwright()
    if can_pw or args.force:
        if not can_pw:
            print("\nWARNING: Playwright not installed. motransportinfo is JS-rendered.")
            print("Options:")
            print("  1. Install playwright in macau-bus venv: cd ~/macau-bus && pip install playwright")
            print("  2. Accept existing motransportinfo data (may be stale)")
            print("  3. Continue without it (dsat_stops.json only updated)")
            if not args.force:
                print("\nKeeping existing motransportinfo files (routes.json, stops.json, route_list.json).")
                return results.get("dsat", 0)

        results["motransportinfo"] = fetch_motransportinfo_with_playwright()

        # If we got motransportinfo data, enrich stops.json with bilingual names
        # For stops that have coords from motransportinfo but no English name, use DSAT
        if bilingual_stops:
            enrich_stops_with_bilingual(bilingual_stops)
    else:
        print("\nPlaywright available: yes (scripts can use it)")
        print("Keeping existing motransportinfo files.")

        # Even without motransportinfo, enrich existing stops.json with DSAT bilingual data
        if bilingual_stops:
            enrich_stops_with_bilingual(bilingual_stops)

    # Step 3: Bridge routes file (hand-maintained)
    results["bridge_routes"] = ensure_bridge_routes()

    # Step 4: Bridge geometry (rarely changes)
    if args.bridges:
        results["bridges"] = fetch_bridge_geometry()
    else:
        bridge_path = REFERENCE_DIR / "bridges.json"
        if bridge_path.exists():
            age = (time.time() - bridge_path.stat().st_mtime) / 86400
            print(f"\nbridges.json: {age:.0f} days old (skip re-fetch). Use --bridges to force.")
        results["bridges"] = 0

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for step, code in results.items():
        status_str = "OK" if code == 0 else "FAILED"
        print(f"  {step}: {status_str}")

    return max(results.values(), default=0)


if __name__ == "__main__":
    sys.exit(main())
