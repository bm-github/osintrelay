# OSINT Relay API Developer Guide

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Authentication](#authentication)
- [API Reference](#api-reference)
- [Common Use Cases](#common-use-cases)
- [SDK Examples](#sdk-examples)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Best Practices](#best-practices)

---

## Overview

The OSINT Relay Web API provides a RESTful interface for programmatically controlling the OSINT intelligence platform. It enables you to:

- Create and manage investigation sessions
- Add/remove targets (social media accounts)
- Run OSINT analyses with natural language queries
- Retrieve discovered contacts and network graphs
- Export reports and timeline data
- Monitor cache status and manage data

The API is versioned at `/api/v1/` and includes interactive documentation at `/api/docs` (Swagger UI) and `/api/redoc`.

### Base URL

```
http://localhost:8000/api/v1
```

### Data Models

All request and response bodies use JSON. The core Pydantic models are defined in `socialosintagent/api_models.py`:

- **Session**: Groups targets, query history, and results
- **Job**: Represents an analysis job with real-time progress
- **Contact**: Discovered network connection from target's posts
- **CacheEntry**: Cached platform data with freshness status

---

## Getting Started

### 1. Start the Web Server

```bash
# Using uvicorn directly
uvicorn socialosintagent.web_server:app --host 127.0.0.1 --port 8000 --reload

# Using docker-compose
docker compose up -d web
```

### 2. Verify the API is Running

```bash
curl http://localhost:8000/api/v1/platforms
```

Expected response:
```json
{
  "platforms": [
    {
      "name": "twitter",
      "available": true,
      "reason": null
    },
    {
      "name": "reddit",
      "available": true,
      "reason": null
    }
    // ... more platforms
  ]
}
```

### 3. Access Interactive Documentation

Open your browser to:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

---

## Authentication

The API supports HTTP Basic Authentication for securing access beyond localhost.

### Setup Authentication

Add to your `.env` file:

```env
OSINT_WEB_USER=your_username
OSINT_WEB_PASSWORD=your_secure_password
```

### Using Auth with cURL

```bash
curl -u username:password http://localhost:8000/api/v1/sessions
```

### Using Auth with Python (requests)

```python
import requests
from requests.auth import HTTPBasicAuth

response = requests.get(
    'http://localhost:8000/api/v1/sessions',
    auth=HTTPBasicAuth('username', 'password')
)
```

### Using Auth with JavaScript (fetch)

```javascript
const response = await fetch('http://localhost:8000/api/v1/sessions', {
  headers: {
    'Authorization': 'Basic ' + btoa('username:password')
  }
});
```

**Note**: If no credentials are configured in `.env`, the server runs in open mode (suitable for localhost-only access).

---

## API Reference

### Platforms

#### List Available Platforms

```http
GET /api/v1/platforms
```

Returns which platforms have valid API credentials configured.

**Response:**
```json
{
  "platforms": [
    {
      "name": "twitter",
      "available": true
    },
    {
      "name": "github",
      "available": false,
      "reason": "No GITHUB_TOKEN configured"
    }
  ]
}
```

---

### Sessions

#### List All Sessions

```http
GET /api/v1/sessions
```

Returns summary info for all sessions, sorted by most recently updated.

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "name": "Operation Nightfall",
      "platforms": {
        "twitter": ["naval", "elonmusk"],
        "github": ["torvalds"]
      },
      "target_count": 3,
      "query_count": 5,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-16T14:22:00Z"
    }
  ]
}
```

#### Create a Session

```http
POST /api/v1/sessions
Content-Type: application/json
```

**Request Body:**
```json
{
  "name": "My Investigation",
  "platforms": {
    "twitter": ["username1", "username2"],
    "github": ["username3"]
  },
  "fetch_options": {
    "default_count": 50,
    "targets": {}
  }
}
```

**Parameters:**
- `name` (required): Human-readable session name (1-100 chars)
- `platforms` (required): Dict mapping platform names to username lists
- `fetch_options` (optional): Fetch configuration

**Response (201 Created):**
```json
{
  "session_id": "abc123",
  "name": "My Investigation",
  "platforms": {
    "twitter": ["username1", "username2"],
    "github": ["username3"]
  },
  "target_count": 3,
  "query_count": 0,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### Get Session Details

```http
GET /api/v1/sessions/{session_id}
```

Returns full session data including query history.

**Response:**
```json
{
  "session_id": "abc123",
  "name": "My Investigation",
  "platforms": {
    "twitter": ["username1"],
    "github": ["username3"]
  },
  "fetch_options": {
    "default_count": 50,
    "targets": {}
  },
  "monitoring_rules": [],
  "query_history": [
    {
      "query_id": "q456",
      "query": "Summarize recent activity patterns",
      "report": "# Analysis Report\n\n## Summary\n...",
      "metadata": {
        "targets": ["twitter/username1"],
        "total_posts": 150,
        "models_used": ["gpt-4o"],
        "duration_seconds": 45.2
      },
      "entities": {
        "emails": ["user@example.com"],
        "locations": ["New York"],
        "crypto": ["0x1234...abcd"]
      },
      "timestamp": "2024-01-15T11:00:00Z"
    }
  ],
  "dismissed_contacts": [],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:00:00Z"
}
```

#### Delete a Session

```http
DELETE /api/v1/sessions/{session_id}
```

Permanently deletes a session and all its data.

**Response:** 204 No Content

#### Rename a Session

```http
PATCH /api/v1/sessions/{session_id}/rename
Content-Type: application/json
```

**Request Body:**
```json
{
  "name": "Updated Session Name"
}
```

**Response:**
```json
{
  "session_id": "abc123",
  "name": "Updated Session Name",
  // ... other session fields
}
```

#### Update Session Targets

```http
PUT /api/v1/sessions/{session_id}/targets
Content-Type: application/json
```

**Request Body:**
```json
{
  "platforms": {
    "twitter": ["user1", "user2"],
    "reddit": ["user3"]
  },
  "fetch_options": {
    "default_count": 100,
    "targets": {}
  }
}
```

**Note:** This replaces the entire target list. Include all desired targets.

**Response:** Updated session summary

---

### Analysis Jobs

#### Start Analysis

```http
POST /api/v1/sessions/{session_id}/analyse
Content-Type: application/json
```

**Request Body:**
```json
{
  "query": "Identify network connections and recent behavioral patterns",
  "force_refresh": false
}
```

**Parameters:**
- `query` (required): Natural language analysis query (1-500 chars)
- `force_refresh` (optional): Bypass 24h cache and re-fetch all data (default: false)

**Response (202 Accepted):**
```json
{
  "job_id": "job_789",
  "session_id": "abc123",
  "status": "running"
}
```

#### Get Job Status (Polling)

```http
GET /api/v1/jobs/{job_id}
```

**Response:**
```json
{
  "job_id": "job_789",
  "session_id": "abc123",
  "status": "running",
  "query": "Identify network connections...",
  "query_id": null,
  "error": null,
  "progress": {
    "stage": "Fetching posts from Twitter",
    "message": "Loading 50 posts for user1...",
    "current": 25,
    "total": 50
  }
}
```

**Status Values:**
- `running`: Job is in progress
- `complete`: Job finished successfully
- `error`: Job failed with an error

#### Stream Job Progress (SSE)

```http
GET /api/v1/jobs/{job_id}/stream
```

Returns Server-Sent Events stream for real-time progress updates.

**Event Types:**
- `stage`: New processing stage started
- `log`: Informational log message
- `status`: Status update
- `complete`: Job completed successfully
- `error`: Job failed with error

**Example Event Stream:**
```
event: stage
data: {"message": "Fetching posts from Twitter"}

event: log
data: {"message": "Loaded 50 posts for user1"}

event: complete
data: {"query_id": "q456"}
```

**JavaScript Example:**
```javascript
const eventSource = new EventSource('/api/v1/jobs/job_789/stream');

eventSource.addEventListener('stage', (e) => {
  const data = JSON.parse(e.data);
  console.log('Stage:', data.message);
});

eventSource.addEventListener('complete', (e) => {
  const data = JSON.parse(e.data);
  console.log('Query ID:', data.query_id);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  console.error('Job failed:', e.data);
});
```

**Python Example:**
```python
import sseclient

response = requests.get(
    'http://localhost:8000/api/v1/jobs/job_789/stream',
    stream=True
)
client = sseclient.SSEClient(response)

for event in client.events():
    if event.event == 'complete':
        data = json.loads(event.data)
        print(f"Complete! Query ID: {data['query_id']}")
        break
```

---

### Contacts

#### Get Discovered Contacts

```http
GET /api/v1/sessions/{session_id}/contacts
```

Returns contacts discovered from cached posts, excluding dismissed contacts.

**Response:**
```json
{
  "contacts": [
    {
      "platform": "twitter",
      "username": "contact_user",
      "interaction_types": ["mention", "retweet"],
      "weight": 15,
      "first_seen": "2024-01-10T08:00:00Z",
      "last_seen": "2024-01-15T14:30:00Z"
    }
  ],
  "dismissed": ["twitter/dismissed_user"],
  "total_extracted": 25
}
```

**Fields:**
- `weight`: Total interaction count (higher = stronger connection)
- `interaction_types`: How this contact was found (mention, retweet, reply, etc.)

#### Dismiss a Contact

```http
POST /api/v1/sessions/{session_id}/contacts/dismiss
Content-Type: application/json
```

**Request Body:**
```json
{
  "platform": "twitter",
  "username": "contact_user"
}
```

**Response:**
```json
{
  "dismissed": "twitter/contact_user"
}
```

#### Restore a Dismissed Contact

```http
POST /api/v1/sessions/{session_id}/contacts/undismiss
Content-Type: application/json
```

**Request Body:** Same as dismiss

**Response:**
```json
{
  "undismissed": "twitter/contact_user"
}
```

---

### Timeline & Media

#### Get Timeline Data

```http
GET /api/v1/sessions/{session_id}/timeline
```

Returns timestamp data for visualization.

**Response:**
```json
{
  "events": [
    {
      "timestamp": "2024-01-15T10:00:00Z",
      "platform": "twitter",
      "username": "user1",
      "content": "Post content..."
    }
  ]
}
```

#### Get Media List

```http
GET /api/v1/sessions/{session_id}/media
```

**Response:**
```json
{
  "media": [
    {
      "path": "data/media/twitter/user1/image1.jpg",
      "analysis": "A photo showing..."
    }
  ]
}
```

#### Download Media File

```http
GET /api/v1/sessions/{session_id}/media/file?path={encoded_path}
```

Returns the media file as a binary response.

---

### Cache

#### Get Cache Status

```http
GET /api/v1/cache
```

**Response:**
```json
{
  "entries": [
    {
      "platform": "twitter",
      "username": "user1",
      "post_count": 150,
      "cached_at": "2024-01-15T10:00:00Z",
      "is_fresh": true
    }
  ]
}
```

#### Purge Cache

```http
POST /api/v1/cache/purge
Content-Type: application/json
```

**Request Body - Purge All:**
```json
{
  "targets": ["all"]
}
```

**Request Body - Purge Specific:**
```json
{
  "targets": ["specific"],
  "keys": ["twitter/user1", "github/user2"]
}
```

**Request Body - Purge by Type:**
```json
{
  "targets": ["cache", "media", "outputs"]
}
```

**Response:** 204 No Content

---

### Export

#### Export Session

```http
GET /api/v1/sessions/{session_id}/export
```

Returns full session data as JSON.

---

## Common Use Cases

### Use Case 1: Simple Analysis Workflow

Create a session, add targets, run analysis, and get results.

```python
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

# 1. Create a session
session = requests.post(f"{BASE_URL}/sessions", json={
    "name": "Target Investigation",
    "platforms": {
        "twitter": ["target_user"]
    }
}).json()
session_id = session["session_id"]

# 2. Start analysis
job = requests.post(
    f"{BASE_URL}/sessions/{session_id}/analyse",
    json={"query": "Summarize recent activity and connections"}
).json()
job_id = job["job_id"]

# 3. Wait for completion (polling)
while True:
    status = requests.get(f"{BASE_URL}/jobs/{job_id}").json()
    if status["status"] == "complete":
        break
    elif status["status"] == "error":
        raise Exception(f"Job failed: {status['error']}")
    time.sleep(2)

# 4. Get results
session_data = requests.get(f"{BASE_URL}/sessions/{session_id}").json()
latest_result = session_data["query_history"][-1]
print(latest_result["report"])
```

### Use Case 2: Real-time Progress with SSE

Use Server-Sent Events for live progress updates.

```javascript
async function runAnalysisWithProgress(sessionId, query) {
  // Start job
  const startRes = await fetch(`/api/v1/sessions/${sessionId}/analyse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });
  const { job_id } = await startRes.json();

  // Stream progress
  const eventSource = new EventSource(`/api/v1/jobs/${job_id}/stream`);

  return new Promise((resolve, reject) => {
    eventSource.addEventListener('stage', (e) => {
      const data = JSON.parse(e.data);
      console.log('▶', data.message);
    });

    eventSource.addEventListener('log', (e) => {
      const data = JSON.parse(e.data);
      console.log('  ', data.message);
    });

    eventSource.addEventListener('complete', async (e) => {
      eventSource.close();
      const session = await fetch(`/api/v1/sessions/${sessionId}`).then(r => r.json());
      const latestQuery = session.query_history[session.query_history.length - 1];
      resolve(latestQuery);
    });

    eventSource.addEventListener('error', (e) => {
      eventSource.close();
      reject(new Error('Analysis failed'));
    });
  });
}

// Usage
const result = await runAnalysisWithProgress('abc123', 'Analyze behavior patterns');
console.log(result.report);
```

### Use Case 3: Network Graph Analysis

Extract and analyze network connections.

```python
import requests
import networkx as nx
import matplotlib.pyplot as plt

BASE_URL = "http://localhost:8000/api/v1"
session_id = "abc123"

# Get contacts
contacts_resp = requests.get(f"{BASE_URL}/sessions/{session_id}/contacts").json()
session_data = requests.get(f"{BASE_URL}/sessions/{session_id}").json()

# Build network graph
G = nx.Graph()

# Add target nodes
for platform, users in session_data["platforms"].items():
    for user in users:
        G.add_node(user, platform=platform, type='target')

# Add contact nodes and edges
for contact in contacts_resp["contacts"]:
    contact_id = f"{contact['username']}"
    G.add_node(contact_id, platform=contact["platform"], type='contact')

    # Connect to all targets on same platform
    for platform, users in session_data["platforms"].items():
        if platform == contact["platform"]:
            for user in users:
                G.add_edge(user, contact_id, weight=contact["weight"])

# Visualize
pos = nx.spring_layout(G)
node_colors = ['red' if G.nodes[n].get('type') == 'target' else 'blue' for n in G.nodes]
node_sizes = [100 if G.nodes[n].get('type') == 'target' else 50 for n in G.nodes]

nx.draw(G, pos, node_color=node_colors, node_size=node_sizes, with_labels=True)
plt.show()

# Find most connected contacts
betweenness = nx.betweenness_centrality(G)
top_contacts = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:5]
print("Most connected contacts:", top_contacts)
```

### Use Case 4: Batch Analysis of Multiple Targets

Analyze multiple users in parallel.

```python
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

async def analyze_target(session, target, query):
    """Analyze a single target"""
    async with aiohttp.ClientSession() as http:
        # Add target to session
        await http.put(
            f"http://localhost:8000/api/v1/sessions/{session}/targets",
            json={
                "platforms": {"twitter": [target]},
                "fetch_options": {"default_count": 50}
            }
        )

        # Start analysis
        job = await http.post(
            f"http://localhost:8000/api/v1/sessions/{session}/analyse",
            json={"query": query}
        )
        job_id = (await job.json())["job_id"]

        # Poll for completion
        while True:
            status = await http.get(f"http://localhost:8000/api/v1/jobs/{job_id}")
            status_data = await status.json()
            if status_data["status"] == "complete":
                return target, "complete"
            elif status_data["status"] == "error":
                return target, "error"
            await asyncio.sleep(1)

async def batch_analyze(targets, query):
    """Analyze multiple targets in parallel"""
    # Create session
    async with aiohttp.ClientSession() as http:
        session = await http.post(
            "http://localhost:8000/api/v1/sessions",
            json={"name": "Batch Analysis", "platforms": {}}
        )
        session_id = (await session.json())["session_id"]

        # Run analyses in parallel (limited concurrency)
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent

        async def limited_analyze(target):
            async with semaphore:
                return await analyze_target(session_id, target, query)

        results = await asyncio.gather(*[
            limited_analyze(target) for target in targets
        ])

        return session_id, results

# Usage
targets = ["user1", "user2", "user3", "user4", "user5"]
session_id, results = asyncio.run(batch_analyze(targets, "Summarize activity"))
print(f"Session: {session_id}")
for target, status in results:
    print(f"{target}: {status}")
```

### Use Case 5: Continuous Monitoring with Webhooks

Set up monitoring and send alerts to external systems.

```python
import requests
import time
from datetime import datetime

def send_webhook_alert(webhook_url, session_id, alert_data):
    """Send alert to external webhook"""
    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "alert": alert_data
    }
    requests.post(webhook_url, json=payload)

def monitor_session(session_id, keywords, webhook_url=None):
    """Monitor session for keyword matches"""
    BASE_URL = "http://localhost:8000/api/v1"

    # Get initial analysis
    contacts = requests.get(f"{BASE_URL}/sessions/{session_id}/contacts").json()
    seen_posts = set()

    while True:
        # Refresh analysis
        job = requests.post(
            f"{BASE_URL}/sessions/{session_id}/analyse",
            json={
                "query": f"Check for mentions of: {', '.join(keywords)}",
                "force_refresh": True
            }
        ).json()

        # Wait for completion
        job_id = job["job_id"]
        while True:
            status = requests.get(f"{BASE_URL}/jobs/{job_id}").json()
            if status["status"] in ["complete", "error"]:
                break
            time.sleep(2)

        # Check for new matches
        session = requests.get(f"{BASE_URL}/sessions/{session_id}").json()
        latest = session["query_history"][-1]

        if any(kw.lower() in latest["report"].lower() for kw in keywords):
            alert = {
                "type": "keyword_match",
                "keywords": keywords,
                "report": latest["report"]
            }
            if webhook_url:
                send_webhook_alert(webhook_url, session_id, alert)
            print(f"ALERT: Keyword match detected!")

        time.sleep(300)  # Check every 5 minutes

# Usage
# monitor_session("abc123", ["bitcoin", "crypto"], "https://hooks.slack.com/...")
```

---

## SDK Examples

### Python SDK Wrapper

```python
import requests
from typing import List, Dict, Optional
from datetime import datetime

class OSINTRelayClient:
    """Python SDK for OSINT Relay API"""

    def __init__(self, base_url: str = "http://localhost:8000/api/v1",
                 username: Optional[str] = None, password: Optional[str] = None):
        self.base_url = base_url
        self.auth = (username, password) if username and password else None

    def _request(self, method: str, endpoint: str, **kwargs):
        """Make authenticated request"""
        url = f"{self.base_url}{endpoint}"
        if self.auth:
            kwargs.setdefault('auth', self.auth)
        return requests.request(method, url, **kwargs)

    # Sessions
    def create_session(self, name: str, platforms: Dict[str, List[str]],
                      fetch_options: Optional[Dict] = None) -> Dict:
        """Create a new investigation session"""
        return self._request('POST', '/sessions', json={
            'name': name,
            'platforms': platforms,
            'fetch_options': fetch_options
        }).json()

    def list_sessions(self) -> List[Dict]:
        """List all sessions"""
        return self._request('GET', '/sessions').json()['sessions']

    def get_session(self, session_id: str) -> Dict:
        """Get session details"""
        return self._request('GET', f'/sessions/{session_id}').json()

    def delete_session(self, session_id: str) -> None:
        """Delete a session"""
        self._request('DELETE', f'/sessions/{session_id}')

    # Analysis
    def start_analysis(self, session_id: str, query: str,
                       force_refresh: bool = False) -> str:
        """Start an analysis job, returns job_id"""
        response = self._request('POST', f'/sessions/{session_id}/analyse', json={
            'query': query,
            'force_refresh': force_refresh
        })
        return response.json()['job_id']

    def get_job_status(self, job_id: str) -> Dict:
        """Get job status"""
        return self._request('GET', f'/jobs/{job_id}').json()

    def wait_for_job(self, job_id: str, timeout: int = 300) -> Dict:
        """Wait for job to complete"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            status = self.get_job_status(job_id)
            if status['status'] == 'complete':
                return status
            elif status['status'] == 'error':
                raise Exception(f"Job failed: {status.get('error')}")
            time.sleep(2)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")

    def analyze(self, session_id: str, query: str,
                force_refresh: bool = False, timeout: int = 300) -> Dict:
        """Run analysis and wait for completion"""
        job_id = self.start_analysis(session_id, query, force_refresh)
        return self.wait_for_job(job_id, timeout)

    # Contacts
    def get_contacts(self, session_id: str) -> Dict:
        """Get discovered contacts"""
        return self._request('GET', f'/sessions/{session_id}/contacts').json()

    def dismiss_contact(self, session_id: str, platform: str, username: str) -> None:
        """Dismiss a contact"""
        self._request('POST', f'/sessions/{session_id}/contacts/dismiss', json={
            'platform': platform,
            'username': username
        })

    def restore_contact(self, session_id: str, platform: str, username: str) -> None:
        """Restore a dismissed contact"""
        self._request('POST', f'/sessions/{session_id}/contacts/undismiss', json={
            'platform': platform,
            'username': username
        })

    # Cache
    def get_cache_status(self) -> Dict:
        """Get cache status"""
        return self._request('GET', '/cache').json()

    def purge_cache(self, targets: List[str], keys: Optional[List[str]] = None) -> None:
        """Purge cache"""
        self._request('POST', '/cache/purge', json={
            'targets': targets,
            'keys': keys
        })

    # Platforms
    def get_platforms(self) -> List[Dict]:
        """Get available platforms"""
        return self._request('GET', '/platforms').json()['platforms']


# Usage Example
if __name__ == "__main__":
    client = OSINTRelayClient()

    # Check available platforms
    platforms = client.get_platforms()
    available = [p['name'] for p in platforms if p['available']]
    print(f"Available platforms: {available}")

    # Create session
    session = client.create_session(
        name="Demo Investigation",
        platforms={"twitter": ["example_user"]}
    )
    session_id = session['session_id']
    print(f"Created session: {session_id}")

    # Run analysis
    result = client.analyze(
        session_id=session_id,
        query="Summarize recent activity and connections"
    )
    print(f"Analysis complete!")

    # Get contacts
    contacts = client.get_contacts(session_id)
    print(f"Found {len(contacts['contacts'])} contacts")
```

### JavaScript/TypeScript SDK Wrapper

```typescript
interface AuthConfig {
  username?: string;
  password?: string;
}

interface Session {
  session_id: string;
  name: string;
  platforms: Record<string, string[]>;
  target_count: number;
  query_count: number;
  created_at: string;
  updated_at: string;
}

interface Contact {
  platform: string;
  username: string;
  interaction_types: string[];
  weight: number;
  first_seen?: string;
  last_seen?: string;
}

class OSINTRelayClient {
  private baseUrl: string;
  private auth?: string;

  constructor(baseUrl: string = 'http://localhost:8000/api/v1', auth?: AuthConfig) {
    this.baseUrl = baseUrl;
    if (auth?.username && auth?.password) {
      this.auth = btoa(`${auth.username}:${auth.password}`);
    }
  }

  private async request<T>(
    method: string,
    endpoint: string,
    body?: any
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (this.auth) {
      headers['Authorization'] = `Basic ${this.auth}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  // Sessions
  async createSession(
    name: string,
    platforms: Record<string, string[]>,
    fetchOptions?: Record<string, any>
  ): Promise<Session> {
    return this.request<Session>('POST', '/sessions', {
      name,
      platforms,
      fetch_options: fetchOptions,
    });
  }

  async listSessions(): Promise<{ sessions: Session[] }> {
    return this.request<{ sessions: Session[] }>('GET', '/sessions');
  }

  async getSession(sessionId: string): Promise<Session> {
    return this.request<Session>('GET', `/sessions/${sessionId}`);
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.request('DELETE', `/sessions/${sessionId}`);
  }

  // Analysis
  async startAnalysis(
    sessionId: string,
    query: string,
    forceRefresh = false
  ): Promise<{ job_id: string; session_id: string; status: string }> {
    return this.request('POST', `/sessions/${sessionId}/analyse`, {
      query,
      force_refresh: forceRefresh,
    });
  }

  async getJobStatus(jobId: string): Promise<{
    job_id: string;
    session_id: string;
    status: string;
    query?: string;
    query_id?: string;
    error?: string;
    progress?: Record<string, any>;
  }> {
    return this.request('GET', `/jobs/${jobId}`);
  }

  async waitForJob(jobId: string, timeout = 300000): Promise<any> {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      const status = await this.getJobStatus(jobId);

      if (status.status === 'complete') {
        return status;
      }

      if (status.status === 'error') {
        throw new Error(`Job failed: ${status.error}`);
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    throw new Error(`Job ${jobId} timed out after ${timeout}ms`);
  }

  async analyze(
    sessionId: string,
    query: string,
    forceRefresh = false,
    timeout = 300000
  ): Promise<any> {
    const { job_id } = await this.startAnalysis(sessionId, query, forceRefresh);
    return this.waitForJob(job_id, timeout);
  }

  // Contacts
  async getContacts(sessionId: string): Promise<{
    contacts: Contact[];
    dismissed: string[];
    total_extracted: number;
  }> {
    return this.request('GET', `/sessions/${sessionId}/contacts`);
  }

  async dismissContact(
    sessionId: string,
    platform: string,
    username: string
  ): Promise<{ dismissed: string }> {
    return this.request('POST', `/sessions/${sessionId}/contacts/dismiss`, {
      platform,
      username,
    });
  }

  async restoreContact(
    sessionId: string,
    platform: string,
    username: string
  ): Promise<{ undismissed: string }> {
    return this.request('POST', `/sessions/${sessionId}/contacts/undismiss`, {
      platform,
      username,
    });
  }

  // Cache
  async getCacheStatus(): Promise<{ entries: any[] }> {
    return this.request('GET', '/cache');
  }

  async purgeCache(
    targets: string[],
    keys?: string[]
  ): Promise<void> {
    await this.request('POST', '/cache/purge', { targets, keys });
  }

  // Platforms
  async getPlatforms(): Promise<{
    platforms: Array<{ name: string; available: boolean; reason?: string }>;
  }> {
    return this.request('GET', '/platforms');
  }
}

// Usage Example
async function main() {
  const client = new OSINTRelayClient();

  // Check available platforms
  const platforms = await client.getPlatforms();
  console.log('Available platforms:', platforms.platforms.filter(p => p.available));

  // Create session
  const session = await client.createSession('Demo Investigation', {
    twitter: ['example_user'],
  });
  console.log('Created session:', session.session_id);

  // Run analysis
  await client.analyze(session.session_id, 'Summarize activity');

  // Get contacts
  const contacts = await client.getContacts(session.session_id);
  console.log(`Found ${contacts.contacts.length} contacts`);
}

main().catch(console.error);
```

---

## Error Handling

### Error Response Format

All errors return JSON with a `detail` field:

```json
{
  "detail": "Session 'abc123' not found"
}
```

### Common HTTP Status Codes

| Code | Meaning | Example Scenarios |
|------|---------|-------------------|
| 200 | OK | Successful GET/PUT/PATCH |
| 201 | Created | New session created |
| 202 | Accepted | Analysis job started |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid request body |
| 401 | Unauthorized | Missing/invalid auth |
| 404 | Not Found | Session or job doesn't exist |
| 409 | Conflict | Job already running for session |
| 422 | Unprocessable Entity | Validation error |
| 500 | Internal Server Error | Server error |

### Handling Errors in Python

```python
import requests
from requests.exceptions import HTTPError, RequestException

try:
    response = requests.post('http://localhost:8000/api/v1/sessions', json={
        "name": "Test",
        "platforms": {}
    })
    response.raise_for_status()
    return response.json()
except HTTPError as e:
    if e.response.status_code == 422:
        print(f"Validation error: {e.response.json()['detail']}")
    elif e.response.status_code == 404:
        print("Resource not found")
    else:
        print(f"HTTP error: {e}")
except RequestException as e:
    print(f"Request failed: {e}")
```

### Handling Errors in JavaScript

```javascript
async function createSession(name, platforms) {
  try {
    const response = await fetch('http://localhost:8000/api/v1/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, platforms })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Failed to create session:', error.message);
    throw error;
  }
}
```

---

## Rate Limiting

### Platform API Limits

The API respects rate limits imposed by each platform:

- **Twitter**: ~900 requests/15 minutes (app auth)
- **Reddit**: ~60 requests/minute
- **GitHub**: 5000 requests/hour (authenticated)
- **Bluesky**: ~100 requests/second
- **Mastodon**: Varies by instance
- **Hacker News**: No strict limit

### Internal Rate Limiting

The web server uses a single-threaded executor (`max_workers=1`) to prevent exhausting platform rate limits. Only one analysis job runs at a time.

### Best Practices

1. **Use cache**: Enable caching to avoid redundant API calls
2. **Batch targets**: Group multiple users in one session
3. **Respect intervals**: Don't run analyses too frequently
4. **Monitor status**: Check platform availability before starting jobs

---

## Best Practices

### 1. Session Management

- **Organize by investigation**: Create separate sessions for different targets/operations
- **Meaningful names**: Use descriptive session names for easy identification
- **Clean up**: Delete old sessions to free up disk space

### 2. Caching Strategy

- **Leverage cache**: Use cached data when recent (24h fresh)
- **Selective refresh**: Only use `force_refresh` when necessary
- **Monitor cache age**: Check cache status before heavy operations

```python
# Check if data is fresh before analysis
cache = client.get_cache_status()
twitter_cache = next((e for e in cache['entries'] if e['platform'] == 'twitter' and e['username'] == 'target'), None)

if twitter_cache and twitter_cache['is_fresh']:
    # Use cached data
    result = client.analyze(session_id, "Analyze patterns", force_refresh=False)
else:
    # Need fresh data
    result = client.analyze(session_id, "Analyze patterns", force_refresh=True)
```

### 3. Error Handling

- **Always handle errors**: Implement try-catch for all API calls
- **Check job status**: Verify job completion before using results
- **Retry logic**: Implement exponential backoff for transient failures

### 4. Performance

- **Use SSE for progress**: Prefer SSE streaming over polling for long jobs
- **Limit contact size**: Contact lists are capped at top results for performance
- **Batch operations**: Group related operations to reduce overhead

### 5. Security

- **Use authentication**: Always enable auth in production
- **Secure credentials**: Never hardcode API keys in client code
- **Validate inputs**: Sanitize user inputs before sending to API

### 6. Data Management

- **Export regularly**: Periodically export important sessions
- **Purge old data**: Clean up cache and old sessions
- **Monitor storage**: Check disk usage for `data/` directory

```python
# Regular maintenance routine
def maintain_data(client, max_age_days=30):
    """Purge old cache and export important sessions"""
    from datetime import datetime, timedelta

    # Purge old cache
    cache = client.get_cache_status()
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    old_entries = [
        f"{e['platform']}/{e['username']}"
        for e in cache['entries']
        if datetime.fromisoformat(e['cached_at']) < cutoff
    ]

    if old_entries:
        client.purge_cache(['specific'], old_entries)
        print(f"Purged {len(old_entries)} old cache entries")
```

---

## Support & Resources

- **Interactive API Docs**: http://localhost:8000/api/docs
- **ReDoc Documentation**: http://localhost:8000/api/redoc
- **Main README**: See project README.md for setup instructions
- **Issues**: Report bugs and feature requests on GitHub

---

## License

This API is part of the OWASP OSINT Relay project. See LICENSE file for details.
