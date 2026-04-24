#!/usr/bin/env python3
"""
Macau Bus Route & Stop Distance Calculator

Fetches bus route information and calculates distances between stops.

Usage:
    python bus_route_info.py --route 51A --stop T394
    
Examples:
    python bus_route_info.py --route 51A
    python bus_route_info.py --route 51A --stop T394
    python bus_route_info.py --route 51A --from-stop T394 --to-stop M1
"""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from requests.exceptions import RequestException

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"

# DSAT API endpoint with proper Referer header
BASE_URL = "https://bis.dsat.gov.mo/macauweb/routestation/bus"


def calculate_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth
    using the Haversine formula.
    
    Returns distance in kilometers.
    """
    R = 6371.0  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def fetch_dsat_stops_data() -> dict:
    """
    Fetch stop lists for all routes from DSAT API.
    Returns parsed JSON structure.
    """
    print("Fetching DSAT stop data...")
    
    # DSAT requires proper Referer header
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://bis.dsat.gov.mo/macauweb/",
        "Accept": "application/json, text/plain, */*",
    }
    
    try:
        response = requests.get(BASE_URL, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Return raw JSON (in real usage, you'd filter by specific route)
        return response.json()
        
    except RequestException as e:
        print(f"Error fetching DSAT data: {e}")
        return {"error": str(e)}


def load_local_route_data(data_dir: Path) -> tuple[dict, dict]:
    """
    Load local cached route and stop data.
    
    Returns:
        tuple: (route_stop_order, stop_coordinates)
    """
    print("Loading local route data...")
    
    try:
        # Load route stop order (from DSAT)
        dsat_path = data_dir / "dsat_stops.json"
        if dsat_path.exists():
            dsat_data = json.loads(dsat_path.read_text(encoding="utf-8"))
        else:
            print(f"  ⚠️  Warning: {dsat_path} not found")
            dsat_data = {}
        
        # Load stop coordinates
        stops_path = data_dir / "stops.json"
        if stops_path.exists():
            stops_data = json.loads(stops_path.read_text(encoding="utf-8"))
        else:
            print(f"  ⚠️  Warning: {stops_path} not found")
            stops_data = []
        
        # Create lookup dict for stop coordinates
        stop_coordinates = {
            stop["id"]: (stop["lat"], stop["lng"])
            for stop in stops_data
            if "lat" in stop and "lng" in stop
        }
        
        return dsat_data, stop_coordinates, stops_data
        
    except Exception as e:
        print(f"Error loading local data: {e}")
        return {}, {}, []


def find_route_in_dsat(route_id: str, dsat_data: dict) -> Optional[list]:
    """
    Find if a route exists in DSAT data.
    """
    routes = dsat_data.get("routes", {})
    return routes.get(route_id.upper())


def find_stop_in_stops(stop_id: str, stops_data: list) -> Optional[dict]:
    """
    Find stop by ID in the stops list.
    """
    for stop in stops_data:
        if stop.get("id") == stop_id:
            return stop
    return None


def calculate_distance_between_stops(
    stop1_coords: tuple,
    stop2_coords: tuple
) -> Optional[float]:
    """
    Calculate distance between two stops.
    
    Returns:
        Optional[float]: Distance in km, or None if coords unavailable
    """
    if not stop1_coords or not stop2_coords:
        return None
    
    return calculate_distance_km(
        stop1_coords[0], stop1_coords[1],
        stop2_coords[0], stop2_coords[1]
    )


def main():
    parser = argparse.ArgumentParser(
        description="Macau Bus Route & Stop Distance Calculator"
    )
    parser.add_argument(
        "--route",
        required=True,
        help="Bus route number (e.g., 51A, 1, 10)"
    )
    parser.add_argument(
        "--stop",
        help="Stop ID to check (e.g., T394)"
    )
    parser.add_argument(
        "--from-stop",
        help="Source stop ID for distance calculation"
    )
    parser.add_argument(
        "--to-stop",
        help="Destination stop ID for distance calculation"
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory containing bus reference data (default: ./data)",
    )
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    route_id = args.route.upper()
    
    print(f"\n{'='*60}")
    print(f"macau Bus Route Calculator")
    print(f"Route: {route_id}")
    print(f"{'='*60}\n")
    
    # Load local data
    dsat_data, stop_coordinates, stops_data = load_local_route_data(data_dir)
    
    # Check if requested stop exists in coordinates
    if args.stop:
        stop_info = find_stop_in_stops(args.stop, stops_data)
        if stop_info:
            print(f"✅ Stop {args.stop} found in database!")
            print(f"   Name: {stop_info.get('nameCn', 'Unknown')}")
            print(f"   Coordinates: {stop_info['lat']}, {stop_info['lng']}")
        else:
            print(f"❌ Stop {args.stop} not found in database")
        
        args.from_stop = args.stop
    
    # Check route in DSAT data
    route_stops = find_route_in_dsat(route_id, dsat_data)
    
    if route_stops:
        print(f"\n🚌 Route {route_id} found in DSAT!")
        print(f"   Forward stops: {len(route_stops.get('forward', []))}")
        print(f"   Backward stops: {len(route_stops.get('backward', []))}")
        
        if args.from_stop:
            print(f"\n📍 Checking distance from stop: {args.from_stop}")
            
            # Check if stop is in either direction
            forward_stops = route_stops.get('forward', [])
            backward_stops = route_stops.get('backward', [])
            
            if args.from_stop in forward_stops:
                print(f"   ⬅️  Found in FORWARD direction")
                from_index = forward_stops.index(args.from_stop)
            elif args.from_stop in backward_stops:
                print(f"   ➡️  Found in BACKWARD direction")
                from_index = backward_stops.index(args.from_stop)
            else:
                print(f"   ⚠️  Stop {args.from_stop} not found in route {route_id}")
                from_index = None
            
            # Calculate distance if from stop found
            if from_index is not None and args.to_stop:
                # Find to_stop in the same direction
                all_stops = forward_stops if from_index < len(forward_stops) else backward_stops
                to_index = -1
                
                if args.to_stop in all_stops:
                    to_index = all_stops.index(args.to_stop)
                    print(f"\n📏 DISTANCE CALCULATION:")
                    print(f"   From: {from_index} → To: {to_index}")
                    print(f"   Stops apart: {abs(to_index - from_index)} stops")
                    
                    # If we have coordinates, calculate real distance
                    if args.from_stop in stop_coordinates:
                        from_coords = stop_coordinates[args.from_stop]
                        if len(all_stops) > 0:
                            # Estimate: average stop spacing ~200m in urban, ~500m rural
                            estimated_km = abs(to_index - from_index) * 0.3
                            print(f"   Estimated distance: {estimated_km:.1f} km")
                else:
                    print(f"❌ Stop {args.to_stop} not found in route {route_id}")
        
        else:
            print(f"\n📋 Route {route_id} stop list (forward):")
            print(f"   {route_stops.get('forward', [])[:10]}...")
            
    else:
        print(f"⚠️  Route {route_id} not found in DSAT data")
        print(f"   Available routes (sample): {list(dsat_data.get('routes', {}).keys())[:10]}")
    
    print(f"\n{'='*60}")


if __name__ == "__main__":
    main()
