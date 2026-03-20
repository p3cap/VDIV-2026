import sys
import unittest
from pathlib import Path

MARS_ROVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(MARS_ROVER_ROOT))

from MapClass import Map
from Simulation import Simulation


class SimulationDaytimeTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(Map([["S"]]), run_hrs=24.0, day_hrs=16.0, night_hrs=8.0)

    def assertDaytime(self, start_hrs: float, end_hrs: float, expected: float):
        actual = self.sim.get_daytime_in_interval(start_hrs, end_hrs)
        self.assertAlmostEqual(actual, expected, places=7)

    def test_same_day_window(self):
        self.assertDaytime(0.0, 0.5, 0.5)

    def test_day_to_night_boundary(self):
        self.assertDaytime(15.5, 16.0, 0.5)
        self.assertDaytime(15.5, 16.5, 0.5)

    def test_night_window_has_no_daylight(self):
        self.assertDaytime(16.0, 16.5, 0.0)
        self.assertDaytime(23.5, 24.0, 0.0)

    def test_wraparound_into_next_day(self):
        self.assertDaytime(23.5, 24.5, 0.5)

    def test_full_cycle_contains_exact_day_length(self):
        self.assertDaytime(0.0, 24.0, 16.0)
        self.assertDaytime(24.0, 48.0, 16.0)

    def test_multi_cycle_span(self):
        self.assertDaytime(10.0, 40.0, 22.0)


if __name__ == "__main__":
    unittest.main()
