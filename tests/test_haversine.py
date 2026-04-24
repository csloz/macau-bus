"""Tests for haversine_distance_km from macau_bus_arrivals.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import macau_bus_arrivals


class TestHaversineDistance:
    """Test the haversine great-circle distance calculation."""

    def test_same_point(self):
        d = macau_bus_arrivals.haversine_distance_km(22.19, 113.54, 22.19, 113.54)
        assert d == 0.0

    def test_hainan_macau_distance(self):
        """Hainan to Macau is approximately 570 km."""
        hainan = (18.75, 109.50)
        macau = (22.19, 113.54)
        d = macau_bus_arrivals.haversine_distance_km(*hainan, *macau)
        assert 550 < d < 600

    def test_small_distance(self):
        """0.001 degrees apart ≈ 111 meters."""
        d = macau_bus_arrivals.haversine_distance_km(
            22.19000, 113.54000, 22.19100, 113.54000
        )
        assert 0.10 < d < 0.12

    def test_antipodal(self):
        """Opposite sides of the Earth ≈ half circumference."""
        macau = (22.19, 113.54)
        antipode = (-22.19, -66.46)
        d = macau_bus_arrivals.haversine_distance_km(*macau, *antipode)
        assert 19500 < d < 20500

    def test_results_are_positive(self):
        assert macau_bus_arrivals.haversine_distance_km(0, 0, 1, 1) > 0

    def test_reversed_arguments_same_distance(self):
        d1 = macau_bus_arrivals.haversine_distance_km(22.19, 113.54, 22.20, 113.55)
        d2 = macau_bus_arrivals.haversine_distance_km(22.20, 113.55, 22.19, 113.54)
        assert d1 == d2

    def test_returns_float(self):
        assert isinstance(
            macau_bus_arrivals.haversine_distance_km(22.0, 113.0, 23.0, 114.0),
            float
        )
