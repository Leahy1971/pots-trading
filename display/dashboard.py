"""
display/dashboard.py
====================
Renders a live, colour-coded terminal dashboard using the Rich library.

Layout (top to bottom):
  ┌──────────────────────────────────────────────────────┐
  │  HEADER  — market name / time to off / timestamp     │
  ├────────────────────┬─────────────────────────────────┤
  │  RUNNER TABLE      │  WOM BARS                       │
  ├────────────────────┴─────────────────────────────────┤
  │  TRADE VERDICTS  (one panel per signal)              │
  ├──────────────────────────────────────────────────────┤
  │  TOP SIGNAL DETAIL  (reasons, resistance, EMA)       │
  └──────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import contextlib
import math
from typing import List

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from analysis.engine import Signal

console = Console()

# ── Colour map ────────────────────────────────────────────────────────────────
VERDICT_COLOUR = {
    "BACK":  "bold green",
    "LAY":   "bold red",
    "SCALP": "bold cyan",
    "NONE":  "dim white",
}

TREND_COLOUR = {
    "Steaming": "green",
    "Drifting": "red",
    "Neutral":  "yellow",
}

TREND_ARROW = {
    "Steaming": "▼",
    "Drifting": "▲",
    "Neutral":  "─",
}


# ──────────────────────────────────────────────────────────────────────────────

class Dashboard:
    """Produces all Rich-rendered output for the trading terminal."""

    def __init__(self) -> None:
        self._console = console
        self._live: Live | None = None

    # ── Banner ────────────────────────────────────────────────────────────────

    def print_banner(self) -> None:
        banner = Text()
        banner.append("  ╔══════════════════════════════════════════╗\n", style="bold cyan")
        banner.append("  ║  ", style="bold cyan")
        banner.append("BETFAIR PRE-RACE TRADING TERMINAL", style="bold white")
        banner.append("  ║\n", style="bold cyan")
        banner.append("  ║  ", style="bold cyan")
        banner.append("v1.0  ·  Pre-Race Only  ·  Oxford English  ", style="dim")
        banner.append("║\n", style="bold cyan")
        banner.append("  ╚══════════════════════════════════════════╝\n", style="bold cyan")
        self._console.print(banner)

    # ── Live context ──────────────────────────────────────────────────────────

    @contextlib.contextmanager
    def live_context(self):
        with Live(
            console=self._console,
            refresh_per_second=2,
            screen=False,
        ) as live:
            self._live = live
            yield live

    # ── Main render ───────────────────────────────────────────────────────────

    def render(
        self,
        live: Live,
        market_data: dict,
        signals: List[Signal],
    ) -> None:
        sections = []

        sections.append(self._header(market_data))
        sections.append(self._runner_table(signals))
        sections.append(self._wom_bars(signals))
        sections.append(self._verdicts(signals))

        if signals:
            sections.append(self._top_signal_detail(signals[0]))

        from rich.console import Group
        live.update(Group(*sections))

    # ── Sections ──────────────────────────────────────────────────────────────

    def _header(self, market_data: dict) -> Panel:
        secs   = market_data.get("seconds_to_start", 0)
        mins   = int(secs // 60)
        s_rem  = int(secs % 60)
        name   = market_data.get("market_name", "Unknown Market")
        ts     = market_data.get("fetched_at", "")[:19].replace("T", " ")

        colour = "green" if secs > 300 else ("yellow" if secs > 120 else "red")

        txt = Text()
        txt.append(f"  {name}\n", style="bold white")
        txt.append(f"  ⏱  Time to Off: ", style="dim")
        txt.append(f"{mins}m {s_rem:02d}s", style=f"bold {colour}")
        txt.append(f"   ·   Last update: {ts} UTC", style="dim")

        return Panel(txt, title="[bold cyan]MARKET[/bold cyan]", border_style="cyan")

    def _runner_table(self, signals: List[Signal]) -> Table:
        t = Table(
            title="Runners",
            box=box.SIMPLE_HEAVY,
            header_style="bold magenta",
            show_lines=False,
        )
        t.add_column("Runner",      style="white",        width=22)
        t.add_column("Back",        style="bold green",   justify="right", width=7)
        t.add_column("Lay",         style="bold red",     justify="right", width=7)
        t.add_column("LPT",         style="yellow",       justify="right", width=7)
        t.add_column("Trend",       justify="center",     width=10)
        t.add_column("EMA-20",      style="dim",          justify="right", width=8)
        t.add_column("Vol (£k)",    style="dim",          justify="right", width=9)
        t.add_column("Confidence",  justify="center",     width=12)

        for sig in signals:
            trend_col = TREND_COLOUR.get(sig.price_trend, "white")
            arrow     = TREND_ARROW.get(sig.price_trend, "─")
            conf_bar  = self._conf_bar(sig.confidence)

            t.add_row(
                sig.runner_name[:22],
                f"{sig.back_price:.2f}"   if sig.back_price else "—",
                f"{sig.lay_price:.2f}"    if sig.lay_price  else "—",
                f"{sig.lpt:.2f}"          if sig.lpt        else "—",
                Text(f"{arrow} {sig.price_trend}", style=trend_col),
                f"{sig.ema_20:.2f}"       if sig.ema_20 > 0 else "—",
                f"{sig.total_matched/1000:.1f}",
                conf_bar,
            )
        return t

    def _wom_bars(self, signals: List[Signal]) -> Panel:
        """Horizontal ASCII bars showing WOM for each runner."""
        lines: List[Text] = []
        bar_width = 30

        for sig in signals:
            wom    = sig.wom
            filled = int(round(wom * bar_width))
            empty  = bar_width - filled

            bar = Text()
            bar.append(f"  {sig.runner_name[:18]:<18} ", style="dim white")
            bar.append("LAY ", style="bold red")
            bar.append("█" * (bar_width - filled), style="red")
            bar.append("░" * filled,               style="green")
            bar.append(" BACK", style="bold green")
            bar.append(f"  WOM {wom:.0%}", style="white")

            if sig.wom_delta > 0.05:
                bar.append(f"  ↑ +{sig.wom_delta:.1%}", style="green")
            elif sig.wom_delta < -0.05:
                bar.append(f"  ↓ {sig.wom_delta:.1%}", style="red")

            lines.append(bar)

        # Combine into a single renderable
        from rich.console import Group
        return Panel(
            Group(*lines),
            title="[bold magenta]WEIGHT OF MONEY[/bold magenta]",
            border_style="magenta",
        )

    def _verdicts(self, signals: List[Signal]) -> Panel:
        """One-line verdict per runner, colour coded."""
        lines: List[Text] = []

        for sig in signals:
            col = VERDICT_COLOUR.get(sig.verdict_code, "dim white")
            t   = Text()
            t.append(f"  {sig.runner_name[:18]:<18} ", style="white")
            t.append(f"► {sig.verdict}", style=col)

            sm_flag = "  ⚡ Smart Money" if sig.smart_money else ""
            sp_warn = "" if sig.spread_ok else "  ⚠ Wide Spread"
            t.append(sm_flag, style="bold yellow")
            t.append(sp_warn, style="bold red")
            lines.append(t)

        from rich.console import Group
        return Panel(
            Group(*lines),
            title="[bold yellow]TRADE VERDICTS[/bold yellow]",
            border_style="yellow",
        )

    def _top_signal_detail(self, sig: Signal) -> Panel:
        """Detailed breakdown for the highest-confidence signal."""
        col = VERDICT_COLOUR.get(sig.verdict_code, "dim white")

        t = Text()
        t.append(f"\n  TOP SIGNAL: {sig.runner_name}\n\n", style="bold white")
        t.append(f"  Verdict:     ", style="dim")
        t.append(f"{sig.verdict}\n", style=col)
        t.append(f"  Confidence:  ", style="dim")
        t.append(f"{sig.confidence}/10  {self._conf_bar(sig.confidence)}\n", style="white")
        t.append(f"  Back / Lay:  ", style="dim")
        t.append(
            f"{sig.back_price or '—'} / {sig.lay_price or '—'}\n",
            style="white"
        )
        t.append(f"  LPT:         ", style="dim")
        t.append(f"{sig.lpt or '—'}\n", style="yellow")
        t.append(f"  EMA-20:      ", style="dim")
        t.append(f"{sig.ema_20:.2f}\n", style="white")

        if sig.resistance_lvl:
            t.append(f"  Resistance:  ", style="dim")
            t.append(f"{sig.resistance_lvl:.2f}\n", style="red")
        if sig.support_lvl:
            t.append(f"  Support:     ", style="dim")
            t.append(f"{sig.support_lvl:.2f}\n", style="green")

        if sig.reasons:
            t.append("\n  Signal Evidence:\n", style="bold dim")
            for reason in sig.reasons:
                t.append(f"    • {reason}\n", style="dim white")

        return Panel(
            t,
            title="[bold white]SIGNAL DETAIL[/bold white]",
            border_style="white",
        )

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _conf_bar(score: int) -> Text:
        """Return a coloured 10-block confidence bar."""
        filled = score
        empty  = 10 - score
        if score >= 7:
            colour = "green"
        elif score >= 4:
            colour = "yellow"
        else:
            colour = "red"
        t = Text()
        t.append("█" * filled, style=colour)
        t.append("░" * empty,  style="dim")
        t.append(f" {score}/10", style=colour)
        return t

    # ── Error / warning helpers ────────────────────────────────────────────────

    def show_error(self, live: Live, message: str) -> None:
        live.update(
            Panel(
                Text(f"  ⚠  {message}", style="bold red"),
                title="ERROR",
                border_style="red",
            )
        )

    def show_pre_off_warning(self, live: Live) -> None:
        live.update(
            Panel(
                Text(
                    "  Race is 60 seconds or less from the off.\n"
                    "  All trading signals suspended — exiting safely.",
                    style="bold yellow",
                ),
                title="⚑  PRE-OFF LOCKOUT",
                border_style="yellow",
            )
        )
