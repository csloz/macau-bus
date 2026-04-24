"""Tests for data loading functions in macau_bus_arrivals.py"""
import sys
from pathlib import Path

# Add macau-bus to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import macau_bus_arrivals


class TestDataLoading:
    """Test load_stops, load_routes, load_dsat_stops."""

    def test_load_stops(self, tmp_path):
        """load_stops returns dict keyed by stop id."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        stops_data = [
            {"id": "T394", "nameCn": "漁翁街巴士站", "lat": 22.19, "lng": 113.54, "route_ids": ["51A", "102"]},
            {"id": "M93", "nameCn": "關閘", "lat": 22.20, "lng": 113.55, "route_ids": ["51A"]},
        ]
        (data_dir / "stops.json").write_text(json.dumps(stops_data))
        stops = macau_bus_arrivals.load_stops(data_dir)
        assert isinstance(stops, dict)
        assert "T394" in stops
        assert "M93" in stops
        assert stops["T394"]["nameCn"] == "漁翁街巴士站"
        assert stops["T394"]["route_ids"] == ["51A", "102"]

    def test_load_stops_missing_file(self, tmp_path):
        """Missing stops.json returns empty dict."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        stops = macau_bus_arrivals.load_stops(data_dir)
        assert stops == {}

    def test_load_routes(self, tmp_path):
        """load_routes returns dict keyed by route id."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        routes_data = [
            {"id": "51A", "avg_freq": 8, "service_start": 6, "service_end": 23},
            {"id": "102", "avg_freq": 12, "service_start": 6, "service_end": 22},
        ]
        (data_dir / "routes.json").write_text(json.dumps(routes_data))
        routes = macau_bus_arrivals.load_routes(data_dir)
        assert isinstance(routes, dict)
        assert "51A" in routes
        assert "102" in routes
        assert routes["51A"]["avg_freq"] == 8

    def test_load_dsat_stops(self, tmp_path):
        """load_dsat_stops returns the raw dict structure."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        dsat_data = {
            "totalRoutes": 3,
            "emptyRoutes": [],
            "routes": {"51A": {"forward": ["M93", "T394", "C690"]}}
        }
        (data_dir / "dsat_stops.json").write_text(json.dumps(dsat_data))
        dsat = macau_bus_arrivals.load_dsat_stops(data_dir)
        assert isinstance(dsat, dict)
        assert dsat["totalRoutes"] == 3
        assert "51A" in dsat["routes"]

    def test_load_corrupted_json(self, tmp_path):
        """Corrupted JSON files return empty dict, not crash."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        corrupted = data_dir / "stops.json"
        corrupted.write_text("{ not valid json }")
        stops = macau_bus_arrivals.load_stops(data_dir)
        assert stops == {}

    def test_load_stops_with_invalid_entries(self, tmp_path):
        """Stops without 'id' field are skipped."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        stops_data = [
            {"id": "T394", "nameCn": "test"},
            {"nameCn": "no id"},  # missing id
            {"id": None, "nameCn": "none id"},  # None id
        ]
        (data_dir / "stops.json").write_text(json.dumps(stops_data))
        stops = macau_bus_arrivals.load_stops(data_dir)
        assert len(stops) == 1
        assert "T394" in stops
        assert "nameCn" in stops["T394"]

    def test_load_routes_missing_file(self, tmp_path):
        """Missing routes.json returns empty dict."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        routes = macau_bus_arrivals.load_routes(data_dir)
        assert routes == {}

    def test_load_dsat_stops_missing_file(self, tmp_path):
        """Missing dsat_stops.json returns empty dict."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        dsat = macau_bus_arrivals.load_dsat_stops(data_dir)
        assert dsat == {}
