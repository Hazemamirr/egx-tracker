# EGX Session Tracker

A small site that shows, after every EGX trading session ("جلسة"), how much
each tracked stock moved (%) and its volume — sorted into all / top gainers /
top losers / most active.

It's two pieces:

1. **`scraper/fetch_egx.py`** — a Python script that pulls the latest close,
   % change and volume for each ticker in `data/tickers.json` from Yahoo
   Finance, and writes it to `data/latest.json`.
2. **`index.html` / `style.css` / `app.js`** — a static page that reads
   `data/latest.json` and renders it. No backend needed at request time.

A GitHub Actions workflow (`.github/workflows/update.yml`) runs the scraper
automatically after each session and commits the fresh `data/latest.json`,
so the live site updates itself.

## Why Yahoo Finance, and its limits

EGX itself doesn't publish a free, structured API — its official daily
bulletin is a PDF/Excel report. Yahoo Finance lists most actively-traded EGX
stocks under a `.CA` suffix (e.g. `COMI.CA` for Commercial International
Bank) and has a stable-enough unofficial interface (via the `yfinance`
package) to pull from. This is a **best-effort public source**, not an
official feed:

- It won't cover all 200+ EGX-listed names — only the ones Yahoo tracks.
  `data/tickers.json` ships with 97 names that were each verified to return
  live, actively-traded data. Add more by looking up a company's `.CA`
  ticker on Yahoo Finance and adding a line.
- Yahoo can change its unofficial API without notice. If the scraper starts
  failing, try `pip install -U yfinance` first — that package tracks Yahoo's
  changes closely.
- If you later get access to a paid feed (EODHD, ICE, a broker API), swap
  it into `fetch_egx.py` — the frontend only cares about the shape of
  `data/latest.json` below, not where the numbers came from.

### Three Yahoo quirks this project works around

These were all found by running against the live API, and they are the
reason a few things in `fetch_egx.py` look the way they do. Please read
before "simplifying" it.

**1. Yahoo's quote endpoint is broken for `.CA` symbols.** `Ticker.info`
and `Ticker.fast_info` — the obvious way to get a live price — return
long-stale garbage. For `COMI.CA` they report a price of 81.20, a
`regularMarketTime` from **2024**, and a `quoteType` of `MUTUALFUND`, while
the real close that day was 128.10. The scraper therefore reads daily bars
from the *history* endpoint only, which is accurate and current.

**2. Yahoo publishes the daily bar hours after the close.** EGX closes
~14:30 Cairo; the bar for that session was measured as still missing more
than 2.5 hours later. A job that runs "shortly after the close" will
silently fetch the *previous* session and present it as today's. Hence the
late cron times, the morning catch-up run, and the staleness banner on the
site.

**3. Yahoo keeps serving frozen quotes for dead listings.** `ORAS.CA`
(Orascom Construction) sat at exactly 71.05 with zero volume for months
after it stopped trading on EGX. It has been removed from `tickers.json`,
and the scraper now rejects any name with no trades at all across its last
10 sessions so a delisted stock can't quietly show up as a flat row.

The scraper also passes `auto_adjust=False`. yfinance defaults to
back-adjusting closes for dividends, which silently rewrites past prices
every time a stock goes ex-dividend. We want the actual traded EGP close, so
the % change here matches what EGX itself publishes.

## Quick start (local)

```bash
pip install -r requirements.txt
python scraper/fetch_egx.py     # writes data/latest.json
python -m http.server 8000      # serves the site at localhost:8000
```

Open http://localhost:8000 — you should see real numbers instead of the demo
banner.

## The update schedule

`.github/workflows/update.yml` runs twice per trading day:

| cron (UTC)       | Cairo (summer / winter) | purpose                          |
|------------------|-------------------------|----------------------------------|
| `23 18 * * 0-4`  | 21:23 / 20:23, Sun–Thu  | main run, ~7h after the close    |
| `23 6  * * *`    | 09:23 / 08:23, daily    | catch-up before the next open    |

EGX is closed Friday and Saturday, so the main run only fires Sun–Thu. The
catch-up runs *every* day on purpose: if Yahoo hasn't published Thursday's
bar by Friday morning, a Mon–Fri catch-up would leave Wednesday's closes on
the site until Sunday evening. The extra weekend runs cost nothing — they
find no new session and skip the commit.

Both are deliberately late, because of quirk #2 above. Cairo is UTC+3 in
summer and UTC+2 in winter, and GitHub cron is always UTC — both slots stay
safely after the close and on the correct Cairo day year-round. The minutes
are off-the-hour on purpose: GitHub delays scheduled runs that pile up
at `:00`.

The commit step only commits when the *numbers* changed, not just the
`updated_at` stamp, so weekends and holidays don't produce empty commits.
You can also trigger the workflow manually any time from the **Actions** tab.

> Scheduled workflows are disabled automatically after 60 days with no
> activity in the repo. If the data stops updating, check the Actions tab —
> a manual run re-enables the schedule.

## Deploying it (GitHub Pages)

1. Push this folder to a GitHub repo.
2. **Settings → Pages** → source "Deploy from a branch", branch `main`,
   folder `/ (root)`.
3. **Settings → Actions → General → Workflow permissions** → "Read and write
   permissions" (the update workflow needs this to commit `data/latest.json`
   back to the repo).
4. Your site goes live at `https://<username>.github.io/<repo-name>/`.

> **Private repos:** GitHub Pages only serves from a private repo on a paid
> plan (Pro / Team / Enterprise). On the Free plan you'll need to make the
> repo public to publish the site. The scraper and Actions workflow work
> either way — it's only the public URL that needs the plan.

If you'd rather host elsewhere (Netlify, Vercel, your own server), the
static files (`index.html`, `style.css`, `app.js`, `data/`) work anywhere —
you just need *something* to run `fetch_egx.py` on a schedule and update
`data/latest.json` (a GitHub Action, a cron job, etc.).

## `data/latest.json` shape

```json
{
  "updated_at": "2026-09-24T18:23:11+00:00",
  "session_date": "2026-09-24",
  "demo": false,
  "stocks": [
    { "symbol": "COMI.CA", "name": "Commercial International Bank",
      "name_ar": "البنك التجاري الدولي", "price": 128.1,
      "prev_close": 131.5, "change_pct": -2.59, "volume": 5462562,
      "session_date": "2026-09-24" }
  ]
}
```

A ticker that couldn't be fetched appears with an `error` key instead of
prices, and the frontend skips it rather than rendering a blank row.

`session_date` is the date of the bar the numbers actually came from. The
site compares it to today and shows a warning banner once the data is more
than four days old (EGX trades Sun–Thu, so a Thursday close is legitimately
three days old by Sunday), which is what surfaces a silently broken feed.

## Customizing

- **Add/remove stocks** — edit `data/tickers.json`. English names come from
  Yahoo's own `longName`; the Arabic names were filled in by hand, so
  correct any that read oddly. `BIOC.CA` is listed under its former
  GlaxoSmithKline name, which is worth double-checking.
- **Change the update time** — edit the `cron` lines in
  `.github/workflows/update.yml` (UTC; see the table above).
- **Colors / fonts / layout** — `style.css` uses CSS variables at the top
  (`:root { ... }`) for the whole palette.
- **Green = up / red = down** is used here (the global convention). If you'd
  rather match a specific local convention, swap `--up` and `--down` in
  `style.css`.
