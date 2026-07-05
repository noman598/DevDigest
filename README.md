# GitHub Trending Digest

Daily email digest of trending GitHub repos, summarized by Claude.

## Architecture

```
scrapers/github_trending.py   -> fetches github.com/trending (BeautifulSoup, retry logic)
storage/db.py                  -> SQLite, dedup + idempotency
services/summarizer.py         -> batches new items into one Claude API call
services/mailer.py              -> renders HTML email, sends via Resend
main.py                        -> orchestrates the full pipeline
scheduler.py                   -> optional: runs main.py daily, in-process
```

Every module is isolated behind a clean function signature, so swapping
SQLite -> Postgres, or Resend -> SendGrid, or adding a new scraper source,
never requires touching unrelated files.

## Setup

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env
# fill in .env: ANTHROPIC_API_KEY, RESEND_API_KEY, EMAIL_FROM, EMAIL_TO
```

Get keys:
- Anthropic API key: console.anthropic.com
- Resend API key: resend.com (free tier, verify a sending domain or use their test domain)

## Run once (manual test)

```bash
python main.py
```

## Run on a daily schedule (keeps process alive)

```bash
python scheduler.py
```

Change `DAILY_RUN_HOUR_UTC` in `scheduler.py` to your preferred send time.

## Run via cron instead (if deploying to a server with cron access)

```bash
# crontab -e
0 8 * * * cd /path/to/github-digest && /usr/bin/python3 main.py >> logs/cron.log 2>&1
```

## How dedup & idempotency work

- `storage/db.py` keeps a unique `(source, url)` constraint — a repo already
  seen is never re-summarized or re-emailed, even if scraped again.
- `digest_log` table ensures only ONE email is sent per day per recipient,
  even if `main.py` is accidentally run twice the same day.

## Adding a new source later (e.g. Hacker News)

1. Create `scrapers/hacker_news.py`, subclass `BaseScraper`, implement `fetch()`
   returning `List[RawItem]` — same shape as `github_trending.py`.
2. In `main.py`, instantiate it alongside the GitHub scraper and merge results
   before passing to `save_items()`.
3. No changes needed to storage, summarizer, or mailer — they're source-agnostic.

## Next steps toward production (see conversation for full roadmap)

- Swap SQLite -> PostgreSQL once adding multiple sources/users
- Add Celery + Redis if scraping multiple sources sequentially becomes slow
- Add Sentry for error tracking
- Add multi-user support (user table, per-user preferences, unsubscribe links)
- Containerize with Docker, deploy to Railway/Render
