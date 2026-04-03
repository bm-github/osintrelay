# Docker Setup Summary

## Overview

OSINT Relay now includes comprehensive Docker support for both production deployments and local development. The setup includes:

- **3 Docker images**: Web server, CLI agent, and Bot
- **3 Docker Compose files**: Production, development, and profiles
- **1 Makefile**: Convenient commands for all operations
- **1 Web UI**: Interactive analysis interface
- **Complete documentation**: DOCKER.md with detailed usage instructions

## File Structure

```
.
├── Dockerfile                  # Main CLI image
├── Dockerfile.web              # Web server image
├── Dockerfile.agent            # Lightweight CLI image
├── Dockerfile.bot              # Bot image
├── docker-compose.yml          # Production services
├── docker-compose.dev.yml      # Development services (with code mounting)
├── Makefile                    # Convenience commands
├── .env.docker.example         # Docker environment template
├── .dockerignore               # Docker build exclusions
├── static/
│   └── index.html             # Web UI frontend
├── query.json.example         # Example stdin input
└── DOCKER.md                  # Complete Docker documentation
```

## Quick Start Commands

### Production

```bash
# Setup
cp .env.docker.example .env
# Edit .env with your credentials

# Build and run
make build-all
make up

# Access web UI at http://localhost:8000
```

### Development

```bash
# Local Python development
make dev-install
make run

# Docker development with live reload
make dev-up
make dev-logs
make dev-down
```

## Docker Services

### 1. Web Server (`web`)

**Purpose:** Interactive web UI and REST API

**Features:**
- Web-based analysis form
- REST API endpoints (`/api/analyze`, `/health`)
- Real-time status updates
- Health checks

**Access:** http://localhost:8000

**Commands:**
```bash
make up-web              # Start
make logs-web            # View logs
docker compose exec web bash  # Shell access
```

### 2. Bot Service (`bot`)

**Purpose:** Continuous monitoring via Discord/Telegram

**Features:**
- Keyword monitoring
- Continuous polling
- Alert notifications
- Automatic restart

**Access:** Bot commands in Discord/Telegram

**Commands:**
```bash
make up-bot              # Start
make logs-bot            # View logs
```

### 3. CLI Agent (`agent`)

**Purpose:** One-off analyses from command line

**Features:**
- Interactive CLI mode
- JSON/Markdown output
- Offline mode support
- Stdin input support

**Commands:**
```bash
make agent               # Interactive
make agent-offline       # Offline mode
docker compose run --rm -T agent --stdin < query.json
```

## Makefile Commands

### Local Development
- `make install` - Install production dependencies
- `make dev-install` - Install development dependencies
- `make run` - Run CLI locally
- `make run-offline` - Run CLI locally in offline mode
- `make test` - Run tests
- `make lint` - Run linting

### Docker Build
- `make build-all` - Build all Docker images
- `make build-web` - Build web server image
- `make build-agent` - Build CLI agent image
- `make build-bot` - Build bot image

### Docker Services
- `make up` - Start web and bot services
- `make up-web` - Start web service only
- `make up-bot` - Start bot service only
- `make down` - Stop all services
- `make logs` - View logs from all services
- `make logs-web` - View web service logs
- `make logs-bot` - View bot service logs

### Docker Development
- `make dev-up` - Start dev services with code mounting
- `make dev-down` - Stop dev services
- `make dev-logs` - View dev service logs

### Docker CLI
- `make agent` - Run CLI agent in Docker (interactive)
- `make agent-offline` - Run CLI agent in Docker (offline)
- `make shell` - Open shell in web container

### Maintenance
- `make clean` - Clean Docker resources
- `make prune` - Prune all Docker resources

## Docker Images

All images are based on `python:3.11-slim` and include:

### Common Features
- Non-root user (appuser:1000)
- Minimal system dependencies (libmagic1, curl)
- Optimized layer caching
- Security hardening
- Proper directory permissions

### Dockerfile (Main)
- Full CLI and bot capabilities
- Both interactive and stdin modes
- Default: `python -m socialosintagent.main`

### Dockerfile.web
- Web server + FastAPI + Uvicorn
- Static frontend assets
- Health checks
- Exposes port 8000

### Dockerfile.agent
- CLI-only (lightweight)
- No web server or bot code
- Optimized for one-off analyses

### Dockerfile.bot
- Bot-only
- Discord and Telegram support
- Continuous monitoring
- Auto-restart on failure

## Volumes

All services share these volumes:

- `./data:/app/data` - Cache, media, outputs, sessions
- `./logs:/app/logs` - Application logs
- `./static:/app/static` - Web frontend (web service only)

## Environment Configuration

Required environment variables (in `.env`):

**LLM Configuration:**
- `LLM_API_KEY` - Your LLM provider API key
- `LLM_API_BASE_URL` - LLM API endpoint
- `IMAGE_ANALYSIS_MODEL` - Vision model name
- `ANALYSIS_MODEL` - Text model name
- `TRIAGE_MODEL` - Triage model name (optional)

**Platform Credentials (at least one):**
- `TWITTER_BEARER_TOKEN` - Twitter API access
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` - Reddit API access
- `BLUESKY_IDENTIFIER`, `BLUESKY_PASSWORD` - Bluesky API access
- `DISCORD_BOT_TOKEN` - Discord bot token
- `TELEGRAM_BOT_TOKEN` - Telegram bot token

**Optional:**
- `OSINT_WATCH_INTERVAL_SECONDS` - Monitoring poll interval (default: 300)
- `OSINT_WATCH_FETCH_LIMIT` - Posts to fetch per check (default: 20)
- `UNSAFE_ALLOW_EXTERNAL_MEDIA` - Allow external media downloads (default: false)

## REST API

### POST /api/analyze

Run an OSINT analysis.

**Example Request:**
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "platforms": {
      "twitter": ["username1"],
      "reddit": ["username1"]
    },
    "query": "What are their primary interests?",
    "fetch_options": {
      "default_count": 50
    }
  }'
```

**Response:**
```json
{
  "metadata": {
    "query": "...",
    "targets": {...},
    "generated_utc": "...",
    "mode": "Online",
    "models": {...},
    "fetch_stats": {...},
    "vision_stats": {...}
  },
  "report": "...",
  "entities": {
    "locations": [],
    "emails": [],
    "phones": [],
    "crypto": [],
    "aliases": []
  },
  "error": false
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Development Workflow

### Local Python Development

```bash
# 1. Install dependencies
make dev-install

# 2. Run CLI locally
make run

# 3. Run tests
make test

# 4. Check code
make lint
```

### Docker Development with Live Reload

```bash
# 1. Start dev services
make dev-up

# 2. View logs
make dev-logs

# 3. Make code changes - they auto-reload

# 4. Stop when done
make dev-down
```

### Production Deployment

```bash
# 1. Build images
make build-all

# 2. Start services
make up

# 3. Check status
make logs

# 4. Access web UI
open http://localhost:8000
```

## Security Best Practices

1. **Never commit `.env` to version control**
2. Use secrets management for production credentials
3. Enable HTTPS/TLS for web interface
4. Restrict network access with Docker networks
5. Regularly update base images
6. Use non-root users (already implemented)
7. Scan images for vulnerabilities: `docker scan osint-web`

## Troubleshooting

### Container Won't Start

1. Check logs: `make logs`
2. Verify `.env` file exists and is properly configured
3. Ensure no port conflicts (port 8000)
4. Check Docker is running: `docker ps`

### Permission Issues

```bash
sudo chown -R 1000:1000 ./data ./logs
```

### Out of Disk Space

```bash
make clean
make prune
```

## Next Steps

1. Review [DOCKER.md](DOCKER.md) for detailed documentation
2. Test the web UI at http://localhost:8000
3. Set up Discord/Telegram bot for monitoring
4. Configure platform credentials in `.env`
5. Try the CLI agent: `make agent`

## Support

For issues or questions:
- Check [DOCKER.md](DOCKER.md) for detailed documentation
- Review logs for error details
- Verify all environment variables are set correctly
- Ensure all platform credentials are valid
