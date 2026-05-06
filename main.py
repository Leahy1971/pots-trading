"""
Betfair Pre-Race Trading Terminal
==================================
Entry point. Run with:  python main.py
"""

import sys
import time
import argparse
from rich.console import Console
from rich.prompt import Prompt

from core.api_connector import BetfairConnector
from analysis.engine import AnalysisEngine
from display.dashboard import Dashboard

console = Console()


def parse_market_id(raw: str) -> str:
    """Accept a full Betfair URL or a bare market ID and return '1.XXXXXXXXX'."""
    raw = raw.strip()
    if "betfair.com" in raw:
        # Extract the numeric ID that follows 'market/'
        parts = raw.split("market/")
        if len(parts) > 1:
            market_id = parts[-1].split("?")[0].strip("/")
            if not market_id.startswith("1."):
                market_id = f"1.{market_id}"
            return market_id
    if raw.isdigit():
        return f"1.{raw}"
    return raw  # Already formatted, e.g. "1.234567890"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Betfair Pre-Race Trading Terminal"
    )
    parser.add_argument(
        "--market", "-m",
        help="Betfair Market ID or URL (e.g. 1.234567890)",
        default=None,
    )
    parser.add_argument(
        "--demo", "-d",
        action="store_true",
        help="Run in demo mode with simulated data (no API key required)",
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=5,
        help="Poll interval in seconds (default: 5)",
    )
    args = parser.parse_args()

    dashboard = Dashboard()
    dashboard.print_banner()

    # ── Credentials ────────────────────────────────────────────────────────────
    if args.demo:
        console.print(
            "\n[bold yellow]⚡ DEMO MODE — simulated market data[/bold yellow]\n"
        )
        connector = BetfairConnector(demo=True)
    else:
        console.print("\n[bold cyan]Betfair API Login[/bold cyan]")
        username   = Prompt.ask("  Username")
        password   = Prompt.ask("  Password", password=True)
        app_key    = Prompt.ask("  App Key")
        connector  = BetfairConnector(
            username=username,
            password=password,
            app_key=app_key,
            demo=False,
        )
        if not connector.login():
            console.print("[bold red]Login failed — check credentials.[/bold red]")
            sys.exit(1)
        console.print("[bold green]✓ Logged in successfully[/bold green]\n")

    # ── Market ID ──────────────────────────────────────────────────────────────
    if args.market:
        market_id = parse_market_id(args.market)
    else:
        raw = Prompt.ask(
            "  Enter Market ID or Betfair URL",
            default="DEMO" if args.demo else "",
        )
        market_id = parse_market_id(raw) if raw.upper() != "DEMO" else "1.999999999"

    console.print(f"\n[dim]Market ID: {market_id}[/dim]")
    console.print(
        f"[dim]Polling every {args.interval}s — press Ctrl+C to exit[/dim]\n"
    )
    time.sleep(1)

    # ── Main polling loop ──────────────────────────────────────────────────────
    engine = AnalysisEngine()

    try:
        with dashboard.live_context() as live:
            while True:
                market_data = connector.fetch_market(market_id)

                if market_data is None:
                    dashboard.show_error(live, "Unable to fetch market data.")
                    time.sleep(args.interval)
                    continue

                if "_error" in market_data:
                    err = market_data["_error"]
                    tb  = market_data.get("_traceback", "")
                    dashboard.show_error(live, f"API Error: {err} | {tb[-300:]}")
                    time.sleep(args.interval)
                    continue

                # Bail out 60 seconds before the off
                seconds_to_start = market_data.get("seconds_to_start", 9999)
                if seconds_to_start <= 60:
                    dashboard.show_pre_off_warning(live)
                    time.sleep(2)
                    break

                signals = engine.analyse(market_data)
                dashboard.render(live, market_data, signals)

                time.sleep(args.interval)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Session ended by user.[/bold yellow]")
    finally:
        if not args.demo:
            connector.logout()
            console.print("[dim]Session token released.[/dim]")


if __name__ == "__main__":
    main()
