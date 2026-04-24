"""Tests for macau_bus_distance.py functions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import macau_bus_distance


class TestCalculateDistanceKm:
    """Test calculate_distance_km (the Haversine impl in macau_bus_distance.py)."""

    def test_same_point(self):
        d = macau_bus_distance.calculate_distance_km(22.19, 113.54, 22.19, 113.54)
        assert d == 0.0

    def test_known_distance(self):
        """Haikou (Hainan) to Macau ≈ 410 km."""
        hainan = (20.04, 110.35)
        macau = (22.19, 113.54)
        d = macau_bus_distance.calculate_distance_km(*hainan, *macau)
        assert 390 < d < 430

    def test_small_distance(self):
        """0.001 degrees apart ≈ 111 meters."""
        d = macau_bus_distance.calculate_distance_km(
            22.19000, 113.54000, 22.19100, 113.54000
        )
        assert 0.10 < d < 0.12

    def test_returns_float(self):
        assert isinstance(
            macau_bus_distance.calculate_distance_km(0, 0, 1, 1), float
        )

    def test_negative_input_still_positive(self):
        """Even with negative coords, result is non-negative."""
        d = macau_bus_distance.calculate_distance_km(-22.0, -113.0, 0, 0)
        assert d > 0

    def test_decimal_precision(self):
        """Result is a float with reasonable precision."""
        d = macau_bus_distance.calculate_distance_km(22.19, 113.54, 22.30, 113.60)
        assert isinstance(d, float)
        # Check it's not a weirdly precise or imprecise value
        assert d > 10  # 0.11 degrees lat + 0.06 degrees lng is well over 10 km


class TestFindRouteInDsat:
    """Test find_route_in_dsat."""

    def test_route_found(self):
        dsat_data = {
            "routes": {
                "51A": {"forward": ["M93", "T394"], "backward": ["T394", "M93"]},
            }
        }
        result = macau_bus_distance.find_route_in_dsat("51A", dsat_data)
        assert result is not None
        assert "forward" in result
        assert len(result["forward"]) == 2

    def test_route_not_found(self):
        dsat_data = {"routes": {"51A": {"forward": []}}}
        result = macau_bus_distance.find_route_in_dsat("999", dsat_data)
        assert result is None

    def test_route_not_found_uppercase(self):
        """Route lookup should be case-insensitive."""
        dsat_data = {
            "routes": {
                "51A": {"forward": ["M93"], "backward": ["M93"]},
            }
        }
        result = macau_bus_distance.find_route_in_dsat("51a", dsat_data)
        assert result is not None

    def test_empty_dsat(self):
        result = macau_bus_distance.find_route_in_dsat("51A", {})
        assert result is None


class TestFindStopInStops:
    """Test find_stop_in_stops."""

    def test_stop_found(self):
        stops_data = [
            {"id": "T394", "nameCn": "漁翁街"},
            {"id": "M93", "nameCn": "關閘"},
        ]
        result = macau_bus_distance.find_stop_in_stops("T394", stops_data)
        assert result is not None
        assert result["nameCn"] == "漁翁街"

    def test_stop_not_found(self):
        stops_data = [{"id": "T394", "nameCn": "漁翁街"}]
        result = macau_bus_distance.find_stop_in_stops("M93", stops_data)
        assert result is None

    def test_empty_stops_list(self):
        result = macau_bus_distance.find_stop_in_stops("T394", [])
        assert result is None


class TestCalculateDistanceBetweenStops:
    """Test calculate_distance_between_stops."""

    def test_valid_coordinates(self):
        c1 = (22.19, 113.54)
        c2 = (22.20, 113.55)
        d = macau_bus_distance.calculate_distance_between_stops(c1, c2)
        assert d is not None
        assert d > 0
        assert 0.01 < d < 2.0  # small Macau urban distance

    def test_same_coordinates(self):
        c = (22.19, 113.54)
        d = macau_bus_distance.calculate_distance_between_stops(c, c)
        assert d is not None
        assert d == 0.0

    def test_none_coords(self):
        d = macau_bus_distance.calculate_distance_between_stops(None, (22.0, 113.0))
        assert d is None

    def test_both_none(self):
        d = macau_bus_distance.calculate_distance_between_stops(None, None)
        assert d is None


class TestLoadLocalRouteData:
    """Test load_local_route_data — loads from data directory."""

    def test_valid_data(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        dsat = {"totalRoutes": 2, "routes": {"51A": {"forward": ["A", "B"]}}}
        (data_dir / "dsat_stops.json").write_text(json.dumps(dsat))

        stops = [
            {"id": "A", "lat": 22.19, "lng": 113.54},
            {"id": "B", "lat": 22.20, "lng": 113.55},
        ]
        (data_dir / "stops.json").write_text(json.dumps(stops))

        dsat_data, coords, stops_data = macau_bus_distance.load_local_route_data(data_dir)

        assert dsat_data["totalRoutes"] == 2
        assert "A" in coords
        assert coords["A"] == (22.19, 113.54)
        assert "B" in coords
        assert len(stops_data) == 2

    def test_missing_files(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        dsat_data, coords, stops_data = macau_bus_distance.load_local_route_data(data_dir)

        assert dsat_data == {}
        assert coords == {}
        assert stops_data == []

    def test_stops_without_coords_filtered(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        dsat = {"totalRoutes": 1, "routes": {}}
        (data_dir / "dsat_stops.json").write_text(json.dumps(dsat))

        stops = [
            {"id": "A", "lat": 22.19, "lng": 113.54},
            {"id": "B"},  # no lat/lng
        ]
        (data_dir / "stops.json").write_text(json.dumps(stops))

        _, coords, _ = macau_bus_distance.load_local_route_data(data_dir)

        assert "A" in coords
        assert "B" not in coords

    def test_invalid_json(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "dsat_stops.json").write_text("not json")
        (data_dir / "stops.json").write_text("also not json")

        dsat_data, coords, stops_data = macau_bus_distance.load_local_route_data(data_dir)

        assert dsat_data == {}
        assert coords == {}
        assert stops_data == []
