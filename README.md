# 📋 Macau Bus Information Tool

A Python script to query Macau bus route information and calculate distances between stops.

All scripts are in the `~/macau-bus/` directory.

## 📍 Data Sources

All data fetched from **DSAT** (Macau Bus Authority):
- https://bis.dsat.gov.mo
- Official bus routes and stop lists
- Stop coordinates with Chinese names

The local reference data is in `~/macau-bus/data/`:
- `dsat_stops.json` — Per-direction stop sequences from DSAT live API
- `routes.json` — Service hours, frequencies, stop sequences with coordinates
- `stops.json` — Stop IDs, Chinese names, GPS coordinates
- `bridges.json` — Macau-Taipa Bridge geometry
- `bridge_routes.json` — Which routes use which channel-crossing bridge

## 🛠️ Usage

### Basic: Show Route Info
```bash
python ~/macau-bus/macau_bus_info.py --route 51A
```

### Check a Specific Stop
```bash
python ~/macau-bus/macau_bus_info.py --route 51A --stop T394
```

### Distance Between Two Stops
```bash
python ~/macau-bus/macau_bus_distance.py --from-stop M93 --to-stop T394
```

### Get Full Stop Details
```bash
python ~/macau-bus/macau_bus_info.py --route 51A --stop T394 --info
```

## 🔄 Regenerating Reference Data

To re-fetch bus stop sequences from the live DSAT API:
```bash
python ~/macau-bus/regenerate_bus_reference.py --dsat-only
```

Or a full update (requires Playwright for motransportinfo.com):
```bash
python ~/macau-bus/regenerate_bus_reference.py --bridges
```

## 📡 DSAT API Endpoints (Detailed)

### Primary Endpoint
`https://bis.dsat.gov.mo/macauweb/routestation/bus?routeName=X&dir=0|1`

Returns per-route stop sequences with live GPS bus positions (plates, speeds, status).

### SuperMap Supplementary Endpoints

These are location-based search endpoints under `/ddbus/common/supermap/`. They are NOT route-specific — they search across the entire Macau bus network.

#### Station Search Endpoint
```
GET /ddbus/common/supermap/point/station?device=web&HUID=XX&keywords=Y&lang=en
```

**Parameters:**
| Param | Description | Example |
|-------|-------------|---------|
| `device` | Fixed value | `web` |
| `HUID` | Session/user ID | `33`, `41` |
| `keywords` | Search term | `T394`, `Venetian`, `新城大馬路` |
| `lang` | Language | `en` |

**Response format:**
```json
{
  "header": "000",
  "data": [
    {
      "stationCode": "T394",
      "stationName": "New City Avenue / Venetian",
      ...
    }
  ]
}
```

**Notes:**
- Status `"000"` = success with data, `"1000"` = no data (not an error)
- Returns results from the entire network, not filtered to a specific route
- Keywords support English, Chinese, and stop codes

#### Other SuperMap Endpoints

| Endpoint | Path | Notes |
|----------|------|-------|
| Route Traffic | `/ddbus/common/supermap/route/traffic` | Returns `{"data":"","header":{"status":"1000"}}` without params |
| Zone Lookup | `/ddbus/common/zone/findAllZone` | Zone-based search |
| Station Capacity | `/ddbus/common/station/capacity` | Station capacity info |

### Required Headers (ALL endpoints)

## 📝 Examples

### Example 1: Route 51A Overview
```bash
$ python macau_bus_info.py --route 51A
```
Output:
- Forward: 21 stops (M93 → C690/1)
- Backward: 18 stops (C690/1 → M93)
- Availability status

### Example 2: Stop Location (T394 on Route 51A)
```bash
$ python macau_bus_info.py --route 51A --stop T394
```
Output:
- Stop T394: 新城大馬路／威尼斯人 (Venetian Macao)
- Coordinates: 22.148614, 113.558158

### Example 3: Distance Calculation
```bash
$ python macau_bus_info.py --route 51A --from-stop M93 --to-stop T394
```
Output:
- From: M93 (海擎天總站)
- To: T394 (新城大馬路／威尼斯人)
- Distance: 6.62 km
- Walking time: ~79 minutes
- Transit stops: ~53 stops

## 🙋 What This Script Does

1. **Route Info**: Shows forward/backward stop lists for any bus route
2. **Stop Check**: Verifies if a stop is on the specified route
3. **Distance**: Calculates real-world distance between stops using coordinates
4. **Estimates**: Provides walking time and transit stop count

## 📂 Installed Location

`~/macau-bus/macau_bus_info.py`

## 💡 Tips

- **Stop IDs**: Start with letters like `T`, `M`, `C`, `H` (e.g., T394, M93)
- **Not on route?**: The script will tell you if a stop isn't on that route
- **Distance only**: Works between ANY two stops, not just on same route
- **Coordinates**: All stops have lat/lng for real distance calculation
