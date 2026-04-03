# Docker Quick Reference

## 🚀 Get Started in 3 Steps

### 1. Configure Environment
```bash
cp .env.docker.example .env
# Edit .env with your API keys and credentials
```

### 2. Build & Run
```bash
make build-all
make up
```

### 3. Access Web UI
Open http://localhost:8000

## 📋 Common Commands

### Start/Stop Services
```bash
make up              # Start web + bot
make up-web          # Start web only
make up-bot          # Start bot only
make down            # Stop all services
```

### View Logs
```bash
make logs            # All services
make logs-web        # Web only
make logs-bot        # Bot only
```

### CLI Operations
```bash
make agent           # Interactive CLI in Docker
make agent-offline   # Offline mode in Docker
docker compose run --rm -T agent --stdin < query.json  # Stdin input
```

### Development
```bash
make dev-up          # Start with code mounting (live reload)
make dev-logs        # View dev logs
make dev-down        # Stop dev services
```

### Local Python (No Docker)
```bash
make dev-install     # Install dependencies
make run             # Run CLI locally
make test            # Run tests
```

## 🏗️ Docker Images

| Image | Purpose | Size | Use Case |
|-------|---------|------|----------|
| `Dockerfile` | Main CLI | ~500MB | General purpose |
| `Dockerfile.web` | Web Server | ~600MB | Web UI + API |
| `Dockerfile.agent` | CLI Agent | ~400MB | Lightweight CLI |
| `Dockerfile.bot` | Bot | ~500MB | Continuous monitoring |

## 🔧 Environment Variables (Required)

**Minimum configuration in `.env`:**
```bash
LLM_API_KEY=your_api_key
LLM_API_BASE_URL=https://api.openai.com/v1
IMAGE_ANALYSIS_MODEL=gpt-4o-mini
ANALYSIS_MODEL=gpt-4o-mini
TWITTER_BEARER_TOKEN=your_token  # or other platform
```

## 🌐 Services & Ports

| Service | Port | Access |
|---------|------|--------|
| Web | 8000 | http://localhost:8000 |
| Bot | - | Discord/Telegram commands |
| CLI | - | `make agent` |

## 📦 Volumes

All services share:
- `./data:/app/data` - Cache, media, outputs
- `./logs:/app/logs` - Application logs

## 🛠️ Troubleshooting

**Container won't start?**
```bash
make logs  # Check logs
# Verify .env exists and is configured
# Check port 8000 is not in use
```

**Permission issues?**
```bash
sudo chown -R 1000:1000 ./data ./logs
```

**Out of disk space?**
```bash
make clean
make prune
```

## 📚 Documentation

- **Full Docker Guide:** [DOCKER.md](DOCKER.md)
- **Setup Summary:** [DOCKER_SETUP_SUMMARY.md](DOCKER_SETUP_SUMMARY.md)
- **Main README:** [README.md](README.md)

## 🎯 Quick Examples

### Run Analysis via Web UI
1. Open http://localhost:8000
2. Fill in platforms, targets, and query
3. Click "Run Analysis"

### Run Analysis via API
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "platforms": {"twitter": ["nasa"]},
    "query": "What are their recent activities?"
  }'
```

### Run Analysis via CLI (Docker)
```bash
make agent
# Follow interactive prompts
```

### Run Analysis via CLI (Local)
```bash
make run
# Follow interactive prompts
```

### Set Up Monitoring
```bash
# Start bot service
make up-bot

# In Discord/Telegram:
/monitor twitter/nasa for keywords "space, launch, mars"
```

## 🔒 Security Tips

1. ✅ Never commit `.env` to git
2. ✅ Use non-root users (already configured)
3. ✅ Enable HTTPS in production
4. ✅ Regularly update images
5. ✅ Scan images: `docker scan osint-web`

## 📝 Development Workflow

**Local Python Development:**
```bash
make dev-install
make run
# Make changes and test
```

**Docker Development:**
```bash
make dev-up      # Start with code mounting
# Make changes - auto-reload
make dev-down    # Stop when done
```

**Production Deployment:**
```bash
make build-all
make up
# Verify: http://localhost:8000
```

## 🆘 Need Help?

- Check logs: `make logs`
- Verify env vars: `cat .env`
- Test locally: `make run`
- Read docs: [DOCKER.md](DOCKER.md)
