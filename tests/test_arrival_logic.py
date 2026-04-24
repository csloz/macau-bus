"""Tests for live arrival logic in macau_bus_arrivals.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import macau_bus_arrivals


class TestFindRouteDirection:
    """Test find_route_direction — finds stop index in live route data."""

    def test_stop_found_at_start(self):
        live_data = [
            {"staCode": "M93"},
            {"staCode": "T395"},
            {"staCode": "T394"},
        ]
        targets, idx = macau_bus_arrivals.find_route_direction("51A", "M93", live_data)
        assert targets == ["M93", "T395", "T394"]
        assert idx == 0

    def test_stop_found_in_middle(self):
        live_data = [
            {"staCode": "M93"},
            {"staCode": "T395"},
            {"staCode": "T394"},
        ]
        targets, idx = macau_bus_arrivals.find_route_direction("51A", "T395", live_data)
        assert targets == ["M93", "T395", "T394"]
        assert idx == 1

    def test_stop_found_at_end(self):
        live_data = [
            {"staCode": "M93"},
            {"staCode": "T395"},
            {"staCode": "T394"},
        ]
        targets, idx = macau_bus_arrivals.find_route_direction("51A", "T394", live_data)
        assert idx == 2

    def test_stop_with_slash_code(self):
        live_data = [
            {"staCode": "M93/1"},
            {"staCode": "T395/2"},
            {"staCode": "T394/1"},
        ]
        targets, idx = macau_bus_arrivals.find_route_direction("51A", "T395", live_data)
        assert targets == ["M93", "T395", "T394"]
        assert idx == 1

    def test_stop_not_found(self):
        live_data = [{"staCode": "M93"}, {"staCode": "T394"}]
        targets, idx = macau_bus_arrivals.find_route_direction("51A", "M1", live_data)
        assert targets is None
        assert idx is None


class TestCalcDistance:
    """Test calc_distance — calculates distance between two stops."""

    def test_valid_distance(self, test_data_dir):
        stops = macau_bus_arrivals.load_stops(test_data_dir)
        result = macau_bus_arrivals.calc_distance("M93", "C690", stops)
        assert "error" not in result
        assert "distance_km" in result
        assert "distance_m" in result
        assert result["from_stop"] == "M93"
        assert result["to_stop"] == "C690"
        assert result["distance_km"] > 0
        assert result["distance_m"] > 0

    def test_stop_not_found(self, test_data_dir):
        stops = macau_bus_arrivals.load_stops(test_data_dir)
        result = macau_bus_arrivals.calc_distance("M93", "ZZZZ", stops)
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_no_coordinates(self, test_data_dir):
        stops = macau_bus_arrivals.load_stops(test_data_dir)
        stops["NOCOORD"] = {"id": "NOCOORD", "nameCn": "No Coords"}
        result = macau_bus_arrivals.calc_distance("M93", "NOCOORD", stops)
        assert "error" in result
        assert "coordinate" in result["error"].lower()

    def test_same_stop(self, test_data_dir):
        stops = macau_bus_arrivals.load_stops(test_data_dir)
        result = macau_bus_arrivals.calc_distance("T394", "T394", stops)
        assert result["distance_km"] == 0.0
        assert result["distance_m"] == 0

    def test_distance_name_fields(self, test_data_dir):
        stops = macau_bus_arrivals.load_stops(test_data_dir)
        result = macau_bus_arrivals.calc_distance("M93", "C690", stops)
        assert result["from_name"] == "關閘"
        assert result["to_name"] == "媽閣"

    def test_distance_precision(self, test_data_dir):
        stops = macau_bus_arrivals.load_stops(test_data_dir)
        result = macau_bus_arrivals.calc_distance("M93", "C690", stops)
        # distance_km should be rounded to 2 decimal places
        assert result["distance_km"] == round(result["distance_km"], 2)


class TestEstimateArrivals:
    """Test estimate_arrivals_live — calculates live bus arrivals."""

    def _make_stops_data(self):
        return {
            "T394": ["51A", "102", "5"],
            "M93": ["51A", "10"],
            "C690": ["51A", "3"],
        }

    def _make_routes_data(self):
        return {
            "51A": {"avg_freq": 8, "headway": 8},
            "102": {"avg_freq": 12},
            "5": {"avg_freq": 15},
            "10": {"avg_freq": 10},
            "3": {"avg_freq": 10},
        }

    def test_bus_at_stop(self, stopped_at_bus):
        """Bus sitting at T394 — should show 0 stops away."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return stopped_at_bus
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )

        assert "51A" in arrivals
        assert arrivals["51A"]["stops"] == 0
        assert arrivals["51A"]["status"] == "● AT STOP"
        assert arrivals["51A"]["nearestPlate"] == "MA-1234"
        assert arrivals["51A"]["nearestSpeed"] == 0
        assert arrivals["51A"]["totalBuses"] == 1

    def test_bus_approaching(self, approaching_bus):
        """Bus approaching T394 from T395 — 1 stop away."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return approaching_bus
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )

        assert "51A" in arrivals
        assert arrivals["51A"]["stops"] == 1
        assert arrivals["51A"]["nearestPlate"] == "MA-5678"
        assert arrivals["51A"]["nearestSpeed"] == 45

    def test_bus_already_passed(self, behind_bus):
        """Bus past T394 — should be excluded from arrivals."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return behind_bus
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert "51A" not in arrivals

    def test_closing_bus_excluded_from_forward(self):
        """In forward direction, a bus AFTER the stop is excluded."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()
        # Forward order: M93(0), T395(1), T394(2), C690(3)
        # Bus at C690 is at idx 3, stop is at idx 2, 3-2=1 > 0 → excluded
        fwd = [
            {"staCode": "M93", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "C690", "busInfo": [{"busPlate": "LA-001", "speed": 40}]},
        ]

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return fwd
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert "51A" not in arrivals

    def test_multiple_buses_one_route(self):
        """Multiple buses on same route — finds the nearest."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()
        # M93(idx 0), T395(idx 1), T394(idx 2)
        # Bus at M93: 2 stops away
        # Bus at T395: 1 stop away (nearest)
        data = [
            {"staCode": "M93", "busInfo": [{"busPlate": "MA-1001", "speed": 50}]},
            {"staCode": "T395", "busInfo": [{"busPlate": "MA-1002", "speed": 40}]},
            {"staCode": "T394", "busInfo": []},
        ]

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return data
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )

        assert "51A" in arrivals
        assert arrivals["51A"]["totalBuses"] == 2  # both buses counted
        assert arrivals["51A"]["nearestPlate"] == "MA-1002"  # closest
        assert arrivals["51A"]["stops"] == 1

    def test_no_live_data(self):
        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", self._make_stops_data(), self._make_routes_data(),
            lambda route_id, direction: None
        )
        assert arrivals == {}

    def test_direction_returns_arrow(self):
        """Direction 0 →, direction 1 ←."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()
        fwd = [
            {"staCode": "C690", "busInfo": []},
            {"staCode": "T394", "busInfo": [{"busPlate": "FA-001", "speed": 0}]},
            {"staCode": "T395", "busInfo": []},
        ]

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return fwd
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert "51A" in arrivals
        assert arrivals["51A"]["direction"] == "→"

    def test_stops_field_is_int(self):
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return [
                    {"staCode": "M93", "busInfo": [{"busPlate": "T-001", "speed": 30}]},
                    {"staCode": "T394", "busInfo": []},
                ]
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert isinstance(arrivals["51A"]["stops"], int)
        assert arrivals["51A"]["stops"] == 1

    def test_frequency_from_avg_freq(self):
        stops_data = self._make_stops_data()
        routes_data = {"51A": {"avg_freq": 7, "headway": 9}}

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return [
                    {"staCode": "M93", "busInfo": [{"busPlate": "F-001", "speed": 0}]},
                    {"staCode": "T394", "busInfo": []},
                ]
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert arrivals["51A"]["frequency"] == 7

    def test_frequency_falls_back_to_headway(self):
        stops_data = self._make_stops_data()
        routes_data = {"51A": {"headway": 11}}

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return [
                    {"staCode": "M93", "busInfo": [{"busPlate": "H-001", "speed": 0}]},
                    {"staCode": "T394", "busInfo": []},
                ]
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert arrivals["51A"]["frequency"] == 11

    def test_frequency_default_10(self):
        stops_data = self._make_stops_data()
        routes_data = {"51A": {}}

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return [
                    {"staCode": "M93", "busInfo": [{"busPlate": "D-001", "speed": 0}]},
                    {"staCode": "T394", "busInfo": []},
                ]
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert arrivals["51A"]["frequency"] == 10

    def test_direction_prefers_closer_stop(self):
        """Backward: T394 at index 1 (closer). Bus at C690(idx 0) approaches T394."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        fwd = [
            {"staCode": "M93", "busInfo": [{"busPlate": "FAR-001", "speed": 40}]},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "C690", "busInfo": []},
        ]
        bwd = [
            {"staCode": "C690", "busInfo": [{"busPlate": "CLOSE-001", "speed": 40}]},
            {"staCode": "T394", "busInfo": []},
            {"staCode": "T395", "busInfo": []},
            {"staCode": "M93", "busInfo": []},
        ]

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return fwd if direction == 0 else bwd
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )

        # Backward wins: T394 at index 1 vs forward index 2
        # Bus at C690(idx 0) in backward: 1-0=1 stop away
        # Bus at M93(idx 0) in forward: 2-0=2 stops away
        # Backward preferred (closer stop index), 1 stop away
        assert "51A" in arrivals
        assert arrivals["51A"]["nearestPlate"] == "CLOSE-001"
        assert arrivals["51A"]["stops"] == 1

    def test_arrival_has_all_required_fields(self):
        """Each arrival dict has all expected fields."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return [
                    {"staCode": "M93", "busInfo": [{"busPlate": "X-001", "speed": 0}]},
                    {"staCode": "T394", "busInfo": []},
                ]
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        info = arrivals["51A"]
        required = {
            "stops", "status", "direction", "frequency",
            "totalBuses", "nearestPlate", "nearestSpeed",
            "secondNearestStops", "secondNearestPlate", "secondNearestSpeed",
            "lastUpdate",
        }
        assert required.issubset(set(info.keys()))

    def test_zero_speed_at_stop(self):
        """Bus at stop shows speed=0."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return [
                    {"staCode": "T394", "busInfo": [{"busPlate": "Z-001", "speed": 0}]},
                    {"staCode": "C690", "busInfo": []},
                ]
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert arrivals["51A"]["nearestSpeed"] == 0

    def test_status_at_stop_unicode(self):
        """AT STOP status uses Unicode bullet."""
        stops_data = self._make_stops_data()
        routes_data = self._make_routes_data()

        def mock_fetch(route_id, direction):
            if route_id == "51A":
                return [
                    {"staCode": "T394", "busInfo": [{"busPlate": "S-001", "speed": 0}]},
                    {"staCode": "C690", "busInfo": []},
                ]
            return None

        arrivals = macau_bus_arrivals.estimate_arrivals_live(
            "T394", stops_data, routes_data, mock_fetch
        )
        assert arrivals["51A"]["status"] == "● AT STOP"
