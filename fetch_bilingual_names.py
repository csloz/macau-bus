#!/usr/bin/env python3
"""Fetch bilingual stop names from DSAT SuperMap endpoint.

Uses the DSAT SuperMap station endpoint which returns stationName
in the requested language:
  - lang=en → English (Portuguese-style) names like "AL. DA HARMONIA / EDF. LOK KUAN"
  - lang=zh-tw → Chinese names like "和諧廣場/樂群樓"

Updates existing stops.json to include nameEn field alongside nameCn.
Also updates routes.json with bilingual route descriptions.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

REFERENCE_DIR = Path(__file__).resolve().parent / "data"
DSAT_ENDPOINT = "https://bis.dsat.gov.mo/ddbus/common/supermap/point/station"
DSAT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://bis.dsat.gov.mo/macauweb/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en",
}
DSAT_DELAY = 0.15
DSAT_RETRIES = 2


def fetch_route_stops(route_id: str, lang: str) -> dict[str, dict]:
    """Fetch stop names for a route from DSAT SuperMap endpoint.
    
    Returns: {stationCode: {stationName, latitude, longitude}}
    """
    url = f"{DSAT_ENDPOINT}?device=web&HUID={route_id}&keywords=&lang={lang}"
    last_err = None
    for attempt in range(DSAT_RETRIES + 1):
        try:
            r = requests.get(url, headers=DSAT_HEADERS, timeout=15)
            r.raise_for_status()
            payload = r.json()
            # Check response format: {"data": [...], "header": {"status": "000" or "006"}}
            header = payload.get("header", {})
            if isinstance(header, dict):
                status = header.get("status", "")
            else:
                status = header
            # Status "006" also means success (from testing)
            if status not in ("000", "006"):
                return {}
            stops = payload.get("data", []) or []
            return {
                s["stationCode"]: {
                    "stationName": s.get("stationName", ""),
                    "latitude": s.get("latitude", 0),
                    "longitude": s.get("longitude", 0),
                }
                for s in stops if s.get("stationCode")
            }
        except Exception as e:
            last_err = e
            if attempt < DSAT_RETRIES:
                time.sleep(0.5 * (attempt + 1))
    print(f"  Error fetching {route_id} ({lang}): {last_err}", file=sys.stderr)
    return {}


def fetch_bilingual_stops() -> dict[str, dict]:
    """Fetch bilingual stop names from all routes via DSAT SuperMap.
    
    Returns: {stop_code: {stationNameEn, stationNameCn, latitude, longitude}}
    """
    # Load route list
    route_list_path = REFERENCE_DIR / "route_list.json"
    if not route_list_path.exists():
        print("ERROR: route_list.json not found", file=sys.stderr)
        return {}
    
    route_list = json.loads(route_list_path.read_text())
    route_ids = [r["id"] for r in route_list]
    print(f"Found {len(route_ids)} routes")

    all_stops: dict[str, dict] = {}
    seen_codes: set[str] = set()

    for lang in ["en", "zh-tw"]:
        lang_name = "English" if lang == "en" else "Chinese"
        lang_short = "en" if lang == "en" else "zh"
        print(f"\nFetching {lang_name} names...")
        
        for i, rid in enumerate(route_ids):
            stops = fetch_route_stops(rid, lang)
            new_count = 0
            for code, info in stops.items():
                if code not in seen_codes:
                    seen_codes.add(code)
                    new_count += 1
                    if code not in all_stops:
                        all_stops[code] = {}
                    key = "stationNameEn" if lang == "en" else "stationNameCn"
                    all_stops[code][key] = info["stationName"]
                    if info.get("latitude"):
                        all_stops[code]["latitude"] = info["latitude"]
                    if info.get("longitude"):
                        all_stops[code]["longitude"] = info["longitude"]
            
            if i % 10 == 0:
                print(f"  [{i+1:3d}/{len(route_ids)}] {rid:>6} ({lang_short}) → {len(seen_codes)} unique stops")
            
            time.sleep(DSAT_DELAY)

    return all_stops


def update_stops_json(bilingual_stops: dict[str, dict]) -> None:
    """Update stops.json with bilingual names."""
    stops_path = REFERENCE_DIR / "stops.json"
    if not stops_path.exists():
        print("ERROR: stops.json not found", file=sys.stderr)
        return
    
    stops = json.loads(stops_path.read_text())
    print(f"\nLoaded {len(stops)} stops from stops.json")

    # Update each stop
    updated_cn = 0
    updated_en = 0
    for stop in stops:
        code = stop.get("id")
        if code and code in bilingual_stops:
            bio = bilingual_stops[code]
            if "stationNameCn" in bio:
                stop["nameCn"] = bio["stationNameCn"]
                updated_cn += 1
            if "stationNameEn" in bio:
                stop["nameEn"] = bio["stationNameEn"]
                updated_en += 1
    
    # Save enriched stops.json
    stops_path.write_text(
        json.dumps(stops, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    print(f"\nUpdated stops.json:")
    print(f"  Chinese names updated: {updated_cn}")
    print(f"  English names added: {updated_en}")
    
    # Also save a standalone bilingual lookup file
    bilingual_path = REFERENCE_DIR / "stops_bilingual.json"
    bilingual_path.write_text(
        json.dumps(bilingual_stops, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved standalone bilingual data: {bilingual_path}")
    print(f"  Total unique stops: {len(bilingual_stops)}")
    with_cn = sum(1 for s in bilingual_stops.values() if s.get("stationNameCn"))
    with_en = sum(1 for s in bilingual_stops.values() if s.get("stationNameEn"))
    print(f"  With Chinese name: {with_cn}")
    print(f"  With English name: {with_en}")


def update_routes_json(bilingual_stops: dict[str, dict]) -> None:
    """Update routes.json to add bilingual route descriptions.
    
    This is more complex because route descriptions like "關閘 - 媽閣"
    need to be translated. We can extract start/end stops and translate them.
    """
    routes_path = REFERENCE_DIR / "routes.json"
    if not routes_path.exists():
        print("Skipping routes.json update (would need route name translation)")
        return
    
    routes = json.loads(routes_path.read_text())
    print(f"\nLoaded {len(routes)} routes from routes.json")
    
    # For now, just add a comment about bilingual data availability
    for route in routes:
        route_id = route.get("id")
        # Check if we can extract bilingual info from the stops
        if route_id in bilingual_stops:
            pass  # Routes don't directly map to single stops
    
    # Save unchanged (bilingual route descriptions would need manual translation)
    routes_path.write_text(
        json.dumps(routes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Routes.json: bilingual route descriptions need manual translation")


def main():
    print("=" * 60)
    print("Fetching Bilingual Stop Names from DSAT")
    print("=" * 60)
    
    bilingual_stops = fetch_bilingual_stops()
    
    if bilingual_stops:
        update_stops_json(bilingual_stops)
        update_routes_json(bilingual_stops)
    else:
        print("\nNo data fetched. Check network connectivity.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
