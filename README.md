# OSINT Relay

**OSINT Relay** is a sandboxed, read-only ChatOps OSINT agent. It gathers public activity across social platforms, synthesizes Markdown intelligence reports via an OpenAI-compatible LLM API, and delivers them directly to your **Telegram** or **Discord** chat — with optional continuous monitoring that alerts you when keyword conditions are met.

Built on the [OWASP Social OSINT Agent](https://github.com/bm-github/owasp-social-osint-agent) engine, it retains all upstream security hardening (XML-wrapped UGC, prompt injection detection, multi-layer sanitization) while adding a ChatOps-first interface and background watcher.

## Features

- **Multi-platform ChatOps** — Run analyses and set up monitors from Telegram and/or Discord. Both bots can run simultaneously in the same process.
- **Continuous monitoring (Watcher)** — Set keyword-based monitoring rules with `/monitor`. A background loop periodically fetches new posts and alerts you only on matches.
- **Multi-model LLM routing** — Cheap triage model for monitoring evaluations (`TRIAGE_MODEL`), heavyweight synthesis model (`ANALYSIS_MODEL`) for full reports.
- **7 platforms** — Twitter/X, Reddit, Bluesky, GitHub, Hacker News, Mastodon. Normalized posts, caching, rate-limit handling, and optional image analysis.
- **Vision analysis** — Downloaded images are analyzed by a vision-capable LLM; descriptions are bound to their parent posts as atomic evidence units.
- **Security-hardened prompts** — Untrusted social content is XML-escaped, line-delimited, and injection-scanned at multiple layers. Injected posts are quarantined and reported to the operator.
- **Read-only by design** — Fetches public data and sends replies to your chat. Never posts to social platforms or interacts with targets.
- **Web UI & CLI** — Optional FastAPI web interface (sessions, SSE progress, contacts, timeline, cache manager) and Rich-based interactive CLI with `--stdin` JSON batch mode.

## Quick start

### Prerequisites

- **Python 3.11+**
- API keys for an OpenAI-compatible LLM and any platforms you want to use

### 1. Clone

```bash
git clone https://github.com/bm-github/osintrelay && cd osintrelay
```

### 2. Virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt          # Core + ChatOps (Telegram, Discord)
pip install -r requirements-web.txt      # Optional: web UI
pip install -r requirements-dev.txt      # Optional: test suite
```

### 4. Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Minimal configuration (see `.env.example` for all options):

```dotenv
# ChatOps — set one or both
TELEGRAM_BOT_TOKEN="your_telegram_token"
DISCORD_BOT_TOKEN="your_discord_token"

# LLM (required)
LLM_API_KEY="your_api_key"
LLM_API_BASE_URL="https://api.example.com/v1"
ANALYSIS_MODEL="gpt-4o"
IMAGE_ANALYSIS_MODEL="gpt-4o-mini"

# Optional: cheaper model for monitoring triage
TRIAGE_MODEL="gpt-4o-mini"

# Platforms (as needed)
TWITTER_BEARER_TOKEN="..."
REDDIT_CLIENT_ID="..."
REDDIT_CLIENT_SECRET="..."
BLUESKY_IDENTIFIER="handle.bsky.social"
BLUESKY_APP_SECRET="..."
GITHUB_TOKEN="..."
MASTODON_INSTANCE_1_URL="https://mastodon.social"
MASTODON_INSTANCE_1_TOKEN="..."

# Security: Media Download Restrictions
# By default, only trusted CDNs are allowed. Override with additional domains:
# EXTRA_TWITTER_CDNS="custom.cdn.example.com"
# EXTRA_REDDIT_CDNS="i.imgur.com,custom.cdn2.com"
# EXTRA_BLUESKY_CDNS="custom.bsky.cdn.com"
# EXTRA_MASTODON_CDNS="media.myinstance.org"
```

Hacker News needs no API key. GitHub works with limited anonymous access; a token is recommended.

### 5. Run

**Bot daemon (recommended):**

```bash
python -m socialosintagent.bot
```

Auto-detects which tokens are set and starts the appropriate bot(s) with the background watcher. Logs go to `logs/` and stderr.

**Telegram only:**

```bash
python -m socialosintagent.telegram_handler
```

**Discord only:**

```bash
python -m socialosintagent.discord_handler
```

**Web UI:**

```bash
uvicorn socialosintagent.web_server:app --host 127.0.0.1 --port 8000 --reload
```

**Interactive CLI:**

```bash
python -m socialosintagent.main
```

**Stdin JSON (non-interactive):**

```bash
echo '{
  "platforms": { "hackernews": ["pg"] },
  "query": "Summarize recent activity themes."
}' | python -m socialosintagent.main --stdin --no-auto-save
```

### 6. Docker

```bash
docker compose up --build
```

Runs the bot as a continuous daemon. Data persists in `./data/` via bind mount.

### 7. Discord bot setup

#### Create a Discord application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application**, give it a name (e.g. "OSINT Relay")
3. Go to **Bot** in the left sidebar
4. Click **Reset Token** (or **Copy Token**) and save it — this is your `DISCORD_BOT_TOKEN`
5. Under **Privileged Gateway Intents**, enable **Message Content Intent** (required for the bot to read commands)

#### Invite the bot to your server

1. Go to **OAuth2 → URL Generator**
2. Select scopes: `bot`
3. Select bot permissions: `Send Messages`, `Read Message History`, `Embed Links` (or use `Administrator` for simplicity in a private server)
4. Copy the generated URL and open it in your browser
5. Select the server you want to add the bot to and authorize

#### Configure and run

Add the token to your `.env`:

```dotenv
DISCORD_BOT_TOKEN="your_bot_token_here"
```

Then start the bot:

```bash
python -m socialosintagent.bot          # starts all configured bots + watcher
# or
python -m socialosintagent.discord_handler  # Discord only
```

#### Available Discord commands

| Command | Description |
|---------|-------------|
| `?help` | Show usage instructions |
| `?analyze <platform>/<username>` | Run OSINT analysis with default query |
| `?analyze <platform>/<username> <query>` | Run analysis with a custom query |
| `?refresh <platform>/<username>` | Force cache refresh + analyze |
| `?contacts <platform>/<username>` | Extract network contacts |
| `?monitor <platform>/<username> for keywords "word1, word2"` | Start continuous monitoring |
| `?listmonitors` | List active monitoring rules |
| `?stopmonitor <rule_id>` | Stop a monitoring rule |
| `?status` | Bot health and platform status |
| `?sessions` | List active sessions |

**Examples:**

```
?analyze twitter/nasa
?analyze github/torvalds
?monitor bluesky/nasa for keywords "mars, rocket"
?refresh reddit/opensource
```

## Chat commands

### Telegram commands

| Command | Description |
|---------|-------------|
| `/help` | Usage instructions |
| `/analyze <platform>/<username>` | Run an OSINT analysis and reply with the Markdown report |
| `/monitor <platform>/<username> for keywords "word1, word2"` | Start continuous monitoring; alerts on keyword matches |
| `/monitor_discord <platform>/<username> for keywords "..." webhook "..."` | Forward alerts to a Discord webhook |

**Mastodon:** Use only the first `/` as separator: `/analyze mastodon/user@instance.social`

**Examples:**

```
/analyze twitter/nasa
/analyze github/torvalds
/monitor bluesky/nasa for keywords "mars, rocket"
```

### Discord commands

| Command | Description |
|---------|-------------|
| `?help` | Usage instructions |
| `?analyze <platform>/<username>` | Run an OSINT analysis and reply with the Markdown report |
| `?analyze <platform>/<username> <query>` | Run analysis with a custom query |
| `?refresh <platform>/<username>` | Force cache refresh + analyze |
| `?contacts <platform>/<username>` | Extract network contacts |
| `?monitor <platform>/<username> for keywords "word1, word2"` | Start continuous monitoring |
| `?listmonitors` | List active monitoring rules |
| `?stopmonitor <rule_id>` | Stop a monitoring rule |
| `?status` | Bot health and platform status |
| `?sessions` | List active sessions |

**Mastodon:** Use only the first `?` as separator: `?analyze mastodon/user@instance.social`

**Examples:**

```
?analyze twitter/nasa
?analyze github/torvalds
?monitor bluesky/nasa for keywords "mars, rocket"
?refresh reddit/opensource
```

### Monitoring behavior

- The watcher polls every 5 minutes by default (`OSINT_WATCH_INTERVAL_SECONDS`).
- Only **new** posts (after rule creation time) are evaluated.
- A cheap triage model decides if posts match your keywords.
- On match, you receive an alert with matched evidence snippets.
- If prompt injection is detected in monitored posts, the post is quarantined and you receive a warning instead.

### CLI flags

| Flag | Description |
|------|-------------|
| `--stdin` | Read analysis request from stdin as JSON |
| `--format [json\|markdown]` | Output format (default: `markdown`) |
| `--no-auto-save` | Don't save reports to `data/outputs/` |
| `--offline` | Cache-only mode; no live fetches or vision calls |
| `--unsafe-allow-external-media` | Allow media downloads outside default CDNs |
| `--log-level [DEBUG\|INFO\|WARNING\|ERROR\|CRITICAL]` | Default: `WARNING` |

### Interactive session commands

Inside a CLI session: `/loadmore`, `/refresh`, `/add`, `/remove`, `/status`, `/help`, `/exit`

## Supported platforms

| Platform | API key required | Notes |
|----------|-----------------|-------|
| Twitter/X | `TWITTER_BEARER_TOKEN` | Full tweet history, metrics |
| Reddit | `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | Posts and comments |
| Bluesky | `BLUESKY_IDENTIFIER` + `BLUESKY_APP_SECRET` | AT Protocol |
| GitHub | `GITHUB_TOKEN` (optional) | Repos, events, org activity |
| Hacker News | None | Algolia search API |
| Mastodon | Per-instance token | Multiple instances supported |

## Architecture

```
socialosintagent/
├── bot.py                 # Daemon entrypoint — starts bot(s) + watcher
├── telegram_handler.py    # Telegram ChatOps (aiogram)
├── discord_handler.py     # Discord ChatOps (discord.py)
├── watcher.py             # Background monitoring loop
├── analyzer.py            # Headless analysis engine (no Rich coupling)
├── llm.py                 # LLM client, triage/synthesis routers, injection detection
├── cache.py               # File-based cache manager
├── session_manager.py     # Session persistence + monitoring rules
├── client_manager.py      # Platform API client factory
├── image_processor.py     # Resilient image download + preprocessing
├── network_extractor.py   # Deterministic contact/relationship extraction
├── platforms/             # Per-platform fetchers
│   ├── base_fetcher.py
│   ├── twitter.py
│   ├── reddit.py
│   ├── bluesky.py
│   ├── github.py
│   ├── hackernews.py
│   └── mastodon.py
├── prompts/               # Externalized LLM prompt templates
│   ├── system_analysis.prompt
│   └── image_analysis.prompt
├── web_server.py          # FastAPI web interface
├── cli_handler.py         # Rich interactive CLI
└── main.py                # CLI entrypoint
```

## Data layout

```
data/
├── cache/       # JSON per target (24-hour freshness)
├── media/       # Downloaded images; vision results written back into cache
├── outputs/     # Saved reports (when auto-save is enabled)
└── sessions/    # Session state + monitoring rules
```

Web UI, CLI, and the bot all share the same `data/` directory.

## Security

- **`.env` is git-ignored** — rotate tokens immediately if exposed.
- **XML structural delimiting** — all untrusted content is wrapped in XML tags and escaped to prevent indirect prompt injection.
- **Injection detection** — both input (UGC) and output (LLM responses) are scanned against pattern sets; flagged content is quarantined.
- **Defense-in-depth** — XML escaping, line-prefixing (`UGC:` delimiter), and pattern scanning operate as independent layers.
- **Read-only** — the agent fetches data and sends messages to your chat; it cannot post to platforms or interact with targets.
- **Watcher quarantine** — monitoring rules that encounter injected content refuse to invoke the heavy synthesis model and alert the operator instead.
- Restrict who can message your Telegram bot (privacy settings) or Discord server for sensitive deployments.
- Treat `data/` as sensitive.
- Respect each platform's Terms of Service and your LLM provider's policies.

## REST API (web server)

When the web server is running, a versioned REST API is available at `/api/v1/`. Interactive docs at `/api/docs` (Swagger) and `/api/redoc`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/platforms` | List configured platforms and availability |
| `GET` | `/api/v1/sessions` | List sessions (summaries) |
| `POST` | `/api/v1/sessions` | Create a session |
| `GET` | `/api/v1/sessions/{id}` | Full session with query history |
| `DELETE` | `/api/v1/sessions/{id}` | Delete a session |
| `PATCH` | `/api/v1/sessions/{id}/rename` | Rename a session |
| `PUT` | `/api/v1/sessions/{id}/targets` | Replace session targets |
| `POST` | `/api/v1/sessions/{id}/analyse` | Start analysis job (returns `job_id`) |
| `GET` | `/api/v1/jobs/{job_id}` | Poll job status |
| `GET` | `/api/v1/jobs/{job_id}/stream` | SSE stream of job progress |
| `GET` | `/api/v1/sessions/{id}/contacts` | Discovered network contacts |
| `POST` | `/api/v1/sessions/{id}/contacts/dismiss` | Dismiss a contact |
| `POST` | `/api/v1/sessions/{id}/contacts/undismiss` | Restore a dismissed contact |
| `GET` | `/api/v1/sessions/{id}/timeline` | Post timestamps for charts |
| `GET` | `/api/v1/sessions/{id}/media` | Media paths and vision analyses |
| `GET` | `/api/v1/sessions/{id}/media/file` | Serve a local media file |
| `GET` | `/api/v1/sessions/{id}/export` | Export full session as JSON |
| `GET` | `/api/v1/cache` | Cache status |
| `POST` | `/api/v1/cache/purge` | Purge cache / media / outputs |

Set `OSINT_WEB_USER` and `OSINT_WEB_PASSWORD` in `.env` for HTTP Basic Auth when exposing beyond localhost.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_API_KEY` | Yes | OpenAI-compatible API key |
| `LLM_API_BASE_URL` | Yes | API base URL |
| `ANALYSIS_MODEL` | Yes | Text synthesis model |
| `IMAGE_ANALYSIS_MODEL` | Yes | Vision model |
| `TRIAGE_MODEL` | No | Cheap model for monitoring triage (falls back to `ANALYSIS_MODEL`) |
| `TELEGRAM_BOT_TOKEN` | One of these | From [@BotFather](https://t.me/BotFather) |
| `DISCORD_BOT_TOKEN` | | From Discord Developer Portal |
| `OSINT_WATCH_INTERVAL_SECONDS` | No | Watcher poll interval (default: `300`) |
| `OSINT_WATCH_FETCH_LIMIT` | No | Posts fetched per poll per target (default: `20`) |
| `OSINT_WATCH_TRIAGE_POST_LIMIT` | No | Max new posts per triage evaluation (default: `8`) |
| `OSINT_WEB_USER` | No | HTTP Basic Auth username |
| `OSINT_WEB_PASSWORD` | No | HTTP Basic Auth password |
| Platform keys | As needed | See `.env.example` |

## Testing

```bash
pip install -r requirements-dev.txt
pytest --tb=short -q tests
```

CI runs on Python 3.11 and 3.12 via GitHub Actions.

## Contributing

Issues and pull requests are welcome. See [spec.md](spec.md) for the full product roadmap and phased implementation plan.
