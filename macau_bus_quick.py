#!/usr/bin/env python3
"""
Macau Bus Quick — Ultra-simple output for casual queries.

When user asks "when's the next bus?" or "where are my buses?"
Output: clean, minimal text for summarizing in plain language.

Usage:
  python macau_bus_quick.py --stop T394
  python macau_bus_quick.py --stop T394 -r 51A
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://bis.dsat.gov.mo/macauweb/routestation/bus"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://bis.dsat.gov.mo/macauweb/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}
TIMEOUT = 15
DATA_DIR = Path(__file__).resolve().parent / "data"


def load_stops():
    path = DATA_DIR / "stops.json"
    return json.loads(path.read_text()) if path.exists() else []


def find_stop(stop_id, stops_data):
    for s in stops_data:
        if s.get("id") == stop_id:
            return s
    return None


def fetch_route(route_id, direction=0):
    """Fetch live data for a route. Returns list of station dicts."""
    url = f"{BASE_URL}?routeName={route_id}&dir={direction}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        payload = r.json()
        if payload.get("header") != "000":
            return None
        return payload.get("data", {}).get("routeInfo", [])
    except Exception:
        return None


def get_stop_index_in_route(route_id, stop_id, live_data):
    """Get the stop's index in the route's stop sequence."""
    if not live_data:
        return None
    codes = [s["staCode"].split("/")[0] for s in live_data]
    if stop_id in codes:
        return codes.index(stop_id)
    return None


def get_arrivals(route_id, stop_id):
    """Get closest bus info for this route at this stop.
    
    Uses position-based calculation: bus is at a station in routeInfo,
    distance = stop_index - bus_station_index.
    """
    best_stops_away = None
    total = 0

    for direction in [0, 1]:
        live_data = fetch_route(route_id, direction)
        if not live_data:
            continue

        stop_idx = get_stop_index_in_route(route_id, stop_id, live_data)
        if stop_idx is None:
            continue

        # Build all station codes for this direction
        all_codes = [s["staCode"].split("/")[0] for s in live_data]

        for station in live_data:
            sta_code = station["staCode"].split("/")[0]
            if sta_code not in all_codes:
                continue

            sta_idx = all_codes.index(sta_code)

            # Calculate stops away based on position
            if direction == 0:
                # Forward: bus station must be before or at stop
                if sta_idx > stop_idx:
                    continue
                away = stop_idx - sta_idx
            else:
                # Backward: bus station must be after or at stop
                if sta_idx < stop_idx:
                    continue
                away = sta_idx - stop_idx

            buses = station.get("busInfo", [])
            if not buses:
                continue

            total += len(buses)

            if away < 0:
                continue

            if best_stops_away is None or away < best_stops_away:
                best_stops_away = away

    if best_stops_away is None:
        return None, 0

    return best_stops_away, total


def main():
    parser = argparse.ArgumentParser(description="Macau Bus Quick — minimal output")
    parser.add_argument("--stop", required=True, help="Stop ID (e.g. T394)")
    parser.add_argument("-r", "--route", help="Filter to specific route")
    args = parser.parse_args()

    stops_data = load_stops()
    stop = find_stop(args.stop, stops_data)

    if not stop:
        print(f"Stop {args.stop} not found")
        sys.exit(1)

    cn = stop.get("nameCn", args.stop)
    pt = stop.get("namePt", "")
    route_ids = stop.get("route_ids", [])

    if args.route:
        route_ids = [r for r in route_ids if r == args.route]

    arrivals = {}
    for route_id in sorted(route_ids):
        closest, total = get_arrivals(route_id, args.stop)
        if closest is not None:
            arrivals[route_id] = {"stops": closest, "total": total}

    now = datetime.now().strftime("%H:%M")
    print(cn)
    if pt:
        print(pt)
    print(now)

    if not arrivals:
        print("No active buses.")
        return

    for route_id in sorted(arrivals):
        info = arrivals[route_id]
        if info["stops"] == 0:
            print(f"Route {route_id}: AT STOP")
        else:
            print(f"Route {route_id}: {info['stops']} stop{'s' if info['stops'] != 1 else ''} away")

    # Summary
    closest = min(arrivals.values(), key=lambda x: x["stops"])
    closest_route = [r for r, v in arrivals.items() if v["stops"] == closest["stops"]][0]
    print()
    print(f"Closest: Route {closest_route} at {closest['stops']} stop{'s' if closest['stops'] != 1 else ''} away.")


if __name__ == "__main__":
    main()
