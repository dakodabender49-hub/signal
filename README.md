# SIGNAL - Daily Market Brief (Phase 1)

A free, no-noise market system: a **deployed dashboard** you can open anywhere plus
**two emailed briefs a day** (pre-open + post-close). Objective, evidence-first reads
in the spirit of The Trade Brigade - price action, structure, defined levels, no opinion.
Numbers are **cross-checked across two sources and fail-closed**: if a value can't be
verified it is withheld, never guessed.

Covers SPY, QQQ and your watchlist (**Mag 7 + MU**), with Fibonacci, support/resistance,
moving averages, pivots and ATR. Fed/economic events lead every brief.

## Try it locally (no keys, 10 seconds)
```bash
python app/test_indicators.py        # 8 golden tests on the math - all pass
python app/build.py --mode sample    # builds docs/index.html with SAMPLE data
# open docs/index.html in your browser
```
`--mode sample` is simulated data for layout only and is clearly labeled in the UI.

## Deploy it free (dashboard reachable anywhere)
1. Create a GitHub repo and push this folder.
2. **Settings -> Pages -> Source: Deploy from a branch -> `main` / `/docs`.**
   Your dashboard goes live at `https://<you>.github.io/<repo>/`.
3. The included Action (`.github/workflows/brief.yml`) runs **pre-open (~08:00 ET)** and
   **post-close (~16:20 ET)** on weekdays, rebuilds with live cross-checked data, emails
   the brief, and commits the refreshed dashboard. Trigger it once manually from the
   **Actions** tab to seed live data.

### Email (free)
Add repo **Settings -> Secrets and variables -> Actions**:
`SMTP_HOST` (`smtp.gmail.com`), `SMTP_PORT` (`465`), `SMTP_USER` (your address),
`SMTP_PASS` (a Gmail **App Password**, not your login), `EMAIL_TO` (where to send).
No secrets? The Action just prints the brief instead of emailing.

## Add or remove a stock
Edit **`config/watchlist.json`** -> `stocks`, commit. The next run picks it up everywhere
(dashboard + emails). Example: add Palantir ->
```json
"stocks": ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","MU","PLTR"]
```

## How the accuracy guarantee works
- Each instrument's latest close is pulled from **two independent free sources** (Stooq +
  yfinance) and reconciled to within **0.1%**; a mismatch withholds that name (fail-closed).
- Validation gates: OHLC invariants (`L<=O,C<=H`), no negatives/dupes, monotonic dates,
  freshness, implausible-move flag.
- `app/test_indicators.py` locks every formula (Fib, pivots, ATR, MAs) to known values so
  a regression can't silently ship a wrong number.
- Official macro (CPI/PCE/rates) is sourced from FRED / the issuing agency in live mode.

## Layout
```
app/      indicators.py  integrity.py  datafeed.py  read_engine.py  build.py  email_brief.py  test_indicators.py
config/   watchlist.json          # <- edit to add tickers
site/     template.html           # dashboard source (build injects state)
docs/     index.html  state.json  # generated; GitHub Pages serves this
.github/workflows/brief.yml       # pre-open + post-close cron
```

## Roadmap (next phases)
P2: real Fed/econ calendar feed + fundamentals cards.  P3: movers + objective setup screener,
confluence/delta intelligence.  P4: hardened post-close reconciliation + "add ticker" form.
P5: free delayed-intraday -> VWAP, opening range, volume profile.

*Not financial advice. Screens surface candidates for your own review.*
