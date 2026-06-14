"""
Quick self-tests. They use offline demo data, so they run anywhere with no
internet and no real money. Run them with:

    python3 -m unittest discover -s tests

If these pass, the core logic works end to end.
"""

import os
import sys
import unittest

# Make the project modules importable when run from the tests/ folder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config       # noqa: E402
import data         # noqa: E402
import strategy     # noqa: E402
import backtest     # noqa: E402
import portfolio    # noqa: E402


class TestData(unittest.TestCase):
    def test_demo_prices_are_positive(self):
        prices = data.demo_closes(config.HISTORY_DAYS, seed=1)
        self.assertEqual(len(prices), config.HISTORY_DAYS)
        self.assertTrue(all(p > 0 for p in prices))


class TestStrategy(unittest.TestCase):
    def test_holds_without_enough_history(self):
        action, _ = strategy.decide([100, 101, 102], holding=False,
                                     entry_price=0)
        self.assertEqual(action, "HOLD")

    def test_stop_loss_triggers(self):
        # Build prices, then pretend we bought far above the current price.
        prices = data.demo_closes(config.HISTORY_DAYS, seed=2)
        entry = prices[-1] * 2  # we "paid" double -> way underwater
        action, reason = strategy.decide(prices, holding=True,
                                         entry_price=entry)
        self.assertEqual(action, "SELL")
        self.assertIn("stop-loss", reason)


class TestBacktest(unittest.TestCase):
    def test_every_strategy_runs_and_keeps_money_sane(self):
        prices = data.demo_closes(config.HISTORY_DAYS, seed=42)
        for name in strategy.STRATEGIES:
            final, trades, wins = backtest.run_backtest(prices, name)
            self.assertGreater(final, 0, name)        # never goes negative
            self.assertGreaterEqual(trades, 0, name)
            self.assertLessEqual(wins, trades, name)


class TestFloor(unittest.TestCase):
    def _fresh(self, cash):
        return {"cash": cash, "symbol": None, "coins": 0.0, "entry_price": 0.0}

    def test_buy_never_risks_below_floor(self):
        # Equity 20, floor 12 -> at most 8 may be spent (not 50% = 10).
        state = self._fresh(20.0)
        portfolio.buy(state, "BTC", 30000.0)
        spent = 20.0 - state["cash"]
        self.assertLessEqual(spent, 20.0 - config.FLOOR_USD + 1e-6)

    def test_no_buy_when_at_floor(self):
        state = self._fresh(config.FLOOR_USD)
        self.assertIsNone(portfolio.buy(state, "BTC", 30000.0))


class TestRiskRatio(unittest.TestCase):
    def test_take_profit_is_four_times_stop(self):
        # The 4:1 plan must hold.
        self.assertAlmostEqual(config.TAKE_PROFIT_PCT,
                               4 * config.STOP_LOSS_PCT, places=6)


if __name__ == "__main__":
    unittest.main()
