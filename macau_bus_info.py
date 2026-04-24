#!/usr/bin/env python3
"""
Macau Bus Information Tool v2.0
Complete bus route & stop distance calculator for Macau

Features:
  - Route information & stop lists
  - Stop location lookup (Chinese name + coordinates)
  - English stop names from DSAT SuperMap API
  - Distance calculation between any two stops
  - Distance from stop to specific location
  - All data sourced from DSAT API (Macau Bus Authority)

Usage:
  python macau_bus_info.py --route 51A
  python macau_bus_info.py --route 51A --stop T394
  python macau_bus_info.py --route 51A --stop M93 --to-stop C690/1
"""

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://bis.dsat.gov.mo/macauweb/routestation/bus"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://bis.dsat.gov.mo/macauweb/",
    "Accept": "application/json, text/plain, */*",
}
TIMEOUT = 15

DEFAULT_DATA_DIR = Path("/tmp/mini-macau/data/bus_reference")

# English stop name cache (process-scope)
EN_NAME_CACHE = {}


def fetch_stop_name_en(stop_id: str) -> str:
    """Fetch English stop name from DSAT SuperMap API."""
    if stop_id in EN_NAME_CACHE:
        return EN_NAME_CACHE[stop_id]
    url = (
        f"https://bis.dsat.gov.mo/ddbus/common/supermap/point/station?"
        f"device=web&HUID=33&keywords={stop_id}&lang=en"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        data = r.json()
        header = data.get("header", {})
        if isinstance(header, dict):
            status = header.get("status", "")
        else:
            status = str(header)
        if status == "000":
            items = data.get("data", [])
            for item in items:
                if item.get("stationCode") == stop_id:
                    EN_NAME_CACHE[stop_id] = item.get("stationName", "")
                    return EN_NAME_CACHE[stop_id]
    except Exception:
        pass
    EN_NAME_CACHE[stop_id] = ""
    return ""


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points (Haversine formula)."""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def load_local_stops_data(data_dir: Path) -> dict:
    """Load stop coordinates from local cache."""
    stops_path = data_dir / "stops.json"
    if not stops_path.exists():
        return {}

    try:
        stops = json.loads(stops_path.read_text())
        return {
            stop["id"]: {
                "nameCn": stop.get("nameCn", ""),
                "nameEn": EN_NAME_CACHE.get(stop["id"], ""),
                "lat": stop.get("lat"),
                "lng": stop.get("lng"),
            }
            for stop in stops
            if stop.get("id") and stop.get("lat") and stop.get("lng")
        }
    except Exception:
        return {}


def load_local_dsat_data(data_dir: Path) -> dict:
    """Load DSAT stop sequences."""
    dsat_path = data_dir / "dsat_stops.json"
    if not dsat_path.exists():
        return {}

    try:
        return json.loads(dsat_path.read_text())
    except Exception:
        return {}


def calc_distance(from_stop: str, to_stop: str, stops_data: dict) -> dict:
    """Calculate distance between two stops."""
    from_data = stops_data.get(from_stop)
    to_data = stops_data.get(to_stop)

    if not from_data or not to_data:
        return {"error": "One or both stops not found"}

    if not from_data['lat'] or not from_data['lng'] or not to_data['lat'] or not to_data['lng']:
        return {"error": "Coordinates missing for one or both stops"}

    distance_km = haversine_distance_km(
        from_data['lat'], from_data['lng'],
        to_data['lat'], to_data['lng']
    )

    return {
        "from_stop": from_stop,
        "from_name": from_data['nameCn'],
        "to_stop": to_stop,
        "to_name": to_data['nameCn'],
        "distance_km": round(distance_km, 2),
        "distance_m": round(distance_km * 1000),
    }


def print_route_info(route_id: str, dsat_data: dict, stops_data: dict, args: argparse.Namespace):
    """Print route details and optional stop information."""
    routes = dsat_data.get("routes", {})
    route = routes.get(route_id)

    if not route:
        print(f"❌ Route {route_id} not found")
        print(f"   Available routes (sample): {list(routes.keys())[:10]}")
        return

    # Show route header
    print(f"\n{'▬' * 60}")
    print(f"🚌 ROUTE: {route_id}")
    print(f"{'▬' * 60}\n")

    # Direction info
    fwd = route.get("forward", [])
    bwd = route.get("backward", [])
    fwd_ok = route.get("forwardOk", True)
    bwd_ok = route.get("backwardOk", True)

    if not args.stops:
        # Summary mode
        print("Forward direction:")
        print(f"  • Stops: {len(fwd)}")
        print(f"  • Status: {'✅' if fwd_ok else '❌'} Available")
        if fwd:
            print(f"  • First: {fwd[0]}")
            print(f"  • Last: {fwd[-1]}")

        print("\nBackward direction:")
        print(f"  • Stops: {len(bwd)}")
        print(f"  • Status: {'✅' if bwd_ok else '❌'} Available")
        if bwd:
            print(f"  • First: {bwd[0]}")
            print(f"  • Last: {bwd[-1]}")
    else:
        # Collect all unique stop IDs from both directions for batch lookup
        all_codes = set()
        for s in fwd:
            all_codes.add(s.split("/")[0])
        for s in bwd:
            all_codes.add(s.split("/")[0])

        # Fetch English names (with cache)
        batch_fetch_en(all_codes)

        # Update stops_data with English names
        for code in all_codes:
            en = EN_NAME_CACHE.get(code, "")
            if en and code in stops_data:
                stops_data[code]["nameEn"] = en

        # Full stop list mode
        print("Forward direction:")
        print(f"  {'─' * 70}")
        print(f"  {'#':<4} {'Code':<7} Chinese Name             English Name                   Coordinates")
        print(f"  {'─' * 70}")
        for i, stop in enumerate(fwd, 1):
            code = stop.split("/")[0]
            info = stops_data.get(code, {})
            cname = info.get("nameCn", "???")
            ename = info.get("nameEn", "???")
            lat = info.get("lat", "?.?")
            lng = info.get("lng", "?.?")
            coord = f"{lat:.4f}, {lng:.4f}" if lat != "?.?" else "????, ?????"
            marker = "  ← HERE" if args.stop == code else ""
            print(f"  {i:<4} {code:<7} {cname:<26} {ename:<30} {coord}{marker}")
        print(f"  {'─' * 70}\n")

        print("Backward direction:")
        print(f"  {'─' * 70}")
        print(f"  {'#':<4} {'Code':<7} Chinese Name             English Name                   Coordinates")
        print(f"  {'─' * 70}")
        for i, stop in enumerate(bwd, 1):
            code = stop.split("/")[0]
            info = stops_data.get(code, {})
            cname = info.get("nameCn", "???")
            ename = info.get("nameEn", "???")
            lat = info.get("lat", "?.?")
            lng = info.get("lng", "?.?")
            coord = f"{lat:.4f}, {lng:.4f}" if lat != "?.?" else "????, ?????"
            marker = "  ← HERE" if args.stop == code else ""
            print(f"  {i:<4} {code:<7} {cname:<26} {ename:<30} {coord}{marker}")
        print(f"  {'─' * 70}\n")

    # Route-specific stop info (only when --stops NOT used, since table above covers it)
    if args.stop and not args.stops:
        print(f"\n{'─' * 60}")
        print(f"📍 STOP: {args.stop}")
        print(f"{'─' * 60}\n")

        stop_in_fwd = args.stop in fwd
        stop_in_bwd = args.stop in bwd

        if not stop_in_fwd and not stop_in_bwd:
            print(f"❌ Stop {args.stop} NOT on route {route_id}")
            print(f"   In forwarding: {stop_in_fwd}")
            print(f"   In backward: {stop_in_bwd}")
        else:
            # Show stop details
            stop_info = stops_data.get(args.stop)
            if stop_info:
                print(f"  Chinese Name: {stop_info['nameCn']}")
                ename = EN_NAME_CACHE.get(args.stop, "")
                if ename:
                    print(f"  English Name: {ename}")
                print(f"  Coordinates: {stop_info['lat']}, {stop_info['lng']}")
            else:
                print(f"  Coordinates: Not in database")

    # Distance calculation
    if args.from_stop and args.to_stop:
        print(f"\n{'═' * 60}")
        print(f"📏 DISTANCE CALCULATION")
        print(f"   From: {args.from_stop}")
        print(f"   To: {args.to_stop}")
        print(f"{'═' * 60}\n")

        result = calc_distance(args.from_stop, args.to_stop, stops_data)

        if "error" in result:
            print(f"⚠️  {result['error']}")
        else:
            print(f"📍 {args.from_stop}: {result['from_name']}")
            print(f"📍 {args.to_stop}: {result['to_name']}")
            print(f"\n  📏 Distance: {result['distance_km']:.2f} km")
            print(f"           = {result['distance_m']} meters")

            # Additional metrics
            walking_min = result['distance_km'] / 5 * 60
            print(f"  🚶 Walking: ~{walking_min:.0f} minutes (5 km/h)")

            # Bus stops estimate
            est_stops = result['distance_km'] * 8  # ~8 stops per km
            print(f"  🚌 Transit: ~{est_stops} stops")

    print(f"\n{'─' * 60}")


def batch_fetch_en(stop_ids: list) -> dict:
    """Batch fetch English names for stop IDs, with caching. Returns {id: en_name}."""
    names = {}
    for sid in stop_ids:
        en = fetch_stop_name_en(sid)
        if en:
            names[sid] = en
    return names


# Main entry point
def main():
    parser = argparse.ArgumentParser(
        description="Macau Bus Route & Stop Information Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python macau_bus_info.py --route 51A
        Show full route 51A info (forward/backward stops)

  python macau_bus_info.py --route 51A --stop T394
        Show route info + details for stop T394

  python macau_bus_info.py --route 51A --stop M93 --to-stop C690/1
        Show distance between first and last stop on 51A

  python macau_bus_info.py --route 71S --stop T394 --info
        Get detailed stop info for T394 (Chinese name, coordinates)

  python macau_bus_info.py --route 51A --stops
        List ALL stops with Chinese + English names + coordinates
        """
    )

    parser.add_argument("--route", "-r", required=True, help="Bus route (e.g., 51A, 71S)")
    parser.add_argument("--stop", "-s", help="Stop to check (e.g., T394)")
    parser.add_argument("--from-stop", dest="from_stop", help="Source stop for distance")
    parser.add_argument("--to-stop", dest="to_stop", help="Destination stop for distance")
    parser.add_argument("--info", action="store_true", help="Full stop details")
    parser.add_argument("--stops", "-S", action="store_true", help="List all stops with Chinese + English names + coordinates")
    parser.add_argument("--data-dir", default="/tmp/mini-macau/data/bus_reference")

    args = parser.parse_args()

    print(f"\n{'═' * 60}")
    print(f"🛑 Macau Bus Information Tool")
    print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═' * 60}\n")

    data_dir = Path(args.data_dir)
    dsat_data = load_local_dsat_data(data_dir)
    stops_data = load_local_stops_data(data_dir)

    if not dsat_data.get("routes"):
        print("⚠️  No DSAT data found. Ensure mini-macau repo data is present.")
        return

    print_route_info(args.route, dsat_data, stops_data, args)


if __name__ == "__main__":
    main()
