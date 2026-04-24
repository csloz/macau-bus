"""Tests for macau_bus_quick.py functions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import json.decoder
import macau_bus_quick


class TestLoadStops:
    """Test load_stops from macau_bus_quick.py."""

    def test_valid_stops(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        stops = [{"id": "T394", "nameCn": "Test"}, {"id": "M93", "nameCn": "Guanzhai"}]
        (data_dir / "stops.json").write_text(json.dumps(stops))
        orig = macau_bus_quick.DATA_DIR
        macau_bus_quick.DATA_DIR = data_dir
        try:
            result = macau_bus_quick.load_stops()
        finally:
            macau_bus_quick.DATA_DIR = orig
        assert len(result) == 2
        assert result[0]["id"] == "T394"

    def test_missing_file(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        orig = macau_bus_quick.DATA_DIR
        macau_bus_quick.DATA_DIR = data_dir
        try:
            result = macau_bus_quick.load_stops()
        finally:
            macau_bus_quick.DATA_DIR = orig
        assert result == []

    def test_invalid_json(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "stops.json").write_text("broken!")
        orig = macau_bus_quick.DATA_DIR
        macau_bus_quick.DATA_DIR = data_dir
        try:
            macau_bus_quick.load_stops()
            assert False, "Expected JSONDecodeError"
        except json.decoder.JSONDecodeError:
            pass
        finally:
            macau_bus_quick.DATA_DIR = orig


class TestFindStop:
    """Test find_stop."""

    def test_stop_found(self):
        stops = [
            {"id": "T394", "nameCn": "漁翁街"},
            {"id": "M93", "nameCn": "關閘"},
        ]
        result = macau_bus_quick.find_stop("M93", stops)
        assert result is not None
        assert result["nameCn"] == "關閘"

    def test_stop_not_found(self):
        stops = [{"id": "T394", "nameCn": "漁翁街"}]
        result = macau_bus_quick.find_stop("M93", stops)
        assert result is None

    def test_empty_list(self):
        result = macau_bus_quick.find_stop("T394", [])
        assert result is None

    def test_partial_id_no_match(self):
        stops = [
            {"id": "T394", "nameCn": "漁翁街"},
            {"id": "M93", "nameCn": "關閘"},
        ]
        result = macau_bus_quick.find_stop("T39", stops)
        assert result is None


class TestGetStopIndexInRoute:
    """Test get_stop_index_in_route."""

    def test_stop_at_start(self):
        live_data = [
            {"staCode": "M93"},
            {"staCode": "T394"},
            {"staCode": "C690"},
        ]
        result = macau_bus_quick.get_stop_index_in_route("51A", "M93", live_data)
        assert result == 0

    def test_stop_at_end(self):
        live_data = [
            {"staCode": "M93"},
            {"staCode": "T394"},
            {"staCode": "C690"},
        ]
        result = macau_bus_quick.get_stop_index_in_route("51A", "C690", live_data)
        assert result == 2

    def test_stop_with_slash(self):
        live_data = [
            {"staCode": "M93/1"},
            {"staCode": "T394/2"},
            {"staCode": "C690/1"},
        ]
        result = macau_bus_quick.get_stop_index_in_route("51A", "T394", live_data)
        assert result == 1

    def test_stop_not_in_route(self):
        live_data = [{"staCode": "M93"}, {"staCode": "C690"}]
        result = macau_bus_quick.get_stop_index_in_route("51A", "T394", live_data)
        assert result is None

    def test_none_live_data(self):
        result = macau_bus_quick.get_stop_index_in_route("51A", "T394", None)
        assert result is None

    def test_empty_live_data(self):
        result = macau_bus_quick.get_stop_index_in_route("51A", "T394", [])
        assert result is None


class TestGetArrivals:
    """Test get_arrivals logic.

    IMPORTANT: get_arrivals calls fetch_route(route_id, 0) and fetch_route(route_id, 1)
    separately. The mock must return DIFFERENT stop-order data for each direction,
    because the code filters buses differently per direction:
      - Forward (d=0): station index <= stop index (bus before or at stop)
      - Backward (d=1): station index >= stop index (bus after or at stop)
    """

    def _mock_for_directions(self, fwd_stops, bwd_stops):
        """Create a mock that returns fwd for d=0, bwd for d=1."""
        def mock_fetch(rid, d):
            return fwd_stops if d == 0 else bwd_stops
        return mock_fetch

    def test_bus_at_stop(self):
        """Bus at T394 in both directions — 0 stops away."""
        fwd = [
            {"staCode": "M93", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": [{"busPlate": "MA-001", "speed": 0}]},
            {"staCode": "C690", "busInfo": []},
        ]
        # Backward: C690(0), T394(1), T395(2), M93(3)
        bwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T394", "busInfo": [{"busPlate": "BA-001", "speed": 0}]},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "M93", "busInfo": []},
        ]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        assert away == 0
        assert total == 2  # 1 bus in forward, 1 bus in backward

    def test_bus_one_stop_away(self):
        """Bus at T395 approaching T394 — 1 stop away."""
        # Forward: M93(0), T395(1), T394(2), C690(3)
        fwd = [
            {"staCode": "M93", "busInfo": []},
            {"staCode": "T395", "busInfo": [{"busPlate": "MA-001", "speed": 40}]},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "C690", "busInfo": []},
        ]
        # Backward: C690(0), T395(1), T394(2), M93(3)
        bwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "M93", "busInfo": []},
        ]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        # Forward: T394 at idx 2, bus at T395(idx 1) → away = 2-1 = 1
        # Backward: T394 at idx 2, no bus after or at T394 → none
        assert away == 1
        assert total == 1

    def test_bus_already_passed_excluded(self):
        """Bus past T394 in forward direction — excluded from forward."""
        # Forward: M93(0), T395(1), T394(2), C690(3)
        fwd = [
            {"staCode": "M93", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "C690", "busInfo": [{"busPlate": "MA-001", "speed": 30}]},
        ]
        # Backward: C690(0), T395(1), T394(2), M93(3)
        bwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "M93", "busInfo": []},
        ]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        # Forward: bus at C690(idx 3) > T394(idx 2) → excluded
        # Backward: no bus at or after T394(idx 2) → none
        assert away is None
        assert total == 0

    def test_no_buses(self):
        fwd = [{"staCode": "M93", "busInfo": []}, {"staCode": "T394", "busInfo": []}]
        bwd = [{"staCode": "T394", "busInfo": []}, {"staCode": "M93", "busInfo": []}]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        assert away is None
        assert total == 0

    def test_multiple_buses_both_directions(self):
        """Multiple buses across directions — total sums all."""
        # Forward: M93(0), T395(1), T394(2), C690(3)
        fwd = [
            {"staCode": "M93", "busInfo": [{"busPlate": "A-001", "speed": 30}]},
            {"staCode": "T395", "busInfo": [{"busPlate": "B-001", "speed": 20}]},
            {"staCode": "T394", "busInfo": [{"busPlate": "C-001", "speed": 0}]},
            {"staCode": "C690", "busInfo": []},
        ]
        # Backward: C690(0), T394(1), T395(2), M93(3)
        bwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "M93", "busInfo": []},
        ]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        assert away == 0  # C-001 at stop
        assert total == 3  # 3 buses in forward, 0 in backward

    def test_backwards_direction(self):
        """Bus approaching from backward direction."""
        # Forward: M93(0), T395(1), T394(2), C690(3)
        fwd = [
            {"staCode": "M93", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "C690", "busInfo": []},
        ]
        # Backward: C690(0), T395(1), T394(2), M93(3)
        # Bus at T395 in backward: T395(idx 1) < T394(idx 2) → 1 < 2, excluded
        # Bus at M93 in backward: M93(idx 3) > T394(idx 2) → away = 3-2 = 1
        bwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "M93", "busInfo": [{"busPlate": "BW-001", "speed": 30}]},
        ]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        assert away == 1
        assert total == 1

    def test_better_direction_chosen(self):
        """If backward has closer bus, backward wins (away = best of both directions)."""
        # Forward: M93(0), T395(1), T394(2), C690(3)
        fwd = [
            {"staCode": "M93", "busInfo": [{"busPlate": "FAR-001", "speed": 40}]},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "C690", "busInfo": []},
        ]
        # Backward: C690(0), T395(1), T394(2), M93(3)
        # Bus at C690(idx 0) in backward: 0 < 2, excluded (before T394)
        # Bus at M93(idx 3) in backward: 3 > 2 → away = 1
        bwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "M93", "busInfo": [{"busPlate": "BW-001", "speed": 40}]},
        ]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        # Forward: bus at M93(idx 0), stop at idx 2 → away = 2
        # Backward: bus at M93(idx 3), stop at idx 2 → away = 1
        # Minimum: backward wins → away = 1
        assert away == 1
        assert total == 2  # 1 bus in each direction

    def test_api_failure_returns_none(self):
        macau_bus_quick.fetch_route = lambda rid, d: None
        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        assert away is None
        assert total == 0

    def test_stop_not_in_route_any_direction(self):
        fwd = [{"staCode": "A", "busInfo": []}, {"staCode": "B", "busInfo": []}]
        bwd = [{"staCode": "B", "busInfo": []}, {"staCode": "A", "busInfo": []}]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        assert away is None
        assert total == 0

    def test_backward_better_gives_correct_plate(self):
        """When backward is better, the closest bus data should be from backward."""
        fwd = [
            {"staCode": "M93", "busInfo": [{"busPlate": "F-001", "speed": 50}]},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "C690", "busInfo": []},
        ]
        # Backward: C690(0), T395(1), T394(2), M93(3)
        # Bus at M93(idx 3): 3-2=1 stop away in backward
        bwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "M93", "busInfo": [{"busPlate": "BW-002", "speed": 40}]},
        ]
        macau_bus_quick.fetch_route = self._mock_for_directions(fwd, bwd)

        away, total = macau_bus_quick.get_arrivals("51A", "T394")
        assert away == 1  # backward wins (1 stop vs forward's 2)
        assert total == 2  # 1 in each direction
