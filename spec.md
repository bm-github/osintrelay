# Product Specification: OWASP Secure ChatOps OSINT Agent

# Product Specification: OWASP OSINT Relay

## 1. Vision & Context
**Context:** We are migrating our existing, highly-secure OSINT scraper ("OWASP Social OSINT Agent") into a continuous, always-on ChatOps agent named **OSINT Relay**. 
**Motivation:** Modern security teams live in Slack, Discord, and Telegram. Instead of running a CLI tool, users need a secure background agent that they can message to initiate investigations, and which will continuously monitor targets and *relay* intelligence back to their secure chat environment.
**Security Posture:** Unlike generalist code-executing agents, OSINT Relay is a strictly sandboxed, read-only intelligence synthesizer. It retains all of our existing robust XML-tag sandboxing to neutralize Indirect Prompt Injections found in hostile social media data.

## 2. Core Architecture Objectives
*   **ChatOps Primary Interface:** Deprioritize the traditional CLI/Web UI. The primary interface will be an async Chat Bot (e.g., Telegram or Discord) where users can issue natural language commands (e.g., *"Monitor @username on Mastodon and alert me of new cryptocurrency domains"*).
*   **Continuous Monitoring (The Watcher):** Transition from run-and-done executions to continuous background monitoring. The agent must wake up periodically, check target profiles via the existing Fetcher architecture, and push asynchronous alerts to the chat if specific conditions are met.
*   **Targeted Multi-Agent LLM Routing:** 
    *   *Agent 1 (Triage/Fast):* A fast, cheap model (e.g., Claude 3.5 Haiku or Llama 3) scans newly fetched posts to see if they match the user's continuous monitoring query.
    *   *Agent 2 (Synthesis/Heavy):* A high-reasoning model (e.g., GPT-4.5, Claude 3 Opus) is only invoked for full psychological/behavioral workups.
*   **Zero-Trust Data Handling:** We will completely reuse the existing `llm.py` injection detection and XML-escaping logic. The agent acts as a secure relay between hostile data and the user.

## 3. Existing Codebase Reusability & Migration Plan
The existing codebase is highly modular and well-organized. We will reuse ~80% of the core engine.

### 🟢 1. Keep As-Is (Core Engine)
*   **`socialosintagent/platforms/*` & `base_fetcher.py`**: The entire platform fetching ecosystem is perfectly structured. Keep rate-limiting logic, standard normalization (`NormalizedPost`), and caching integration.
*   **`socialosintagent/image_processor.py`**: Keep as-is. Resilient image handling is already production-ready.
*   **`socialosintagent/cache.py`**: Keep as-is. File-based caching is excellent for local containerized instances.
*   **`socialosintagent/network_extractor.py`**: Keep as-is. Deterministic network mapping is highly valuable for the background worker to map target associations.
*   **`socialosintagent/prompts/*`**: Keep the existing XML-based security prompts. 

### 🟡 2. Refactor (AI & Orchestration)
*   **`socialosintagent/llm.py`**: 
    *   *Action:* Refactor to support the **Router Pattern**. Add a `run_triage_evaluation()` method to quickly evaluate if a new post triggers a monitoring alert, saving the `run_analysis()` method for deep dives.
*   **`socialosintagent/analyzer.py`**: 
    *   *Action:* Decouple `Console` (Rich printing) dependencies. The analyzer should return pure structured data/events so the ChatOps handler can format them for messaging apps.
*   **`socialosintagent/session_manager.py`**:
    *   *Action:* Expand sessions to include "Monitoring Rules" (e.g., `{ "session_id": "123", "target": "github/torvalds", "condition": "mentions rust", "alert_channel": "telegram_chat_id" }`).

### 🔴 3. Replace/Deprecate (Interfaces)
*   **`socialosintagent/cli_handler.py` & `web_server.py`**: 
    *   *Action:* Move these to a `legacy/` folder or deprecate entirely.
    *   *Replacement:* Create `socialosintagent/telegram_handler.py` utilizing `aiogram` (for Telegram) or `discord.py`.

### 🟣 4. Net-New Components
*   **`socialosintagent/watcher.py` (The Scheduler)**:
    *   *Action:* Implement an `asyncio` background loop. Every *X* minutes, iterate through active "Monitoring Sessions", invoke the fetchers to look for posts newer than the last cached timestamp, run the Triage LLM, and push alerts to the ChatOps handler.

## 4. Required Tech Stack Additions
*   **Chat Integration:** `aiogram` (Telegram) or `discord.py` (Discord) for the primary interface.
*   **Scheduling:** `APScheduler` or native `asyncio` loops for the background watcher.
*   **Database (Optional Upgrade):** While `cache.py` (JSON files) works well, migrating active "Monitoring Rules" to `sqlite3` may be beneficial for concurrency if the background worker and ChatOps bot run in separate threads.

## 5. Security & Guardrails (Strict Enforcement)
*   **Human-In-The-Loop (HITL):** The agent operates in strict read-only mode. It can fetch data and send messages *to the user's private chat*, but it cannot post to social media or interact with targets.
*   **Injection Quarantine:** If `detect_injection_attempt()` in `llm.py` triggers, the agent must quarantine the post, refuse to run the heavy synthesis model on it, and send a specific warning alert to the ChatOps inbox (e.g., *"⚠️ Prompt Injection attempt detected in target's latest Mastodon post."*)

## 6. Implementation Phases (Google Antigravity Instructions)

*   **Phase 1: Interface Swap.** Scaffold `telegram_handler.py`. Connect it to a Telegram Bot token. Prove that a user can text the bot `/analyze twitter/username` and receive the Markdown report as a chat reply. Remove Rich console dependencies from the execution path.
*   **Phase 2: Multi-Agent Routing.** Update `llm.py` to support `TriageAnalyzer` (cheap model) and `SynthesisAnalyzer` (expensive model). 
*   **Phase 3: Continuous Monitoring.** Implement `watcher.py`. Allow the user to text the bot `/monitor bluesky/username for keywords "crypto, wallet"`. Ensure the background loop runs quietly and only pushes messages to the chat when a match occurs.
*   **Phase 4: Dockerization.** Update `docker-compose.yml` to run the bot as a continuous daemon process (`command: python -m socialosintagent.bot`) rather than a run-and-done task.

## 7. Future Roadmap (Phases 5+)

### Phase 5: Web UI Enhancements

#### High Priority Features
- **Dashboard Overview Page**
  - Active monitors with real-time status indicators
  - Recent alerts and notifications feed
  - Quick statistics (total sessions, cache size, platform health)
  - Activity heatmaps across all sessions

- **Real-time Notifications Panel**
  - Persistent sidebar with live monitoring alerts
  - Job completion notifications
  - System status updates
  - Dismissible with full history

- **Advanced Search & Filter**
  - Search sessions by query content, targets, date ranges
  - Filter by platform, entity types
  - Saved search presets and quick filters

- **Comparison View**
  - Side-by-side session comparison
  - Network graph overlap analysis between targets
  - Timeline synchronization for multi-target investigations

#### Medium Priority Features
- **Export Enhancements**
  - PDF export with professional styling
  - JSON export with complete data structures
  - Bulk export of multiple sessions
  - Custom report templates

- **Keyboard Shortcuts**
  - `Ctrl/Cmd+K` - Quick session switcher
  - `Ctrl/Cmd+N` - New session
  - `Ctrl/Cmd+R` - Run analysis
  - `Ctrl/Cmd+E` - Export current view

- **Collaboration Features**
  - Session sharing via shareable links
  - Comment/annotation system on reports
  - Session tagging and categorization
  - Team workspaces

- **Visualization Enhancements**
  - Interactive timeline with drill-down capabilities
  - Geographic mapping for location entities
  - Sentiment analysis charts
  - Word clouds from extracted entities

#### Nice-to-Have Features
- **Mobile Optimizations** - Improved responsive design for phones/tablets
- **Custom Themes** - User-defined color schemes
- **Plugins System** - Extensible visualization widgets

---

### Phase 6: CLI Improvements

#### High Priority Features
- **TUI Mode** - Terminal UI interface (htop-style)
  - Real-time job progress visualization
  - Interactive session browser with keyboard navigation
  - Live monitoring alerts in terminal
  - Color-coded status indicators

- **Batch Operations**
  - Process multiple targets from CSV/JSON files
  - Bulk analysis with parallel execution
  - Automated reporting generation
  - Progress tracking for batch jobs

- **Interactive Query Builder**
  - Guided query construction
  - Suggested queries based on target type
  - Query templates and presets
  - Natural language to query conversion

#### Medium Priority Features
- **Rich Output Formats**
  - Colored, formatted reports with syntax highlighting
  - ASCII art charts for quick insights
  - Progress bars for long operations
  - Spinner animations for real-time feedback

- **Shell Integration**
  - Tab completion for commands and targets
  - Alias support for common operations
  - Pipe-friendly output modes
  - Configuration file support (`~/.osintrelay/config`)

- **Debug/Dev Mode**
  - Verbose logging with color coding
  - Step-by-step execution traces
  - LLM prompt inspection
  - Cache inspection tools

#### Nice-to-Have Features
- **Plugin System** - Custom commands and extensions
- **Remote Mode** - Connect to running web server/bot instance
- **Scripting API** - Python/JS bindings for automation

---

### Phase 7: Bot Enhancements

#### High Priority Features
- **Rich Message Formatting**
  - Interactive buttons for common actions (refresh, export)
  - Inline keyboards for quick commands
  - Progress indicators with cancellable jobs
  - Expandable/collapsible report sections

- **Context-Aware Commands**
  - `?continue` - Rerun last analysis with new query
  - `?compare <session>` - Compare with previous session
  - `?trends` - Show activity patterns
  - `?summary` - Quick overview of current session

- **Threaded Conversations**
  - Keep analysis responses in threads
  - Separate monitoring alerts from analyses
  - Per-target conversation threads
  - Message grouping for better organization

#### Medium Priority Features
- **Notification Controls**
  - Mute/unmute specific monitors
  - Digest mode (batch alerts every N minutes)
  - Priority levels (critical/normal/low)
  - Do-not-disturb hours

- **Multi-User Support**
  - User-specific sessions and monitors
  - Admin commands for managing users
  - Access control lists
  - Per-user rate limiting

- **Quick Actions**
  - Add discovered contacts as new targets
  - One-click schedule monitoring
  - Quick entity lookup (e.g., `?entity email@example.com`)

#### Nice-to-Have Features
- **Voice Commands** - Speech-to-text for hands-free operation
- **Image-Based Queries** - Send screenshot/image to analyze
- **Webhooks** - Forward alerts to external systems (Slack, Mattermost, etc.)

---

### Phase 8: Cross-Platform Features

#### High Priority Features
- **Unified Session Sync** - Sessions accessible across Web, CLI, and Bot
- **Real-time Sync** - Live updates across all interfaces via WebSocket
- **Shared Monitoring Rules** - Configure once, alert everywhere

#### Medium Priority Features
- **API Rate Limit Dashboard** - Visualize remaining quotas per platform
- **Cost Tracking** - LLM token/cost usage per session
- **Audit Log** - Track all actions across interfaces with timestamps

---

### Phase 9: Technical Improvements

#### Performance Enhancements
- **Lazy Loading** - Load large session lists and data on demand
- **Virtual Scrolling** - Efficient rendering for large contact/entity lists
- **Cached D3 Graph Rendering** - Pre-render and cache network graphs
- **Debounced Search/Filter** - Reduce unnecessary API calls

#### Accessibility Improvements
- **Full Keyboard Navigation** - All features accessible via keyboard
- **Screen Reader Support** - Proper ARIA labels and semantic HTML
- **High Contrast Mode** - Enhanced visibility for visually impaired users
- **Reduced Motion Options** - Respect user's motion preferences

#### Security Enhancements
- **Session Pinning** - Biometric unlock or PIN for web sessions
- **Encrypted Local Storage** - Sensitive data encryption at rest
- **Audit Trail** - Track all sensitive operations
- **Per-User Rate Limiting** - Prevent abuse and resource exhaustion

---

## 8. Implementation Priority Matrix

### Immediate (Next 1-3 Months)
1. Web Dashboard Overview Page
2. Real-time Notifications Panel
3. CLI TUI Mode
4. Bot Rich Message Formatting

### Short-Term (Next 3-6 Months)
5. Advanced Search & Filter
6. Batch Operations (CLI)
7. Context-Aware Bot Commands
8. Export Enhancements (PDF, JSON)

### Medium-Term (Next 6-12 Months)
9. Comparison View
10. Collaboration Features
11. Multi-User Bot Support
12. Unified Session Sync

### Long-Term (12+ Months)
13. Plugins System
14. Voice Commands
15. Geographic Mapping
16. Mobile App

---

## 9. Technical Debt & Refactoring Priorities

1. **Database Migration** - Consider migrating from JSON file-based storage to SQLite for better concurrency
2. **API Versioning** - Implement proper API versioning for backward compatibility
3. **Testing Coverage** - Increase test coverage for new features, especially UI components
4. **Documentation** - Create comprehensive developer documentation for plugin system
5. **Error Handling** - Improve error messages and recovery mechanisms across all interfaces
6. **Performance Profiling** - Identify and optimize bottlenecks in data fetching and rendering