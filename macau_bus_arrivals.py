#!/usr/bin/env python3
"""
Macau Bus Tool v3.0 — Route info, live arrivals, stop distances

Shows bus route stop lists, live real-time arrivals, and distances between stops.

Usage:
  python macau_bus_arrivals.py --stop T394                # Live arrivals (full colored)
  python macau_bus_arrivals.py --stop T394 --simple       # Live arrivals (simple)
  python macau_bus_arrivals.py --route 51A                # Route summary
  python macau_bus_arrivals.py --route 51A --stops        # Full stop table
  python macau_bus_arrivals.py --route 51A --stops --stop T394
  python macau_bus_arrivals.py --route 51A --from-stop M93 --to-stop C690
"""
import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import requests

# ---------- API ----------

BASE_URL = "https://bis.dsat.gov.mo/macauweb/routestation/bus"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://bis.dsat.gov.mo/macauweb/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}
TIMEOUT = 15
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"

# English/Portuguese stop name cache (SuperMap API)
EN_NAME_CACHE = {}


def fetch_stop_name_en(stop_id: str) -> str:
    """Fetch English/Portuguese stop name from DSAT SuperMap API."""
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


# ---------- Live bus positions ----------

def fetch_route_live(route_id: str, direction: int = 0):
    """Fetch live bus positions for a route from DSAT API."""
    url = f"{BASE_URL}?routeName={route_id}&dir={direction}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        payload = r.json()
        if payload.get("header") != "000":
            return None
        route_info = payload.get("data", {}).get("routeInfo", [])
        return route_info if route_info else None
    except Exception as e:
        print(f"  !! Live fetch error for route {route_id}: {e}", file=sys.stderr)
        return None


# ---------- Math ----------

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(lat1_r) * math.cos(lat2_r) * math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ---------- Data loading ----------

def load_stops(data_dir: Path) -> dict:
    """Load stops.json (full records with route_ids, coords, Chinese names)."""
    p = data_dir / "stops.json"
    if not p.exists():
        return {}
    try:
        stops = json.loads(p.read_text())
        return {
            s["id"]: s
            for s in stops
            if s.get("id")
        }
    except Exception:
        return {}


def load_routes(data_dir: Path) -> dict:
    """Load routes.json (service info: frequency, hours)."""
    p = data_dir / "routes.json"
    if not p.exists():
        return {}
    try:
        routes = json.loads(p.read_text())
        return {r["id"]: r for r in routes if r.get("id")}
    except Exception:
        return {}


def load_dsat_stops(data_dir: Path) -> dict:
    """Load dsat_stops.json (DSAT route stop sequences)."""
    p = data_dir / "dsat_stops.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


# ---------- Live arrivals (existing) ----------

def find_route_direction(route_id, stop_id, live_data):
    """Find stop index in live route data."""
    targets = [s["staCode"].split("/")[0] for s in live_data]
    if stop_id in targets:
        return targets, targets.index(stop_id)
    return None, None


def estimate_arrivals_live(stop_id, stops_data, routes_data, live_fetcher):
    """Query live API for each route serving the stop."""
    services = stops_data.get(stop_id, {})
    route_ids = services if isinstance(services, list) else []
    if not route_ids:
        for sid, stop in stops_data.items():
            rids = stop.get("route_ids", [])
            if stop_id in rids or sid == stop_id:
                route_ids = rids
                break

    arrivals = {}
    for route_id in sorted(route_ids):
        live_fwd = live_fetcher(route_id, 0)
        live_bwd = live_fetcher(route_id, 1)

        best_dir = None
        best_dir_idx = None
        best_stops = None

        if live_fwd:
            stops_list, idx = find_route_direction(route_id, stop_id, live_fwd)
            if idx is not None:
                best_dir = 0
                best_dir_idx = idx
                best_stops = live_fwd

        if live_bwd:
            stops_list, idx = find_route_direction(route_id, stop_id, live_bwd)
            if idx is not None and (best_dir is None or idx < best_dir_idx):
                best_dir = 1
                best_dir_idx = idx
                best_stops = live_bwd

        if best_stops is None:
            continue

        all_buses_info = []
        total_buses = 0

        for station in best_stops:
            buses = station.get("busInfo", [])
            if not buses:
                continue
            sta_clean = station["staCode"].split("/")[0]
            all_sta = [s["staCode"].split("/")[0] for s in best_stops]
            try:
                current_idx = all_sta.index(sta_clean)
            except ValueError:
                continue

            if current_idx - best_dir_idx > 0:
                continue  # bus already passed

            total_buses += len(buses)
            stops_away = best_dir_idx - current_idx

            for bus in buses:
                plate = bus.get("busPlate", "?")
                speed = int(bus.get("speed") or 0)
                all_buses_info.append((stops_away, plate, speed))

        all_buses_info.sort(key=lambda x: x[0])
        if not all_buses_info:
            continue

        nearest_stops = all_buses_info[0][0]
        nearest_plate = all_buses_info[0][1]
        nearest_speed = all_buses_info[0][2]
        second = all_buses_info[1] if len(all_buses_info) > 1 else (None, None, None)

        status = "?"
        if nearest_stops == 0:
            status = "● AT STOP"
        elif nearest_stops <= 3:
            status = f"{nearest_stops} stop{'s' if nearest_stops > 1 else ''}"
        elif nearest_stops <= 8:
            status = f"{nearest_stops} stops"
        else:
            status = f"{nearest_stops} stops"

        svc = routes_data.get(route_id, {})
        avg_freq = svc.get("avg_freq", svc.get("headway", 10))

        is_express = route_id in ["71S", "701X"]
        route_color = C.ORANGE if is_express else C.BLUE

        arrivals[route_id] = {
            "stops": nearest_stops,
            "status": status,
            "direction": "→" if best_dir == 0 else "←",
            "color": route_color,
            "frequency": int(avg_freq),
            "totalBuses": total_buses,
            "nearestPlate": nearest_plate,
            "nearestSpeed": nearest_speed,
            "secondNearestStops": second[0],
            "secondNearestPlate": second[1],
            "secondNearestSpeed": second[2],
            "lastUpdate": datetime.now().strftime("%H:%M:%S"),
        }

    return arrivals


# ---------- Display functions ----------

class C:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BLUE = "\033[34m"
    ORANGE = "\033[33m"
    GREEN = "\033[32m"
    YELLOW = "\033[93m"
    CYAN = "\033[36m"


def format_simple(stop_id, chinese_name, english_name, arrivals):
    """Simple output: stop name, active routes, next arrivals."""
    label = chinese_name
    if english_name:
        label += f"  ({english_name})"
    print(label)
    print(f"[{datetime.now().strftime('%H:%M')}]")

    if not arrivals:
        print("  No buses approaching")
        return

    for route_id in sorted(arrivals):
        info = arrivals[route_id]
        arrow = info["direction"]
        line = f"  Route {route_id}{arrow}"
        if info["stops"] == 0:
            line += " — AT STOP"
        else:
            line += f" — {info['stops']} stop{'s' if info['stops'] != 1 else ''} away"
        line += f"  [buses: {info['totalBuses']}]"
        print(line)
        plate = info.get("nearestPlate", "?")
        speed = info.get("nearestSpeed", 0)
        print(f"    Nearest: {plate} @ {speed} km/h")
        if info.get("secondNearestStops") is not None:
            s_plate = info.get("secondNearestPlate", "?")
            s_stops = info.get("secondNearestStops")
            s_speed = info.get("secondNearestSpeed", 0)
            print(f"    2nd:     {s_plate} ({s_stops} stop{'s' if s_stops != 1 else ''}) @ {s_speed} km/h")


def format_display(stop_id, chinese_name, english_name, arrivals, route_info):
    """Full colored display mimicking physical bus stop screens."""
    current_time = datetime.now().strftime("%H:%M:%S")
    stop_line = f"{stop_id:<5} {chinese_name}"
    if english_name:
        stop_line += f"  ({english_name})"

    print(f"\n{C.BOLD}{'═' * 70}{C.RESET}")
    print(f"  🚌 {C.BOLD}Macau Bus Real-Time Arrivals{C.RESET}  (Live)")
    print(f"{'═' * 70}")
    print(f"  🚏 {stop_line:<38} ⏰ {current_time}  ⛅ 27°C")
    print(f"{'═' * 70}")
    print(f"\n  Last update: {current_time}")
    print()
    print(f"  {'ROUTE':<8} {'POSITIONS':>16} {'BUSES':>7}  {'DIRECTION'}")
    print(f"  ───────           ────────     ───────     ──────────")

    for route_id, info in sorted(arrivals.items()):
        route_color = C.ORANGE if route_id in ["71S", "701X"] else C.BLUE
        pos_str = info["status"]
        bus_str = str(info["totalBuses"])
        print(f"  {route_color}{route_id:<8}{C.RESET}  {route_color}{pos_str:>16}{C.RESET}  {bus_str:>7}  {info['color']}{info['direction']}{C.RESET}")

        if info["stops"] is not None and info["stops"] != "?" and (
            info["stops"] == 0 or str(info["stops"]).startswith(("0", "1", "2", "3", "4"))
        ):
            plate = info.get("nearestPlate", "?")
            speed = info.get("nearestSpeed", 0)
            print(f"  {C.YELLOW}     Nearest: {plate} @ {speed} km/h{C.RESET}")
            print(f"  {C.YELLOW}     Freq ~{info['frequency']} min{C.RESET}")
            if info.get("secondNearestStops") is not None:
                s_plate = info.get("secondNearestPlate", "?")
                s_stops = info.get("secondNearestStops")
                s_speed = info.get("secondNearestSpeed", 0)
                print(f"  {C.CYAN}     Next: {s_plate} ({s_stops} stop{'s' if s_stops > 1 else ''}) @ {s_speed} km/h{C.RESET}")

    if arrivals:
        print(f"\n{C.YELLOW}{'─' * 70}{C.RESET}")
        real = {r: i for r, i in arrivals.items() if i["stops"] is not None and i["stops"] != "?"}
        if real:
            nearest_r, nearest_i = min(real.items(), key=lambda x: x[1]["stops"])
            svc = route_info.get(nearest_r, {})
            sh, sm = svc.get("service_start", 6), svc.get("service_start_m", 0)
            eh, em = svc.get("service_end", 20), svc.get("service_end_m", 35)
            freq = svc.get("avg_freq", svc.get("headway", 10))
            print(f"  {C.ORANGE}  ⚡ ACTIVE: Route {nearest_r:<5} - {nearest_i['status']:<16}{C.RESET}")
            print(f"  {C.ORANGE}  First: {sh:02d}:{sm:02d} | Last: {eh:02d}:{em:02d} | Freq ~{freq} min{C.RESET}")
            print(f"  {C.ORANGE}{'─' * 70}{C.RESET}")
    else:
        print(f"\n{C.YELLOW}  No buses detected on any route serving this stop.{C.RESET}")

    print(f"\n  Source: DSAT Live API (bis.dsat.gov.mo)")
    print(f"  Refreshed: {datetime.now().strftime('%H:%M:%S')}\n")


# ---------- Route info display (from macau_bus_info.py) ----------

def calc_distance(from_stop: str, to_stop: str, stops_data: dict) -> dict:
    """Calculate distance between two stops."""
    from_data = stops_data.get(from_stop)
    to_data = stops_data.get(to_stop)
    if not from_data or not to_data:
        return {"error": "One or both stops not found"}
    if not from_data.get("lat") or not from_data.get("lng") or not to_data.get("lat") or not to_data.get("lng"):
        return {"error": "Coordinates missing for one or both stops"}

    distance_km = haversine_distance_km(from_data["lat"], from_data["lng"], to_data["lat"], to_data["lng"])

    return {
        "from_stop": from_stop,
        "from_name": from_data.get("nameCn", ""),
        "to_stop": to_stop,
        "to_name": to_data.get("nameCn", ""),
        "distance_km": round(distance_km, 2),
        "distance_m": round(distance_km * 1000),
    }


def print_route_info(route_id: str, dsat_data: dict, stops_data: dict, args: argparse.Namespace):
    """Print route details, optional full stop list, and distance."""
    routes = dsat_data.get("routes", {})
    route = routes.get(route_id)

    if not route:
        print(f"❌ Route {route_id} not found")
        print(f"   Available routes (sample): {list(routes.keys())[:10]}")
        return

    print(f"\n{'▬' * 60}")
    print(f"🚌 ROUTE: {route_id}")
    print(f"{'▬' * 60}\n")

    fwd = route.get("forward", [])
    bwd = route.get("backward", [])
    fwd_ok = route.get("forwardOk", True)
    bwd_ok = route.get("backwardOk", True)

    if not args.stops and not args.from_stop:
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

    elif args.stops or args.from_stop:
        # Collect all unique stop codes from both directions
        all_codes = set()
        for s in fwd:
            all_codes.add(s.split("/")[0])
        for s in bwd:
            all_codes.add(s.split("/")[0])

        # Fetch English/Portuguese names from SuperMap API
        for code in all_codes:
            en = fetch_stop_name_en(code)
            if en:
                stops_data[code]["nameEn"] = en

        # Print stop table
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
            coord = f"{lat:.4f}, {lng:.4f}" if isinstance(lat, float) else "????, ?????"
            marker = "  ← HERE" if args.stop and args.stop == code else ""
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
            coord = f"{lat:.4f}, {lng:.4f}" if isinstance(lat, float) else "????, ?????"
            marker = "  ← HERE" if args.stop and args.stop == code else ""
            print(f"  {i:<4} {code:<7} {cname:<26} {ename:<30} {coord}{marker}")
        print(f"  {'─' * 70}\n")

    # Route-specific stop info (only when --stop given but NOT --stops)
    if args.stop and not args.stops:
        stop_in_fwd = args.stop in fwd
        stop_in_bwd = args.stop in bwd

        if not stop_in_fwd and not stop_in_bwd:
            print(f"\n{'─' * 60}")
            print(f"❌ Stop {args.stop} NOT on route {route_id}")
        else:
            print(f"\n{'─' * 60}")
            print(f"📍 STOP: {args.stop}")
            print(f"{'─' * 60}\n")
            stop_info = stops_data.get(args.stop)
            if stop_info:
                print(f"  Chinese Name: {stop_info.get('nameCn', '???')}")
                ename = EN_NAME_CACHE.get(args.stop, "")
                if ename:
                    print(f"  English Name: {ename}")
                print(f"  Coordinates: {stop_info.get('lat', '?')}, {stop_info.get('lng', '?')}")

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
            walking_min = result['distance_km'] / 5 * 60
            print(f"  🚶 Walking: ~{walking_min:.0f} minutes (5 km/h)")
            est_stops = result['distance_km'] * 8
            print(f"  🚌 Transit: ~{est_stops} stops")

    print(f"\n{'─' * 60}")


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(
        description="Macau Bus Tool — Live arrivals, route info, stop distances",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python macau_bus_arrivals.py --stop T394                  # Live arrivals (full)
  python macau_bus_arrivals.py --stop T394 --simple         # Live arrivals (simple)
  python macau_bus_arrivals.py --route 51A                  # Route summary
  python macau_bus_arrivals.py --route 51A --stops          # Full stop table
  python macau_bus_arrivals.py --route 51A --stops --stop T394
  python macau_bus_arrivals.py --route 51A --from-stop M93 --to-stop C690
        """,
    )

    # Route mode
    parser.add_argument("--route", "-r", help="Bus route (e.g., 51A, 71S)")
    parser.add_argument("--stops", "-S", action="store_true",
                        help="List all stops with Chinese + Portuguese names + coordinates")

    # Stop mode
    parser.add_argument("--stop", "-s", help="Stop ID for live arrivals (e.g., T394, M1)")
    parser.add_argument("--simple", action="store_true",
                        help="Simple output: stop name, active routes, next arrivals")

    # Distance
    parser.add_argument("--from-stop", dest="from_stop", help="Source stop for distance")
    parser.add_argument("--to-stop", dest="to_stop", help="Destination stop for distance")

    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                        help="Path to cached reference data")

    args = parser.parse_args()

    # Normalize user input to uppercase (data keys are uppercase)
    args.route = (args.route or "").upper()
    args.stop = (args.stop or "").upper()
    args.from_stop = (args.from_stop or "").upper()
    args.to_stop = (args.to_stop or "").upper()

    data_dir = Path(args.data_dir)

    if args.route:
        # Route mode — metadata only
        print(f"\n{'═' * 60}")
        print(f"🛑 Macau Bus Information Tool")
        print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'═' * 60}\n")

        dsat_data = load_dsat_stops(data_dir)
        if not dsat_data.get("routes"):
            print("⚠️  No DSAT data found at", data_dir)
            return

        stops_data = load_stops(data_dir)
        if not stops_data:
            print("⚠️  No stop data found at", data_dir)
            return

        print_route_info(args.route, dsat_data, stops_data, args)

    elif args.stop:
        # Live arrivals mode
        stops_data = load_stops(data_dir)
        if not stops_data:
            print(f"⚠️  No stop data found at {data_dir}")
            return

        route_info = load_routes(data_dir)

        stop_data = stops_data.get(args.stop, {})
        chinese_name = stop_data.get("nameCn", "Unknown")
        english_name = fetch_stop_name_en(args.stop)

        live_fetcher = lambda rid, dir=0: fetch_route_live(rid, dir)

        print(f"\n  ⏳ Fetching live data for stop {args.stop}...", file=sys.stderr)
        arrivals = estimate_arrivals_live(args.stop, stops_data, route_info, live_fetcher)

        if args.simple:
            format_simple(args.stop, chinese_name, english_name, arrivals)
        else:
            format_display(args.stop, chinese_name, english_name, arrivals, route_info)
    else:
        print("Use --route <ROUTE> or --stop <STOP_ID>.\n")
        parser.print_help()


if __name__ == "__main__":
    main()
