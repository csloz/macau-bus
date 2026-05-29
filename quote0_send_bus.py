#!/usr/bin/env python3
"""Fetch live bus data from a stop and send to Quote/0 e-ink display.

Usage:
  python quote0_send_bus.py [route] [stop] [--silent]
  python quote0_send_bus.py -h

Examples:
  python quote0_send_bus.py                    # 51A at T394 (default)
  python quote0_send_bus.py --silent           # No CLI output (cron job)
  python quote0_send_bus.py 72 M93             # Route 72 at stop M93
  python quote0_send_bus.py -h                 # Show help

Parameters:
  route    Bus route (e.g., 51A, 72, 701X) — default: 51A
  stop     Stop ID (e.g., T394, M93) — default: T394
  --silent No CLI output (for cron jobs)
  -h       Show this help message

Environment:
  QUOTE0_DEVICE_ID  Quote/0 device serial (from .env)
  QUOTE0_API_KEY    Dot. API key (from .env)
"""

import subprocess, json, os, sys, urllib.request, math
from datetime import datetime
from pathlib import Path

SCRIPT = os.path.expanduser("~/.hermes/macau_bus_arrivals.py")
API_URL = "https://dot.mindreset.tech/api/authV2/open/device/"
ENV_FILE = os.path.expanduser("~/.hermes/.env")
DATA_DIR = Path(__file__).resolve().parent / "data"

def load_env(key):
    with open(ENV_FILE) as f:
        for line in f:
            if line.startswith(key + "="):
                return line.strip().split("=", 1)[1]
    return None

def load_stops_data():
    """Load stops.json as a dict."""
    p = DATA_DIR / "stops.json"
    if not p.exists():
        return {}
    stops_raw = json.loads(p.read_text())
    return {s["id"]: s for s in stops_raw if s.get("id")}

def load_dsat_data():
    """Load dsat_stops.json."""
    p = DATA_DIR / "dsat_stops.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())

def get_route_stops_with_coords(target_stop, route_id):
    """Get all stops for a route (forward) with coordinates, relative to target_stop."""
    dsat = load_dsat_data()
    stops_dict = load_stops_data()
    route = dsat.get("routes", {}).get(route_id)
    if not route:
        return None

    fwd = route.get("forward", [])
    target_idx = None

    # Find target_stop index in forward stops
    for i, stop in enumerate(fwd):
        code = stop.split("/")[0]
        if code == target_stop:
            target_idx = i
            break

    if target_idx is None:
        return None

    # Build list of (index_from_target, code, lat, lng) for stops ahead
    result = []
    for i, stop in enumerate(fwd):
        if i < target_idx:
            continue  # behind target_stop
        code = stop.split("/")[0]
        s = stops_dict.get(code, {})
        lat = s.get("lat")
        lng = s.get("lng")
        if lat and lng:
            result.append((i - target_idx, code, lat, lng))

    return result

def haversine_km(lat1, lon1, lat2, lon2):
    """Distance in km between two coordinates."""
    R = 6371.0
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    d_lat = lat2_r - lat1_r
    d_lon = lon2_r - lon1_r
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(d_lon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def estimate_time_from_stops(stops_away, target_lat, target_lng):
    """ETA based on real distance to the bus's position."""
    if stops_away is None or target_lat is None:
        return "?"

    # Build list of stops for this route from target_stop
    # We need to find the bus's position: it's N stops ahead of us
    route = None  # We'll pass this from build_message

    # The bus is stops_away ahead. Calculate distance to that position.
    # We'll use an average stop-to-stop distance from the route data.
    return "?"  # Placeholder — see below

def calculate_distance_to_bus(target_lat, target_lng, stops_away, route_stops):
    """Calculate real distance from target_stop to bus N stops ahead."""
    if stops_away is None or not route_stops:
        return None, "?"

    # Find the bus's position (N stops ahead of target)
    for idx, code, lat, lng in route_stops:
        if idx == stops_away:
            dist = haversine_km(target_lat, target_lng, lat, lng)
            # Assume avg urban bus speed ~25 km/h (including stops)
            speed_kmh = 25.0
            mins = dist / (speed_kmh / 60.0)
            return round(dist, 1), f"{round(mins)}m"

    return None, "?"

def fetch_bus_json(stop_id):
    """Fetch live bus data as JSON using --json-output flag."""
    result = subprocess.run(
        ["python", SCRIPT, "--stop", stop_id, "--json-output"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def send_to_quote0(device_id, api_key, title, message):
    """Send title + message + signature to Quote/0 device."""
    now_dt = datetime.now()
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    signature = f"{now_dt.day} {months[now_dt.month-1]} {now_dt.year} {now_dt.strftime('%H:%M')}"

    payload = json.dumps({"title": title, "message": message, "signature": signature}).encode()
    req = urllib.request.Request(
        f"{API_URL}{device_id}/text",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

def build_message(data, target_route, target_stop):
    """Build the message from parsed JSON data for a specific route."""
    routes = sorted(data["routes"].keys())

    # Get target_stop coordinates
    stops_dict = load_stops_data()
    target_coords = stops_dict.get(target_stop, {})
    target_lat = target_coords.get("lat")
    target_lng = target_coords.get("lng")

    route_data = data["routes"].get(target_route)
    if not route_data:
        return f"Routes: {' | '.join(routes)}", None, None

    nearest_stops = route_data.get("stops")
    next_stops = route_data.get("secondNearestStops")

    # Get route stops with coordinates from target_stop
    route_stops = get_route_stops_with_coords(target_stop, target_route)

    # Calculate real distances and ETAs
    nearest_dist = "?"
    nearest_eta = "?"
    next_dist = "?"
    next_eta = "?"

    if nearest_stops is not None and target_lat:
        dist, eta = calculate_distance_to_bus(target_lat, target_lng, nearest_stops, route_stops)
        if dist is not None:
            nearest_dist = f"{dist}km"
            nearest_eta = eta

    if next_stops is not None and target_lat:
        dist, eta = calculate_distance_to_bus(target_lat, target_lng, next_stops, route_stops)
        if dist is not None:
            next_dist = f"{dist}km"
            next_eta = eta

    if nearest_stops == 0:
        nearest_text = "at stop"
    else:
        nearest_text = f"{nearest_stops} stops"

    # Build distance/ETA info
    nearest_info = ""
    if nearest_dist != "?" or nearest_eta != "?":
        parts = []
        if nearest_dist != "?":
            parts.append(nearest_dist)
        if nearest_eta != "?":
            parts.append(nearest_eta)
        nearest_info = f" ({', '.join(parts)})"

    next_info = ""
    if next_dist != "?" or next_eta != "?":
        parts = []
        if next_dist != "?":
            parts.append(next_dist)
        if next_eta != "?":
            parts.append(next_eta)
        next_info = f" ({', '.join(parts)})"

    if next_stops is not None:
        message = f"Routes: {' | '.join(routes)}\nNearest: {nearest_text}{nearest_info}\nNext: {next_stops} stops{next_info}"
    else:
        message = f"Routes: {' | '.join(routes)}"

    return message, nearest_stops, next_stops

def main():
    # Handle -h for help
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return 0

    silent = "--silent" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--silent", "-h", "--help")]

    # Default: 51A at T394
    target_route = args[0] if len(args) >= 1 else "51A"
    stop_id = args[1] if len(args) >= 2 else "T394"

    # Load credentials
    device_id = load_env("QUOTE0_DEVICE_ID")
    api_key = load_env("QUOTE0_API_KEY")

    if not device_id or not api_key:
        print("ERROR: QUOTE0_DEVICE_ID or QUOTE0_API_KEY not found in .env", file=sys.stderr)
        return 1

    try:
        data = fetch_bus_json(stop_id)
    except (json.JSONDecodeError, Exception) as e:
        print(f"ERROR: Failed to fetch bus data: {e}", file=sys.stderr)
        return 1

    title = f"{target_route} | {stop_id}"
    message, _, _ = build_message(data, target_route, stop_id)

    if not silent:
        print(f"[Quote/0] {title}:")
        print(message)

    try:
        result = send_to_quote0(device_id, api_key, title, message)
        if not silent:
            print(f"Result: {result.get('message', 'unknown')}")
        return 0
    except Exception as e:
        print(f"ERROR: Failed to send to Quote/0: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
