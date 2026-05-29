# Macau Bus Reference Data

Exported: 2026-04-23

## Files

| File | Source | Description |
|------|--------|-------------|
| dsat_stops.json | DSAT live API | Per-route stop sequences (forward/backward), fetched live from bis.dsat.gov.mo |
| route_list.json | motransportinfo.com | Route IDs and Chinese descriptions |
| routes.json | motransportinfo.com | Service hours, frequencies, stop sequences with coordinates |
| stops.json | motransportinfo.com | Stop IDs, Chinese names, GPS coordinates, route associations |
| bridges.json | Overpass API (OSM) | Macau-Taipa Bridge geometry (road-snapped polyline) |
| bridge_routes.json | Hand-maintained | Which routes use which channel-crossing bridge |

## DSAT API Endpoints

**Primary endpoint** (route stop sequences + live bus positions):
`https://bis.dsat.gov.mo/macauweb/routestation/bus?routeName=X&dir=0|1`

**SuperMap supplementary endpoints** (location-based, network-wide search):
- `/ddbus/common/supermap/route/traffic` — Route traffic summary
- `/ddbus/common/zone/findAllZone` — Zone lookup by location
- `/ddbus/common/station/capacity` — Station capacity info
- `/ddbus/common/supermap/point/station?device=web&HUID=XX&keywords=Y&lang=en` — Station keyword search

See `~/macau-bus/README.md` for more details on SuperMap endpoints.

## DSAT Fetched At

2026-04-23T09:04:51.623589+00:00

Total routes: 92
Routes with no service today: 0

## How to Regenerate

A Python script is available in this directory:
```bash
python3 regenerate_bus_reference.py --dsat-only
```

### Quick update (DSAT stop sequences only, no extra dependencies)
```bash
cd ~/macau-bus
python3 regenerate_bus_reference.py --dsat-only
```

### Full update (DSAT + motransportinfo + bridges)
```bash
cd ~/macau-bus
python3 regenerate_bus_reference.py --bridges
```

### Playwright for motransportinfo scraping
motransportinfo.com is JS-rendered — requires Playwright to scrape route data.
Install in this project's environment:
```bash
cd ~/macau-bus
pip install playwright
playwright install chromium
```

### File descriptions

**dsat_stops.json** — Authoritative per-direction stop lists from DSAT live API.
Contains platform suffixes (e.g. "M172/14"). Updated whenever route changes occur.
Fetched by querying DSAT for each route in both directions.

**routes.json / stops.json** — Service hours, frequencies, coordinates from
motransportinfo.com. These define the detailed route geometry and schedule.
Scraped via Playwright (the site is JS-rendered).

**bridges.json** — Macau-Taipa Bridge (嘉樂庇總督大橋) polyline from OpenStreetMap
via Overpass API. Used to correctly route buses across the channel.

**bridge_routes.json** — Static mapping of which route IDs cross which bridges.

## Notes

- DSAT data includes live bus positions but this export only captures the stop
  sequence (route structure), which changes infrequently.
- motransportinfo.com layout can change — if scraping breaks, inspect the
  Playwright screenshot at /tmp/mini-macau/playwright_screenshot.png.
- Bridge route assignments are hand-maintained based on actual Macau bus operations.

## Quote/0 Integration

The `quote0_send_bus.py` script sends live bus data to a Quote/0 e-ink display
(Dot. mindreset.tech). See `README.md` for full usage.

Requirements:
- `QUOTE0_DEVICE_ID` and `QUOTE0_API_KEY` in `~/.hermes/.env`
- System cron running `quote0_send_bus.py --silent` every 5 minutes

The script uses real stop coordinates from `stops.json` to calculate actual
distance (km) and ETA (minutes) from your position to each bus, not just stop counts.
