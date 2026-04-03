# Docker Setup & Usage

This guide covers how to run OSINT Relay using Docker for both development and production deployments.

## Quick Start

### Prerequisites

- Docker installed (version 20.10 or later)
- Docker Compose installed (version 2.0 or later)

### Setup

1. **Copy environment configuration:**

```bash
cp .env.docker.example .env
```

2. **Edit `.env` with your credentials:**

```bash
nano .env  # or your preferred editor
```

Required minimum configuration:
- `LLM_API_KEY` - Your LLM provider API key
- `LLM_API_BASE_URL` - Your LLM API endpoint
- At least one platform credential (Twitter, Reddit, Bluesky, etc.)

3. **Build and start services:**

```bash
make build-all
make up
```

4. **Access the web interface:**

Open your browser to: `http://localhost:8000`

## Services

OSINT Relay provides three main Docker services:

### 1. Web Server (`web`)

- **Purpose:** Interactive web UI and REST API
- **Port:** 8000
- **Access:** http://localhost:8000
- **Features:**
  - Web-based analysis form
  - REST API endpoints
  - Real-time status updates
  - Health checks

### 2. Bot Service (`bot`)

- **Purpose:** Continuous monitoring via Discord/Telegram
- **Access:** Bot commands in Discord/Telegram
- **Features:**
  - Keyword monitoring
  - Continuous polling
  - Alert notifications
  - Automatic restart on failure

### 3. CLI Agent (`agent`)

- **Purpose:** One-off analyses from command line
- **Access:** Docker compose run
- **Features:**
  - Interactive CLI mode
  - JSON/Markdown output
  - Offline mode support
  - Stdin input support

## Docker Commands

### Using Make (Recommended)

The `Makefile` provides convenient commands for common operations:

```bash
# Build all images
make build-all

# Start web and bot services
make up

# Start only web service
make up-web

# Start only bot service
make up-bot

# Stop all services
make down

# View logs
make logs          # All services
make logs-web      # Web service only
make logs-bot      # Bot service only

# Run CLI agent
make agent         # Interactive
make agent-offline # Offline mode

# Open shell in web container
make shell

# Clean up
make clean
make prune
```

### Using Docker Compose Directly

```bash
# Build images
docker compose build web
docker compose build bot
docker compose build agent

# Start services
docker compose up -d web bot

# Stop services
docker compose down

# View logs
docker compose logs -f
docker compose logs -f web
docker compose logs -f bot

# Run CLI agent
docker compose run --rm -it agent
docker compose run --rm -it agent --offline
docker compose run --rm -T agent --stdin < query.json

# Execute commands in container
docker compose exec web bash
docker compose exec bot python -m socialosintagent.main --help
```

## Local Development

### Running Without Docker

For local development, you can run the application directly with Python:

```bash
# Install dependencies
make dev-install

# Run CLI
make run
make run-offline

# Run tests
make test

# Run linting
make lint
```

### Local Development with Docker

For development with Docker, use volume mounts to sync code changes:

```bash
# Start web with code mounted
docker compose -f docker-compose.dev.yml up -d web
```

The `docker-compose.dev.yml` file (create if needed) should mount the source code:

```yaml
services:
  web:
    volumes:
      - ./socialosintagent:/app/socialosintagent
      - ./static:/app/static
```

## Configuration

### Environment Variables

All configuration is done via environment variables in `.env`:

**Required:**
- `LLM_API_KEY` - LLM provider API key
- `LLM_API_BASE_URL` - LLM API endpoint
- `IMAGE_ANALYSIS_MODEL` - Vision model name
- `ANALYSIS_MODEL` - Text model name

**Platform Credentials (at least one):**
- `TWITTER_BEARER_TOKEN` - Twitter API access
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` - Reddit API access
- `BLUESKY_IDENTIFIER`, `BLUESKY_PASSWORD` - Bluesky API access
- `MASTODON_ACCESS_TOKENS` - Mastodon API access

**Optional:**
- `OSINT_WATCH_INTERVAL_SECONDS` - Monitoring poll interval (default: 300)
- `OSINT_WATCH_FETCH_LIMIT` - Posts to fetch per check (default: 20)
- `UNSAFE_ALLOW_EXTERNAL_MEDIA` - Allow external media downloads (default: false)

### Volumes

The following volumes are mounted for data persistence:

- `./data:/app/data` - Cache, media, outputs, sessions
- `./logs:/app/logs` - Application logs
- `./static:/app/static` - Web frontend assets

## REST API

The web server exposes a REST API for programmatic access:

### POST /api/analyze

Run an OSINT analysis.

**Request:**
```json
{
  "platforms": {
    "twitter": ["username1", "username2"],
    "reddit": ["username1"]
  },
  "query": "What are their primary interests?",
  "fetch_options": {
    "default_count": 50
  }
}
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

## Troubleshooting

### Container Won't Start

1. Check logs: `make logs`
2. Verify `.env` file exists and is properly configured
3. Ensure no port conflicts (port 8000)
4. Check Docker is running: `docker ps`

### Permission Issues

If you encounter permission errors with volumes:

```bash
# Fix data directory permissions
sudo chown -R 1000:1000 ./data ./logs
```

### Out of Disk Space

Clean up Docker resources:

```bash
make clean    # Stop and remove containers
make prune    # Remove unused images and volumes
```

### Bot Not Responding

1. Check bot logs: `make logs-bot`
2. Verify bot tokens in `.env`
3. Ensure bot has proper permissions in Discord/Telegram
4. Check for rate limiting errors

### Analysis Fails

1. Check LLM API credentials
2. Verify platform credentials are valid
3. Check for rate limiting on platform APIs
4. Review logs for specific error messages

## Production Deployment

### Security Considerations

1. **Never commit `.env` to version control**
2. Use secrets management for sensitive credentials
3. Enable HTTPS/TLS for web interface
4. Restrict network access with Docker networks
5. Regularly update base images

### Resource Limits

Add resource limits to `docker-compose.yml`:

```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### Reverse Proxy

Use nginx or traefik as a reverse proxy:

```nginx
server {
    listen 80;
    server_name osint.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Monitoring

Consider adding:

- Prometheus metrics endpoint
- Log aggregation (ELK, Loki)
- Container health checks
- Alerting on failures

## Advanced Usage

### Custom Networks

Create isolated networks for security:

```yaml
networks:
  osint-net:
    driver: bridge
    internal: true  # No internet access (except via proxy)
```

### Multi-Stage Builds

Optimize image sizes with multi-stage builds (already implemented in Dockerfiles):

```dockerfile
# Build stage
FROM python:3.11-slim as builder
# ... build steps ...

# Runtime stage
FROM python:3.11-slim
COPY --from=builder /app /app
# ... runtime configuration ...
```

### Custom Entrypoints

Override default commands:

```bash
docker compose run --rm agent --offline --log-level DEBUG
```

## Support

For issues, questions, or contributions:

- Check existing issues on GitHub
- Review logs for error details
- Verify all environment variables are set correctly
- Ensure all platform credentials are valid
