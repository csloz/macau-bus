# 📋 Macau Bus Tool

Python scripts to query Macau bus route information, live arrivals, and stop distances.

Main script: `macau_bus_arrivals.py` (unified tool — route info, live arrivals, stop distances)
Legacy backup: `macau_bus_info.py` (route/stop info only, same functionality)

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

## 🚌 Live Bus Arrivals (`macau_bus_arrivals.py`)

The unified tool — live arrivals, route info, stop distances, and stop lookup.

### Live Arrivals at a Stop

Full screen-style display with colored routes, bus plates, speeds, and frequency info:

```bash
python ~/macau-bus/macau_bus_arrivals.py --stop T394
```

Simple compact output (stop name, active routes, next arrivals):

```bash
python ~/macau-bus/macau_bus_arrivals.py --stop T394 --simple
```

Short flags work too:

```bash
python ~/macau-bus/macau_bus_arrivals.py -s T394 -S
```

Case-insensitive input (lowercase or uppercase):

```bash
python ~/macau-bus/macau_bus_arrivals.py --stop t394
```

Example output:
```
  新城大馬路／威尼斯人 (AV. CIDADE NOVA/ VENETIAN) [16:53]
  Route 51A→ — 1 stop away  [buses: 6]
    Nearest: AA6848 @ 45 km/h
    2nd:     AA7167 (6 stops) @ 18 km/h
  Route 701X→ — 1 stop away  [buses: 4]
    Nearest: AA2563 @ 22 km/h
    2nd:     AA7454 (11 stops) @ 29 km/h
  Route 72→ — 3 stops away  [buses: 4]
    Nearest: MZ8269 @ 12 km/h
    2nd:     MZ8525 (12 stops) @ 11 km/h
```

### Route Info

Basic route summary (forward/backward stop counts, terminals):

```bash
python ~/macau-bus/macau_bus_arrivals.py --route 51A
```

All stops with Chinese names, English/Portuguese names, and GPS coordinates:

```bash
python ~/macau-bus/macau_bus_arrivals.py --route 51A --stops
```

Highlight your stop location:

```bash
python ~/macau-bus/macau_bus_arrivals.py --route 51A --stops --stop T394
```

### Distance Between Two Stops

```bash
python ~/macau-bus/macau_bus_arrivals.py --route 51A --from-stop M93 --to-stop C690
```

Output:
```
  Distance: 6.62 km
           = 6620 meters
  Walking: ~79 minutes (5 km/h)
  Transit: ~53 stops
```

### JSON Output (programmatic consumption)

```bash
python ~/macau-bus/macau_bus_arrivals.py --stop T394 --json-output
```

Returns structured JSON with all routes serving the stop:

```json
{
  "stopId": "T394",
  "chineseName": "新城大馬路／威尼斯人",
  "englishName": "AV. CIDADE NOVA/ VENETIAN",
  "timestamp": "16:53",
  "routes": {
    "51A→": {
      "stops": 1,
      "status": "active",
      "direction": "→",
      "frequency": 8,
      "totalBuses": 6,
      "lastUpdate": "2026-05-12T08:53:00+08:00",
      "nearestPlate": "AA6848",
      "nearestSpeed": 45,
      "secondNearestStops": 6,
      "secondNearestPlate": "AA7167",
      "secondNearestSpeed": 18
    }
  }
}
```

### Full Flag Reference

| Flag | Short | Description |
|------|-------|-------------|
| `--route` | `-r` | Bus route (e.g. 51A, 71S) |
| `--stop` | `-s` | Stop ID for live arrivals (e.g. T394, M1) |
| `--stops` | `-S` | List all stops (Chinese + English + coords) |
| `--simple` | | Simple output format for live arrivals |
| `--json-output` | | Output results as a JSON string for parsing |
| `--from-stop` | | Source stop for distance calculation |
| `--to-stop` | | Destination stop for distance calculation |

### What Each Output Shows

- **Route**: Bus line number (orange for express routes like 71S, 701X)
- **Positions**: How far the nearest bus is (e.g. "1 stop", "AT STOP")
- **Buses**: Total active buses on that route for the stop
- **Direction**: Arrow indicating direction (→ forward, ← backward)
- **Nearest**: License plate and speed of closest bus
- **Freq**: Average headway in minutes
- **Next**: Second closest bus details

## ⚡ Quick Bus Check (`macau_bus_quick.py`)

Ultra-simple output for casual queries. When you just want to know "when's the next bus?" without all the details.

### Basic Usage

Minimal output: stop name, time, routes and stops away:

```bash
python ~/macau-bus/macau_bus_quick.py --stop T394
```

Example output:
```
新城大馬路／威尼斯人
AV. CIDADE NOVA/ VENETIAN
17:06
Route 51A: 1 stop away
Route 701X: 5 stops away
Route 72: 5 stops away

Closest: Route 51A at 1 stop away.
```

### Filter to One Route

```bash
python ~/macau-bus/macau_bus_quick.py --stop T394 -r 51A
```

Output:
```
新城大馬路／威尼斯人
17:06
Route 51A: 2 stops away

Closest: Route 51A at 2 stops away.
```

### Flag Reference

| Flag | Short | Description |
|------|-------|-------------|
| `--stop` | | Stop ID (required, e.g. T394, M1) |
| `-r` | `--route` | Optional: filter to one route |

### When to Use

Use `macau_bus_quick.py` when you want a bare-minimum answer:
- "Is my bus coming soon?"
- Quick check without full table or colors
- Easy to paste into messages or summaries

## 📟 Quote/0 E-Ink Display (`quote0_send_bus.py`)

Sends live bus arrival data to a **Quote/0** (Dot. mindreset.tech) e-ink display,
with real distance-based ETA from stop coordinates.

### Usage

Default (51A at T394):
```bash
python ~/macau-bus/quote0_send_bus.py
```

Custom route + stop:
```bash
python ~/macau-bus/quote0_send_bus.py 72 M93
```

Silent mode (no CLI output, for cron jobs):
```bash
python ~/macau-bus/quote0_send_bus.py --silent
```

Show help:
```bash
python ~/macau-bus/quote0_send_bus.py -h
```

### Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `route` | Bus route (e.g., 51A, 72, 701X) | `51A` |
| `stop` | Stop ID (e.g., T394, M93) | `T394` |
| `--silent` | No CLI output (for cron) | off |
| `-h` | Show help message | — |

### Environment Variables

Set in `~/.hermes/.env`:
- `QUOTE0_DEVICE_ID` — Quote/0 device serial (e.g., `48F6EE5476A8`)
- `QUOTE0_API_KEY` — Dot. API key

### Output Format

The Quote/0 display shows:
- **Title**: `{route} | {stop}` (e.g., `51A | T394`)
- **Message**: Routes served, nearest bus (stops + distance + ETA), next bus

Example display:
```
51A | T394
Routes: 51A | 701X | 72
Nearest: 2 stops (0.8km, 2m)
Next: 4 stops (2.2km, 5m)
```

The footer shows the timestamp in `D Mon YYYY HH:MM` format.

### How It Works

1. Fetches live bus data from `macau_bus_arrivals.py --json-output`
2. Looks up stop coordinates from `data/stops.json`
3. Calculates real distance (km) and ETA (minutes) from your position to the bus using haversine formula
4. Sends title + message + signature to Quote/0 via Dot. API

### System Cron Setup

Add to your crontab (`crontab -e`):
```cron
*/5 * * * * /usr/bin/python3 ~/macau-bus/quote0_send_bus.py --silent
```

This runs every 5 minutes with no CLI output.

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
