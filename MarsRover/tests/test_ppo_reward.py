import sys
import unittest
from pathlib import Path

MARS_ROVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(MARS_ROVER_ROOT))

from MachineLearning.ppo_shared import compute_reward


class PPORewardTests(unittest.TestCase):
    def test_return_focus_waiting_at_home_is_not_positive(self):
        reward, *_ = compute_reward(
            mined_now=0,
            dist_gain=0.0,
            battery_cost=0.0,
            minerals_left=3,
            return_focus_active=True,
            home_dist_before=0.0,
            home_dist_after=0.0,
            time_left_hrs=1.0,
            return_window_hrs_value=5.0,
            max_home_dist=20.0,
        )
        self.assertLessEqual(reward, 0.0)

    def test_return_focus_arrival_beats_camping(self):
        arrive_reward, *_ = compute_reward(
            mined_now=0,
            dist_gain=1.0,
            battery_cost=0.0,
            minerals_left=3,
            return_focus_active=True,
            home_dist_before=1.0,
            home_dist_after=0.0,
            time_left_hrs=1.0,
            return_window_hrs_value=5.0,
            max_home_dist=20.0,
        )
        camp_reward, *_ = compute_reward(
            mined_now=0,
            dist_gain=0.0,
            battery_cost=0.0,
            minerals_left=3,
            return_focus_active=True,
            home_dist_before=0.0,
            home_dist_after=0.0,
            time_left_hrs=1.0,
            return_window_hrs_value=5.0,
            max_home_dist=20.0,
        )
        self.assertGreater(arrive_reward, camp_reward)

    def test_return_focus_progress_beats_waiting_near_home(self):
        progress_reward, *_ = compute_reward(
            mined_now=0,
            dist_gain=1.0,
            battery_cost=0.0,
            minerals_left=3,
            return_focus_active=True,
            home_dist_before=4.0,
            home_dist_after=3.0,
            time_left_hrs=2.0,
            return_window_hrs_value=5.0,
            max_home_dist=20.0,
        )
        wait_reward, *_ = compute_reward(
            mined_now=0,
            dist_gain=0.0,
            battery_cost=0.0,
            minerals_left=3,
            return_focus_active=True,
            home_dist_before=3.0,
            home_dist_after=3.0,
            time_left_hrs=2.0,
            return_window_hrs_value=5.0,
            max_home_dist=20.0,
        )
        self.assertGreater(progress_reward, wait_reward)


if __name__ == "__main__":
    unittest.main()
