"""Shared test fixtures for macau-bus tests."""
import pytest
import json
from pathlib import Path


@pytest.fixture
def test_data_dir(tmp_path):
    """Create a temporary data directory with realistic test data."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create stops.json with realistic Macau bus data
    stops_data = [
        {"id": "T394", "nameCn": "漁翁街／巴士站", "namePt": "Parada de / bonibus",
         "lat": 22.1917, "lng": 113.5435, "route_ids": ["51A", "102", "5"]},
        {"id": "M93", "nameCn": "關閘", "namePt": "Quعلام",
         "lat": 22.2030, "lng": 113.5410, "route_ids": ["51A", "10"]},
        {"id": "C690", "nameCn": "媽閣", "namePt": "Cenedo",
         "lat": 22.1880, "lng": 113.5370, "route_ids": ["51A", "3"]},
        {"id": "T395", "nameCn": "漁翁街／第二場所", "namePt": "Segunda Paragem de / bonibus",
         "lat": 22.1920, "lng": 113.5440, "route_ids": ["51A", "102"]},
        {"id": "M1", "nameCn": "青洲", "namePt": "Quensau",
         "lat": 22.2050, "lng": 113.5400, "route_ids": ["10"]},
    ]
    (data_dir / "stops.json").write_text(json.dumps(stops_data))

    # Create routes.json
    routes_data = [
        {"id": "51A", "avg_freq": 8, "headway": 8, "service_start": 6, "service_start_m": 0,
         "service_end": 23, "service_end_m": 30},
        {"id": "102", "avg_freq": 12, "headway": 12, "service_start": 6, "service_start_m": 0,
         "service_end": 22, "service_end_m": 0},
        {"id": "3", "avg_freq": 10, "headway": 10, "service_start": 6, "service_start_m": 0,
         "service_end": 23, "service_end_m": 30},
        {"id": "5", "avg_freq": 15, "headway": 15, "service_start": 6, "service_start_m": 0,
         "service_end": 22, "service_end_m": 30},
        {"id": "10", "avg_freq": 10, "headway": 10, "service_start": 6, "service_start_m": 0,
         "service_end": 23, "service_end_m": 0},
    ]
    (data_dir / "routes.json").write_text(json.dumps(routes_data))

    # Create dsat_stops.json
    dsat_data = {
        "totalRoutes": 5,
        "emptyRoutes": [],
        "routes": {
            "51A": {
                "forward": ["M93", "M1", "T395", "T394", "C690"],
                "backward": ["C690", "T394", "T395", "M1", "M93"]
            },
            "102": {
                "forward": ["T395", "T394", "M93"],
                "backward": ["M93", "T394", "T395"]
            },
            "3": {"forward": ["C690", "M1"], "backward": ["M1", "C690"]},
            "5": {"forward": ["T394", "T395"], "backward": ["T395", "T394"]},
            "10": {"forward": ["M93", "M1", "T394"], "backward": ["T394", "M1", "M93"]},
        }
    }
    (data_dir / "dsat_stops.json").write_text(json.dumps(dsat_data))

    return data_dir


@pytest.fixture
def stopped_at_bus():
    """A bus sitting at a station — one bus at T394."""
    return [
        {"staCode": "M93", "busInfo": []},
        {"staCode": "T395", "busInfo": []},
        {"staCode": "T394", "busInfo": [{"busPlate": "MA-1234", "speed": 0}]},
        {"staCode": "C690", "busInfo": []},
    ]


@pytest.fixture
def approaching_bus():
    """A bus approaching T394 from T395 — 1 stop away."""
    return [
        {"staCode": "M93", "busInfo": []},
        {"staCode": "T395", "busInfo": [{"busPlate": "MA-5678", "speed": 45}]},
        {"staCode": "T394", "busInfo": []},
        {"staCode": "C690", "busInfo": []},
    ]


@pytest.fixture
def behind_bus():
    """A bus that already passed T394 — should be ignored."""
    return [
        {"staCode": "M93", "busInfo": []},
        {"staCode": "T395", "busInfo": []},
        {"staCode": "T394", "busInfo": []},
        {"staCode": "C690", "busInfo": [{"busPlate": "MA-9999", "speed": 40}]},
    ]


@pytest.fixture
def multi_bus_scenario():
    """Multiple buses on same route — one close, one far."""
    return [
        {"staCode": "M93", "busInfo": [{"busPlate": "MA-1001", "speed": 50}]},
        {"staCode": "T395", "busInfo": []},
        {"staCode": "T394", "busInfo": []},
        {"staCode": "C690", "busInfo": [{"busPlate": "MA-1002", "speed": 35}]},
    ]
