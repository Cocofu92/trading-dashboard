# Trading Dashboard

A mobile-optimised daily trading dashboard for 17 instruments across Energy, Metals, Forex, and Indices.

## Features

- **Daily Bias** — Long / Short / Neutral based on price vs 200 EMA (0.5% dead zone)
- **EMA Stack** — 21/50/200 alignment (Bull / Bear / Mixed)
- **TTM Squeeze** — Squeeze state + histogram direction
- **52-Week VWAP** — Anchored VWAP with % distance from price
- **5-Year VWAP** — Anchored VWAP with % distance from price
- **Setup Tier** — Auto-scored A / B / None based on signal alignment
- **Key Levels** — Per-instrument notes saved locally in your browser
- **Economic Calendar** — High/Medium impact events for today & tomorrow
- **TradingView links** — One tap to open any chart

## Instruments Covered

| Group | Instruments |
|---|---|
| Energy | TTF Gas, Brent Crude |
| Metals | Gold, Silver, Platinum, Copper |
| Forex | GBP/JPY, EUR/JPY, GBP/USD, EUR/USD, EUR/GBP |
| US Index | NASDAQ, S&P 500, Russell 2000 |
| Other Index | FTSE 100, DAX, Nikkei 225 |

## Setup: Deploy to Render (Free)

### Step 1 — Push to GitHub

1. Create a new **private** GitHub repository (e.g. `trading-dashboard`)
2. Push all files:

```bash
cd trading-dashboard
git init
git add .
git commit -m "Initial dashboard"
git remote add origin https://github.com/YOUR_USERNAME/trading-dashboard.git
git push -u origin main
```

### Step 2 — Deploy on Render

1. Go to [render.com](https://render.com) and sign up (free)
2. Click **New → Web Service**
3. Connect your GitHub account and select the `trading-dashboard` repo
4. Render will auto-detect the `render.yaml` — just click **Deploy**
5. Wait ~3 minutes for the build to complete
6. Your dashboard will be live at `https://trading-dashboard.onrender.com`

> **Note:** On Render's free tier, the service sleeps after 15 minutes of inactivity. First load after sleep takes ~30 seconds. Upgrade to Render's $7/month plan to keep it always-on.

### Step 3 — Bookmark on your phone

On iPhone: Safari → Share → Add to Home Screen  
On Android: Chrome → Menu → Add to Home Screen

This gives you a full-screen app icon on your home screen.

## Running Locally

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

## Data & Caching

- Data is fetched via **yfinance** (Yahoo Finance) — free, no API key needed
- Results are **cached for 30 minutes** — no repeated fetches on refresh
- Hit the **↺ REFRESH** button to force a fresh fetch
- VWAP calculations use full historical data (5Y for 5Y VWAP, 1Y for 52W VWAP)

## Setup Tier Logic

| Tier | Criteria |
|---|---|
| **A** | Bias + EMA stack aligned + TTM Squeeze fired |
| **B** | Bias + stack aligned but squeeze building, OR stack partially aligned |
| **None** | Conflicting signals |

## Key Levels

Key levels are stored **locally in your browser** (localStorage). They persist across sessions on the same device. Enter levels in the expanded row view or via the **Key Levels** tab.

## Limitations (Free API)

- **TTF Gas (TFM1!)** may have limited data via Yahoo Finance — consider manual price check on TradingView
- **Rate limits**: yfinance has occasional throttling; the 30-min cache mitigates this
- Data is **end-of-day** — no intraday updates

## Upgrading to Paid Data

To switch from yfinance to Databento or Polygon.io:
1. Replace the `fetch_ohlcv()` function in `app.py` with the respective API client
2. Add your API key as an environment variable in Render settings
3. Everything else (calculations, frontend) remains unchanged
