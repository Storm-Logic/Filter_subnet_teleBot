import unittest

from filter_subnets import (
    calculate_miner_tao_per_day,
    calculate_owner_incentive_percent,
    count_recent_registrations,
    format_duration,
)


class CalculateOwnerIncentivePercentTests(unittest.TestCase):
    def test_calculates_owner_share(self):
        percent, uids = calculate_owner_incentive_percent(
            ["miner", "owner", "other"],
            [0.25, 0.5, 0.25],
            "owner",
        )
        self.assertAlmostEqual(percent, 50.0)
        self.assertEqual(uids, [1])

    def test_sums_duplicate_owner_hotkeys(self):
        percent, uids = calculate_owner_incentive_percent(
            ["owner", "miner", "owner"],
            [1, 2, 1],
            "owner",
        )
        self.assertAlmostEqual(percent, 50.0)
        self.assertEqual(uids, [0, 2])

    def test_zero_total_is_zero_percent(self):
        percent, uids = calculate_owner_incentive_percent(
            ["owner", "miner"],
            [0, 0],
            "owner",
        )
        self.assertEqual(percent, 0.0)
        self.assertEqual(uids, [0])

    def test_rejects_mismatched_data(self):
        with self.assertRaises(ValueError):
            calculate_owner_incentive_percent(
                ["owner"],
                [0.5, 0.5],
                "owner",
            )


class FormatDurationTests(unittest.TestCase):
    def test_formats_seconds_minutes_and_hours(self):
        self.assertEqual(format_duration(9), "9s")
        self.assertEqual(format_duration(65), "1m 05s")
        self.assertEqual(format_duration(3661), "1h 01m 01s")


class CalculateMinerTaoPerDayTests(unittest.TestCase):
    def test_uses_requested_reward_formula(self):
        reward = calculate_miner_tao_per_day(
            burn_percent=25.0,
            alpha_price_tao=0.5,
        )
        self.assertAlmostEqual(reward, 7200 * 0.41 * 0.75 * 0.5)

    def test_full_burn_has_no_miner_reward(self):
        self.assertEqual(calculate_miner_tao_per_day(100.0, 2.0), 0.0)


class CountRecentRegistrationsTests(unittest.TestCase):
    def test_counts_registration_blocks_in_last_day(self):
        self.assertEqual(
            count_recent_registrations(
                [100, 2800, 2801, 9999, 10000],
                current_block=10000,
                blocks_per_day=7200,
            ),
            4,
        )


if __name__ == "__main__":
    unittest.main()
