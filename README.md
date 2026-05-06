# Betfair Pre-Race Trading Terminal

A modular Python application for pre-race horse racing analysis on the Betfair Exchange.
Provides real-time trading signals based on Weight of Money, price action, EMA trend
analysis, and volume divergence — displayed in a colour-coded Rich terminal dashboard.

---

## Project Structure

```
betfair_trader/
├── main.py                    ← Entry point
├── requirements.txt
├── core/
│   └── api_connector.py       ← Betfair API wrapper (live + demo mode)
├── analysis/
│   └── engine.py              ← Multi-factor weighted scoring engine
└── display/
    └── dashboard.py           ← Rich terminal dashboard renderer
```

---

## Quick Start (Demo Mode — No API Key Required)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run with simulated market data
python main.py --demo

# 3. Optional: set a faster poll interval (seconds)
python main.py --demo --interval 3
```

---

## Live Trading Setup

### Prerequisites

1. A Betfair account with a funded wallet.
2. A **Betfair Developer App Key** — apply at:
   https://developer.betfair.com/get-started/

3. Install the API client:

```bash
pip install betfairlightweight rich
```

### Running Live

```bash
# With an interactive login prompt
python main.py

# Or pass a market ID directly (found in the Betfair URL)
python main.py --market 1.234567890

# Or paste a full Betfair URL
python main.py --market "https://www.betfair.com/exchange/plus/horse-racing/market/1.234567890"
```

You will be prompted for your Betfair username, password, and App Key.

---

## How the Analysis Engine Works

The engine applies a **weighted multi-factor score (0–20 raw, normalised to 1–10)**:

| Factor                           | Max Points | Logic                                              |
|----------------------------------|------------|-----------------------------------------------------|
| WOM strength (>70% or <30%)      | 4          | Strong imbalance = directional conviction           |
| WOM 60-second momentum delta     | 3          | Is the pressure building or fading?                 |
| Price vs. 20-period EMA          | 3          | Below EMA = steaming; above = drifting              |
| Price–Volume divergence          | 3          | Price elevated but heavy back money = mean reversion|
| Resistance wall proximity        | 3          | Price near volume peak = likely reversal            |
| Smart Money spike detection      | 2          | Single trade > 5% of total matched volume           |
| 1-tick spread constraint         | 2          | Only trade liquid, tight markets                    |

### Verdict Logic

| Verdict                         | Condition                                                        |
|---------------------------------|------------------------------------------------------------------|
| BACK — Strong Momentum Steam    | WOM > 70%, delta > +10%, Price < LPT                            |
| BACK — Moderate Backing Pressure| WOM > 60%, Price < LPT                                          |
| LAY — Resistance Found          | WOM < 40%, Price > LPT, near resistance wall                    |
| LAY — Drift Play                | Price > EMA by 2%+, WOM < 45%                                   |
| SCALP — Neutral WOM             | WOM 45%–55%, 1-tick spread, vol > £5,000                        |
| NO TRADE                        | Insufficient confluence, low liquidity, or outside window       |

### Trading Window
The application **only signals trades between 2 and 10 minutes before the off** and
automatically suspends all signals within the final 60 seconds.

---

## Indicators Explained

### Weight of Money (WOM)
```
WOM = Back Unmatched Volume / (Back + Lay Unmatched Volume)
```
- **>70%**: Heavy backing pressure — price likely to shorten.
- **<30%**: Heavy laying pressure — price likely to drift.
- **45–55%**: Neutral — look for a scalp opportunity.

### WOM Momentum Oscillator
The engine tracks WOM over a **60-second rolling window**.  
A delta of **+10% or more** confirms that pressure is building, not dissipating.

### Price–Volume Divergence
If the current price sits **above the 20-EMA** but the unmatched back money is
proportionally heavy, the price is likely to "snap back" — a mean reversion short trade.

### Support & Resistance
The traded grid (matched volume at each price point) accumulates across polls.
The price level with the most matched volume becomes the **resistance wall**.
When the live price approaches this level from below, a reversal signal is raised.

### Smart Money Detection
Any single matched trade exceeding **5% of total market volume** is flagged as a
"Smart Money" entry. Aligning your trade with this direction increases edge probability.

---

## Risk Warnings

- **This is a trading tool, not a betting system.** Pre-race trading requires discipline,
  fast exits, and strict risk management.
- Always begin with the **minimum Betfair stake (£2)** to verify signal quality.
- The 60-second pre-off lockout is a hard safety gate — never override it.
- Past signal accuracy in demo mode does **not** guarantee live performance.
- Betfair commission applies to all net winnings — factor this into your edge calculation.

---

## Licence

Personal use only. Not for redistribution or commercial deployment.
