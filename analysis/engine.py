"""
analysis/engine.py
==================
The core analytical brain of the application.

Implements a weighted, multi-factor scoring system:
  1.  WOM Momentum Oscillator (with 60-second delta)
  2.  Price vs. EMA (20-period exponential moving average)
  3.  Price–Volume Divergence (mean reversion detection)
  4.  Support & Resistance identification from the traded grid
  5.  Smart Money detection (single trade > 5% of total volume)
  6.  Spread constraint (only trade a 1-tick spread)
  7.  Micro-Scalp opportunity detection

Each signal contributes points to a raw score; the final Confidence Score
is a normalised 1–10 integer.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Signal:
    """Trade recommendation for a single runner."""
    runner_name:    str
    back_price:     Optional[float]
    lay_price:      Optional[float]
    lpt:            Optional[float]
    wom:            float          # 0.0 – 1.0
    wom_delta:      float          # change over last 60 s
    ema_20:         float
    price_trend:    str            # "Steaming" | "Drifting" | "Neutral"
    resistance_lvl: Optional[float]
    support_lvl:    Optional[float]
    verdict:        str            # "BACK – …" | "LAY – …" | "SCALP" | "NO TRADE"
    verdict_code:   str            # "BACK" | "LAY" | "SCALP" | "NONE"
    confidence:     int            # 1 – 10
    reasons:        List[str]      = field(default_factory=list)
    smart_money:    bool           = False
    spread_ok:      bool           = True
    total_matched:  float          = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Per-runner state tracker (held between polls)
# ──────────────────────────────────────────────────────────────────────────────

class _RunnerState:
    """Maintains rolling history for a single runner across successive polls."""

    EMA_PERIOD   = 20    # ticks used in EMA calculation
    WOM_WINDOW   = 60    # seconds for WOM delta measurement
    HISTORY_LEN  = 120   # maximum price history length

    def __init__(self, name: str) -> None:
        self.name            = name
        self.price_history:  List[float]              = []
        self.wom_history:    Deque[Tuple[float, float]] = deque()  # (timestamp, wom)
        self.ema:            float                    = 0.0
        self.last_vol:       float                    = 0.0
        self.grid_history:   Dict[float, float]       = {}

    # ── EMA ───────────────────────────────────────────────────────────────────

    def update_ema(self, price: float) -> float:
        """Update and return the 20-period EMA of back price."""
        k = 2 / (self.EMA_PERIOD + 1)
        if not self.price_history:
            self.ema = price
        elif len(self.price_history) < self.EMA_PERIOD:
            # Use simple average until we have enough data
            self.price_history.append(price)
            self.ema = sum(self.price_history) / len(self.price_history)
        else:
            self.ema = price * k + self.ema * (1 - k)
            self.price_history.append(price)
            if len(self.price_history) > self.HISTORY_LEN:
                self.price_history.pop(0)
        return self.ema

    # ── WOM delta ─────────────────────────────────────────────────────────────

    def update_wom(self, wom: float) -> float:
        """Store WOM with timestamp; return delta over the last 60 seconds."""
        now = time.time()
        self.wom_history.append((now, wom))
        # Prune old entries
        while self.wom_history and self.wom_history[0][0] < now - self.WOM_WINDOW:
            self.wom_history.popleft()
        if len(self.wom_history) >= 2:
            oldest_wom = self.wom_history[0][1]
            return wom - oldest_wom
        return 0.0

    # ── Support / Resistance ───────────────────────────────────────────────────

    def update_grid(self, grid: Dict[float, float]) -> None:
        """Merge the latest traded grid snapshot into the rolling history."""
        for price, vol in grid.items():
            self.grid_history[price] = self.grid_history.get(price, 0) + vol

    def resistance_support(self) -> Tuple[Optional[float], Optional[float]]:
        """Return the price levels of maximum resistance and support."""
        if not self.grid_history:
            return None, None
        # Resistance = price with most matched volume (wall above current price)
        # Support    = same concept but below
        sorted_by_vol = sorted(self.grid_history.items(), key=lambda x: x[1], reverse=True)
        # Top 1 = resistance (highest volume level)
        resistance = sorted_by_vol[0][0] if sorted_by_vol else None
        support    = sorted_by_vol[1][0] if len(sorted_by_vol) > 1 else None
        return resistance, support


# ──────────────────────────────────────────────────────────────────────────────
# Main Analysis Engine
# ──────────────────────────────────────────────────────────────────────────────

class AnalysisEngine:
    """
    Processes a market snapshot and produces a list of Signal objects.

    Scoring table (raw points, max = 20):
    ┌─────────────────────────────────────────┬────────┐
    │ Factor                                  │  pts   │
    ├─────────────────────────────────────────┼────────┤
    │ Strong WOM (>70% or <30%)               │   4    │
    │ WOM delta confirms direction            │   3    │
    │ Price < EMA (steaming) / > EMA (drift)  │   3    │
    │ Price–Volume divergence                 │   3    │
    │ Price approaching resistance wall       │   3    │
    │ Smart Money spike                       │   2    │
    │ 1-tick spread                           │   2    │
    └─────────────────────────────────────────┴────────┘
    Confidence = ceil(raw / 20 * 10), clamped to 1–10.
    """

    SMART_MONEY_THRESHOLD = 0.05   # Trade > 5% total volume = "Smart Money"

    def __init__(self) -> None:
        self._states: Dict[str, _RunnerState] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyse(self, market_data: dict) -> List[Signal]:
        """
        Analyse a market snapshot; return one Signal per runner,
        ordered by confidence (highest first).
        """
        signals = []
        runners = market_data.get("runners", [])
        seconds_to_start = market_data.get("seconds_to_start", 9999)

        for runner in runners:
            name = runner.get("name", "Unknown")
            if name not in self._states:
                self._states[name] = _RunnerState(name)
            state = self._states[name]

            sig = self._analyse_runner(runner, state, seconds_to_start)
            signals.append(sig)

        return sorted(signals, key=lambda s: s.confidence, reverse=True)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _analyse_runner(
        self,
        runner: dict,
        state: _RunnerState,
        seconds_to_start: float,
    ) -> Signal:

        back      = runner.get("back")
        lay       = runner.get("lay")
        lpt       = runner.get("lpt")
        back_vol  = runner.get("back_unmatched", 0.0)
        lay_vol   = runner.get("lay_unmatched",  0.0)
        tot_match = runner.get("total_matched",  0.0)
        grid      = runner.get("traded_grid",    {})
        name      = runner.get("name", "Unknown")

        # ── WOM ───────────────────────────────────────────────────────────────
        total_unmatched = back_vol + lay_vol
        wom = (back_vol / total_unmatched) if total_unmatched > 0 else 0.5
        wom_delta = state.update_wom(wom)

        # ── EMA ───────────────────────────────────────────────────────────────
        mid_price = ((back or 0) + (lay or 0)) / 2 if back and lay else (back or lay or 0)
        ema = state.update_ema(mid_price) if mid_price else 0.0

        # ── Traded grid ───────────────────────────────────────────────────────
        state.update_grid(grid)
        state.last_vol = tot_match
        resistance, support = state.resistance_support()

        # ── Spread check ──────────────────────────────────────────────────────
        spread_ok = self._is_one_tick_spread(back, lay)

        # ── Smart money detection ─────────────────────────────────────────────
        smart_money = self._detect_smart_money(runner, tot_match)

        # ── Price trend ───────────────────────────────────────────────────────
        price_trend = self._price_trend(mid_price, ema, lpt)

        # ── Scoring ───────────────────────────────────────────────────────────
        raw_score, reasons = self._score(
            wom=wom,
            wom_delta=wom_delta,
            mid_price=mid_price,
            ema=ema,
            lpt=lpt,
            resistance=resistance,
            back_vol=back_vol,
            spread_ok=spread_ok,
            smart_money=smart_money,
            tot_match=tot_match,
            state=state,
        )

        # ── Verdict ───────────────────────────────────────────────────────────
        verdict, verdict_code = self._verdict(
            wom=wom,
            wom_delta=wom_delta,
            mid_price=mid_price,
            ema=ema,
            lpt=lpt,
            resistance=resistance,
            spread_ok=spread_ok,
            tot_match=tot_match,
            raw_score=raw_score,
        )

        # Minimum liquidity gate — override weak signals
        if tot_match < 2_000 and verdict_code != "NONE":
            verdict      = "NO TRADE — Low Liquidity"
            verdict_code = "NONE"
            reasons.append("Market liquidity below £2,000 threshold")

        # Time gate — only trade 2–10 min before off
        if not (120 <= seconds_to_start <= 600):
            verdict      = "NO TRADE — Outside Trading Window"
            verdict_code = "NONE"

        confidence = self._normalise_score(raw_score)

        return Signal(
            runner_name=name,
            back_price=back,
            lay_price=lay,
            lpt=lpt,
            wom=wom,
            wom_delta=wom_delta,
            ema_20=ema,
            price_trend=price_trend,
            resistance_lvl=resistance,
            support_lvl=support,
            verdict=verdict,
            verdict_code=verdict_code,
            confidence=confidence,
            reasons=reasons,
            smart_money=smart_money,
            spread_ok=spread_ok,
            total_matched=tot_match,
        )

    # ── Scoring engine ─────────────────────────────────────────────────────────

    def _score(
        self, *, wom, wom_delta, mid_price, ema, lpt,
        resistance, back_vol, spread_ok, smart_money,
        tot_match, state,
    ) -> Tuple[int, List[str]]:
        raw   = 0
        notes = []

        # 1. Strong WOM
        if wom > 0.70:
            raw += 4
            notes.append(f"WOM {wom:.0%} — heavy backing pressure")
        elif wom < 0.30:
            raw += 4
            notes.append(f"WOM {wom:.0%} — heavy laying pressure")
        elif wom > 0.55:
            raw += 2
            notes.append(f"WOM {wom:.0%} — moderate backing bias")
        elif wom < 0.45:
            raw += 2
            notes.append(f"WOM {wom:.0%} — moderate laying bias")

        # 2. WOM delta (momentum building)
        if abs(wom_delta) > 0.10:
            raw += 3
            direction = "increasing" if wom_delta > 0 else "decreasing"
            notes.append(f"WOM momentum {direction} ({wom_delta:+.1%} / 60 s)")
        elif abs(wom_delta) > 0.05:
            raw += 1
            notes.append(f"WOM momentum moderate ({wom_delta:+.1%} / 60 s)")

        # 3. Price vs. EMA
        if ema > 0 and mid_price > 0:
            if mid_price < ema * 0.98:
                raw += 3
                notes.append(f"Price {mid_price:.2f} below 20-EMA {ema:.2f} — steaming trend")
            elif mid_price > ema * 1.02:
                raw += 3
                notes.append(f"Price {mid_price:.2f} above 20-EMA {ema:.2f} — drifting trend")

        # 4. Price–Volume divergence (mean reversion)
        if (
            ema > 0
            and mid_price > ema
            and back_vol > 0
            and tot_match > 0
        ):
            back_fraction = back_vol / (back_vol + 1)  # proxy
            if back_fraction > 0.80:
                raw += 3
                notes.append("Price–Volume divergence: price elevated vs. heavy back money — snap-back likely")

        # 5. Resistance wall proximity
        if resistance and mid_price and abs(mid_price - resistance) / mid_price < 0.05:
            raw += 3
            notes.append(f"Price near resistance wall at {resistance:.2f}")

        # 6. Smart Money
        if smart_money:
            raw += 2
            notes.append("Smart Money spike detected — large single trade")

        # 7. Spread constraint
        if spread_ok:
            raw += 2
        else:
            notes.append("Spread wider than 1 tick — low liquidity signal")

        return raw, notes

    # ── Verdict logic ──────────────────────────────────────────────────────────

    def _verdict(
        self, *, wom, wom_delta, mid_price, ema, lpt,
        resistance, spread_ok, tot_match, raw_score,
    ) -> Tuple[str, str]:
        """
        Derive a human-readable trade verdict and a machine verdict code.
        """
        # Scalp opportunity: neutral WOM, tight price range
        if 0.45 <= wom <= 0.55 and spread_ok and tot_match > 5_000:
            return "SCALP — Neutral WOM, Capture 1 Tick", "SCALP"

        # Back signal
        back_conditions = (
            wom > 0.60
            and lpt is not None
            and mid_price is not None
            and mid_price < lpt
        )
        strong_back = wom > 0.70 and wom_delta > 0.10

        if back_conditions:
            if strong_back:
                return "BACK — Strong Momentum Steam", "BACK"
            return "BACK — Moderate Backing Pressure", "BACK"

        # Lay signal
        lay_conditions = (
            wom < 0.40
            and lpt is not None
            and mid_price is not None
            and mid_price > lpt
        )
        # Drift play: price above EMA and WOM weak
        drift_play = (
            ema > 0
            and mid_price is not None
            and mid_price > ema * 1.02
            and wom < 0.45
        )

        if lay_conditions or drift_play:
            if resistance and mid_price and abs(mid_price - resistance) / mid_price < 0.05:
                return "LAY — Resistance Found, Exit Zone", "LAY"
            return "LAY — Drift Play, Weak Market Support", "LAY"

        if raw_score < 4:
            return "NO TRADE — Insufficient Signal Confluence", "NONE"

        return "NO TRADE — Monitoring", "NONE"

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_one_tick_spread(back: Optional[float], lay: Optional[float]) -> bool:
        if back is None or lay is None:
            return False
        from core.api_connector import TICK_LADDER, nearest_tick
        b_tick = nearest_tick(back)
        l_tick = nearest_tick(lay)
        try:
            b_idx = TICK_LADDER.index(b_tick)
            l_idx = TICK_LADDER.index(l_tick)
            return abs(b_idx - l_idx) <= 1
        except ValueError:
            return False

    @staticmethod
    def _detect_smart_money(runner: dict, total_matched: float) -> bool:
        """Detect if any single trade exceeds 5% of total matched volume."""
        # In live mode this would inspect individual trade objects.
        # In demo / normalised mode we approximate via volume delta.
        grid = runner.get("traded_grid", {})
        if not grid or total_matched <= 0:
            return False
        max_single = max(grid.values(), default=0)
        return max_single > total_matched * 0.05

    @staticmethod
    def _price_trend(mid: float, ema: float, lpt: Optional[float]) -> str:
        if not mid or not ema:
            return "Neutral"
        if mid < ema * 0.99 and (lpt is None or mid < lpt):
            return "Steaming"
        if mid > ema * 1.01 and (lpt is None or mid > lpt):
            return "Drifting"
        return "Neutral"

    @staticmethod
    def _normalise_score(raw: int, max_raw: int = 20) -> int:
        import math
        ratio = raw / max_raw
        return max(1, min(10, math.ceil(ratio * 10)))
