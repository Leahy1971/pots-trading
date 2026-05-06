"""
core/api_connector.py
=====================
Handles all communication with the Betfair Exchange API.
Uses betfairlightweight when available; falls back to direct HTTPS calls.
In demo mode it generates realistic synthetic market data for offline testing.
"""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone
from typing import Optional

# ── Optional betfairlightweight import ────────────────────────────────────────
try:
    import betfairlightweight as bfl
    from betfairlightweight.filters import (
        market_book_filter,
        price_projection,
    )
    BFL_AVAILABLE = True
except Exception:
    BFL_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

# Betfair's legal tick ladder (abbreviated)
TICK_LADDER: list[float] = [
    1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08, 1.09, 1.10,
    1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20,
    1.21, 1.22, 1.23, 1.24, 1.25, 1.27, 1.28, 1.29, 1.30, 1.32,
    1.33, 1.34, 1.35, 1.36, 1.37, 1.38, 1.39, 1.40, 1.42, 1.44,
    1.45, 1.46, 1.48, 1.50, 1.52, 1.53, 1.55, 1.57, 1.60, 1.62,
    1.63, 1.65, 1.67, 1.70, 1.72, 1.75, 1.80, 1.83, 1.85, 1.90,
    1.95, 2.00, 2.02, 2.04, 2.06, 2.08, 2.10, 2.12, 2.14, 2.16,
    2.20, 2.25, 2.30, 2.35, 2.40, 2.50, 2.60, 2.70, 2.80, 2.90,
    3.00, 3.10, 3.20, 3.30, 3.40, 3.50, 3.60, 3.70, 3.80, 3.90,
    4.00, 4.20, 4.40, 4.60, 4.80, 5.00, 5.50, 6.00, 6.50, 7.00,
    7.50, 8.00, 8.50, 9.00, 9.50, 10.0,
]


def nearest_tick(price: float) -> float:
    """Snap a price to the nearest valid Betfair tick."""
    return min(TICK_LADDER, key=lambda t: abs(t - price))


def next_tick(price: float, direction: int = 1) -> float:
    """Return the next tick up (+1) or down (-1) from the given price."""
    try:
        idx = TICK_LADDER.index(nearest_tick(price))
        new_idx = max(0, min(len(TICK_LADDER) - 1, idx + direction))
        return TICK_LADDER[new_idx]
    except ValueError:
        return price


# ──────────────────────────────────────────────────────────────────────────────
# Demo data generator
# ──────────────────────────────────────────────────────────────────────────────

class _DemoGenerator:
    """Generates realistic synthetic horse-racing market data for offline use."""

    _RUNNERS = [
        ("Golden Arrow",    3.50, "steaming"),
        ("Silver Lining",   5.00, "neutral"),
        ("Iron Duke",       7.00, "drifting"),
        ("Copper Chief",   12.0,  "neutral"),
        ("Bronze Falcon",  18.0,  "steaming"),
        ("Obsidian Storm", 22.0,  "drifting"),
    ]

    def __init__(self) -> None:
        self._start_time = time.time() + random.randint(180, 600)
        self._state: dict = {}
        for name, sp, bias in self._RUNNERS:
            self._state[name] = {
                "price":        sp,
                "lpt":          sp * random.uniform(0.97, 1.03),
                "bias":         bias,
                "total_matched": random.uniform(5_000, 15_000),
                "history":      [],
            }

    def fetch(self) -> dict:
        seconds_to_start = max(0, self._start_time - time.time())
        runners = []

        for name, _, _ in self._RUNNERS:
            s = self._state[name]
            bias = s["bias"]

            # Simulate price drift / steam
            drift = {"steaming": -0.005, "drifting": 0.008, "neutral": 0.0}[bias]
            noise = random.gauss(0, 0.004)
            raw_new = s["price"] * (1 + drift + noise)
            s["price"] = max(1.01, nearest_tick(raw_new))

            # LPT lags slightly behind
            s["lpt"] = nearest_tick(
                s["lpt"] * (1 + (s["price"] / s["lpt"] - 1) * 0.6 + random.gauss(0, 0.002))
            )

            # Weight of money
            if bias == "steaming":
                wom = random.uniform(0.60, 0.85)
            elif bias == "drifting":
                wom = random.uniform(0.20, 0.42)
            else:
                wom = random.uniform(0.43, 0.57)

            total_unmatched = random.uniform(2_000, 8_000)
            back_unmatched = total_unmatched * wom
            lay_unmatched  = total_unmatched * (1 - wom)

            # Volume traded this tick
            new_vol = random.uniform(100, 1_200)
            s["total_matched"] += new_vol

            # Traded grid (volume at each price ± 5 ticks)
            traded_grid: dict[float, float] = {}
            anchor = nearest_tick(s["price"])
            try:
                idx = TICK_LADDER.index(anchor)
            except ValueError:
                idx = len(TICK_LADDER) // 2
            for offset in range(-5, 6):
                t_idx = max(0, min(len(TICK_LADDER) - 1, idx + offset))
                tick = TICK_LADDER[t_idx]
                traded_grid[tick] = random.uniform(200, 3_000)

            # Price history (last 20 ticks)
            s["history"].append(s["price"])
            if len(s["history"]) > 60:
                s["history"].pop(0)

            runners.append({
                "name":           name,
                "back":           next_tick(s["price"],  1),
                "lay":            next_tick(s["price"], -1),
                "lpt":            s["lpt"],
                "back_unmatched": back_unmatched,
                "lay_unmatched":  lay_unmatched,
                "total_matched":  s["total_matched"],
                "traded_grid":    traded_grid,
                "price_history":  list(s["history"]),
            })

        return {
            "market_id":      "1.999999999",
            "market_name":    "2:30 Ascot — Demo Race",
            "seconds_to_start": seconds_to_start,
            "runners":        runners,
            "fetched_at":     datetime.now(timezone.utc).isoformat(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Live API connector
# ──────────────────────────────────────────────────────────────────────────────

class BetfairConnector:
    """
    Wraps betfairlightweight (preferred) or raw REST calls to fetch market data.
    Falls back to demo mode gracefully if the library is not installed.
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        app_key: str = "",
        demo: bool = False,
    ) -> None:
        self._demo    = demo
        self._client  = None
        self._username = username
        self._password = password
        self._app_key  = app_key
        self._demo_gen = _DemoGenerator() if demo else None

    # ── Authentication ─────────────────────────────────────────────────────────

    def login(self) -> bool:
        """Login to Betfair; returns True on success."""
        if self._demo:
            return True
        # Re-attempt import at login time in case the module-level
        # try/except failed silently on Python 3.14+
        try:
            import betfairlightweight as _bfl
        except Exception as exc:
            raise EnvironmentError(
                f"betfairlightweight could not be imported: {exc}\n"
                "Run:  pip install betfairlightweight"
            )
        self._client = _bfl.APIClient(
            username=self._username,
            password=self._password,
            app_key=self._app_key,
            certs="C:/certs",
        )
        try:
            self._client.login()
            return True
        except Exception:
            return False

    def logout(self) -> None:
        if self._client:
            try:
                self._client.logout()
            except Exception:
                pass

    # ── Data fetching ──────────────────────────────────────────────────────────

    def fetch_market(self, market_id: str) -> Optional[dict]:
        """Return a normalised market snapshot dict, or None on error."""
        if self._demo:
            return self._demo_gen.fetch()
        if BFL_AVAILABLE and self._client:
            return self._fetch_via_bfl(market_id)
        return None

    def _fetch_via_bfl(self, market_id: str) -> Optional[dict]:
        """Fetch live data using betfairlightweight."""
        try:
            import betfairlightweight as _bfl

            # Catalogue (runner names, event info)
            catalogue = self._client.betting.list_market_catalogue(
                filter=_bfl.filters.market_filter(market_ids=[market_id]),
                market_projection=[
                    "RUNNER_DESCRIPTION",
                    "EVENT",
                    "MARKET_START_TIME",
                ],
                max_results=1,
            )
            if not catalogue:
                return None
            cat = catalogue[0]

            # Book (prices, volumes)
            books = self._client.betting.list_market_book(
                market_ids=[market_id],
                price_projection=_bfl.filters.price_projection(
                    price_data=["EX_BEST_OFFERS", "EX_TRADED"],
                ),
            )
            if not books:
                return None
            book = books[0]

            # Seconds to start
            start_dt = cat.market_start_time
            now_utc  = datetime.now(timezone.utc)
            seconds_to_start = (start_dt - now_utc).total_seconds()

            # Build runner list
            runner_map = {r.selection_id: r.runner_name for r in cat.runners}
            runners = []
            for r in book.runners:
                ex = r.ex
                back_prices = ex.available_to_back if ex else []
                lay_prices  = ex.available_to_lay  if ex else []

                best_back = back_prices[0].price if back_prices else None
                best_lay  = lay_prices[0].price  if lay_prices  else None
                lpt       = r.last_price_traded

                back_vol = sum(ps.size for ps in back_prices)
                lay_vol  = sum(ps.size for ps in lay_prices)

                # Traded grid from ex_traded
                traded_grid: dict = {}
                if ex and hasattr(ex, "traded") and ex.traded:
                    for ps in ex.traded:
                        traded_grid[ps.price] = traded_grid.get(ps.price, 0) + ps.size

                runners.append({
                    "name":           runner_map.get(r.selection_id, str(r.selection_id)),
                    "back":           best_back,
                    "lay":            best_lay,
                    "lpt":            lpt,
                    "back_unmatched": back_vol,
                    "lay_unmatched":  lay_vol,
                    "total_matched":  r.total_matched or 0,
                    "traded_grid":    traded_grid,
                    "price_history":  [],
                })

            return {
                "market_id":      market_id,
                "market_name":    f"{cat.event.name} — {cat.market_name}",
                "seconds_to_start": max(0.0, seconds_to_start),
                "runners":        runners,
                "fetched_at":     now_utc.isoformat(),
            }

        except Exception as exc:
            import traceback
            return {"_error": str(exc), "_traceback": traceback.format_exc()}
