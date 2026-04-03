# OSINT Relay - Low Level Process Flow

```mermaid
graph TD
    subgraph User_Layer["User Interaction Layer"]
        CMD[Command] -->|telegram/discord| CHAT{Platform}
        CHAT -->|/analyze| ANA[Analyze Request]
        CHAT -->|/monitor| MON[Monitor Request]
        CHAT -->|/refresh| REF[Refresh Request]
        CHAT -->|/contacts| CON[Contacts Request]
    end

    subgraph Bot_Handler["Bot Handler Layer"]
        BOT[Bot Handler] --> PARSE[Parse Command]
        PARSE -->|platform/username| EXTRACT[Extract Target]
        PARSE -->|keywords| MONKEY[Extract Keywords]
        EXTRACT --> CHECK_CACHE{Cache Fresh?}
        CHECK_CACHE -->|yes| LOAD_CACHE[Load from Cache]
        CHECK_CACHE -->|no/stale| FETCH_NEW[Fetch New Data]
        LOAD_CACHE --> ANALYZE
        FETCH_NEW --> FETCH
    end

    subgraph Fetch_Layer["Platform Fetch Layer"]
        FETCH[Client Manager] -->|twitter| TW[Twitter Fetcher]
        FETCH -->|reddit| RD[Reddit Fetcher]
        FETCH -->|bluesky| BS[Bluesky Fetcher]
        FETCH -->|github| GH[GitHub Fetcher]
        FETCH -->|hackernews| HN[HackerNews Fetcher]
        FETCH -->|mastodon| MD[Mastodon Fetcher]
        
        TW --> NORM[Normalize Posts]
        RD --> NORM
        BS --> NORM
        GH --> NORM
        HN --> NORM
        MD --> NORM
        
        NORM --> HAS_IMG{Has Images?}
        HAS_IMG -->|yes| IMG_PROC[Image Processor]
        HAS_IMG -->|no| SECURE
        IMG_PROC --> SECURE
    end

    subgraph Security_Layer["Security Layer"]
        SECURE[XML Wrapper] --> ESC[Escape UGC]
        ESC --> INJECT_SCAN{Injection?}
        INJECT_SCAN -->|detected| QUARANTINE[Quarantine Post]
        INJECT_SCAN -->|clean| SAVE_CACHE[Save to Cache]
        QUARANTINE --> WARN[Warn Operator]
        SAVE_CACHE --> ANALYZE
    end

    subgraph LLM_Layer["LLM Processing Layer"]
        ANALYZE[Analyzer] --> MODEL_TYPE{Model Type}
        MODEL_TYPE -->|triage| TRIAGE[Triage Model]
        MODEL_TYPE -->|synthesis| SYNTH[Synthesis Model]
        
        TRIAGE --> TRIAGE_EVAL{Keywords Match?}
        TRIAGE_EVAL -->|yes| ALERT[Generate Alert]
        TRIAGE_EVAL -->|no| SILENT[Silent Skip]
        
        SYNTH --> PROCESS[Process Posts]
        PROCESS --> VISION{Has Vision?}
        VISION -->|yes| VISION_LLM[Vision Model]
        VISION -->|no| REPORT_GEN
        VISION_LLM --> REPORT_GEN[Generate Report]
        REPORT_GEN --> FORMAT[Format Markdown]
    end

    subgraph Response_Layer["Response Layer"]
        FORMAT --> RESP[Send Response]
        ALERT --> RESP
        RESP -->|chat| CHAT_REPLY[Reply to Chat]
        SILENT --> NO_ACTION[No Action]
    end

    subgraph Watcher_Layer["Background Watcher"]
        SCHEDULER[Async Scheduler] --> WAKE[Wake Every X Sec]
        WAKE --> GET_MON[Get Active Monitors]
        GET_MON --> FOR_EACH[For Each Monitor]
        FOR_EACH --> W_FETCH[Fetch New Posts]
        W_FETCH --> W_TRIAGE[Run Triage LLM]
        W_TRIAGE --> W_MATCH{Match?}
        W_MATCH -->|yes| W_ALERT[Send Alert]
        W_MATCH -->|no| W_SKIP[Skip]
    end

    MON --> SETUP[Create Monitor Rule]
    SETUP --> SESSION[Save to Session]
    SESSION --> MONITORS[Active Monitors]
    MONITORS --> WAKE

    ANA --> BOT
    REF --> BOT
    CON --> BOT
    WARN --> CHAT_REPLY
```

## Data Flow Description

### 1. Command Entry
- User sends command via Telegram (`/analyze`) or Discord (`?analyze`)
- Bot handler receives and parses the command
- Extracts platform, username, and optional query/keywords

### 2. Cache Check
- Check if target data exists in `data/cache/`
- Verify cache freshness (24-hour TTL by default)
- If fresh: load and proceed to analysis
- If stale/missing: fetch new data

### 3. Data Fetching
- Client Manager routes to appropriate platform fetcher
- Fetcher calls platform API (with rate limiting)
- Posts normalized to `NormalizedPost` format
- Images downloaded to `data/media/`

### 4. Security Processing
- User-Generated Content (UGC) wrapped in XML tags
- All content XML-escaped to prevent injection
- Pattern scan for prompt injection attempts
- Injected content quarantined, operator warned
- Clean content saved to cache

### 5. LLM Analysis
- **Triage Mode** (monitoring): Fast/cheap model evaluates keyword matches
- **Synthesis Mode** (analysis): Heavy model generates full report
- Vision model analyzes images if present
- Results formatted as Markdown

### 6. Response Delivery
- Report/alert sent back to chat platform
- For monitoring: only alerts on keyword matches
- For analysis: full intelligence report

### 7. Background Watcher
- Runs on `asyncio` loop every `OSINT_WATCH_INTERVAL_SECONDS` (default: 300s)
- Iterates through active monitoring rules from `data/sessions/`
- Fetches only new posts (after last check timestamp)
- Uses triage model to evaluate keyword matches
- Sends alerts to user's chat on matches
- Silent on no-match to reduce noise

## Key Files Involved

- `bot.py` - Main daemon entrypoint
- `telegram_handler.py` / `discord_handler.py` - Chat interface
- `watcher.py` - Background scheduler
- `analyzer.py` - Analysis orchestration
- `llm.py` - LLM client with router pattern
- `client_manager.py` - Platform client factory
- `platforms/*.py` - Per-platform fetchers
- `cache.py` - File-based cache manager
- `session_manager.py` - Session & monitor persistence
- `image_processor.py` - Image download & preprocessing
