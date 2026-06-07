# Apple Health MCP Server

Exposes synced Apple Health data to your AI agent via the **Model Context Protocol (HTTP + SSE)**.

Runs as a **separate process** alongside the FastAPI app, sharing the same SQLite database in read-only mode.

---

## Run

```bash
cd backend
python mcp_server.py
```

Or with custom port/host:

```bash
LOCAL_SCALE_MCP_PORT=8001 LOCAL_SCALE_MCP_HOST=0.0.0.0 python mcp_server.py
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LOCAL_SCALE_MCP_PORT` | `8001` | Port to bind the SSE server |
| `LOCAL_SCALE_MCP_HOST` | `0.0.0.0` | Host to bind |
| `LOCAL_SCALE_DATABASE_URL` | Same as FastAPI app | SQLite URL (shared automatically) |
| `LOCAL_SCALE_DATA_DIR` | `<repo>/data` | Data directory (used to resolve default DB path) |

---

## Agent Config

Add this to your agent's MCP config (replace `<minipc-ip>` with your Mini PC's LAN IP):

```json
{
  "mcpServers": {
    "local-scale-health": {
      "url": "http://<minipc-ip>:8001/sse"
    }
  }
}
```

---

## Available Tools

| Tool | Description |
|---|---|
| `get_apple_health_context` | Full LLM-ready overview — all categories in one call |
| `get_activity` | Steps, calories, exercise time, distances (averaged across period) |
| `get_heart` | Resting HR, HRV, VO2 max, O2 sat, blood pressure, ECG, AFib |
| `get_sleep` | Total sleep hours, stage breakdown, under-7h flag |
| `get_nutrition` | Calories, macros, water, fiber, caffeine, alcohol (averaged) |
| `get_vitals` | Body temp, respiratory rate, blood glucose, blood alcohol |
| `get_body_metrics` | Weight, body fat %, BMI, lean mass, waist, height (from Apple Health) |
| `get_workouts` | Workout sessions list with type, duration, calories, distance |
| `get_symptoms` | Active symptoms with severity (fatigue, headache, etc.) |
| `get_snapshots_list` | Metadata-only list — check freshness without loading payloads |

All tools accept `profile_id: int`. `get_snapshots_list` also accepts `limit: int` (default 10, max 90).

---

## Data Flow

```
iPhone shortcut
    POST /api/apple-health/sync
         │
         ▼
  FastAPI (port 8000)
    stores payload_json → apple_health_snapshots table
         │
         ▼ (same SQLite file, read-only)
  MCP Server (port 8001)
    tools extract & return clean structured data
         │
         ▼
  Your AI Agent
```

---

## Notes

- **Compact output**: Null/empty values are stripped from responses and JSON is minified to minimize token usage for LLM agents.
- **Date semantics**: `synced_at` = when data was sent from iPhone. Each metric has its own `measured_at` = actual reading time. Daily metrics (activity, nutrition) are period averages.
- **Sleep data**: `get_sleep` returns `"no_data"` if `HKCategoryTypeIdentifierSleepAnalysis` is absent. Sleep is aggregated by stage (minutes per stage), not individual sessions.
- **Body fat %**: stored as a ratio (0.165) in Apple Health, returned as a percentage (16.5%) by the tools.
- **Body metrics vs scale data**: `get_body_metrics` returns Apple Health readings. For BIA body composition from the scale, use the FastAPI measurement endpoints instead.
- **Freshness**: use `get_snapshots_list` first to check `synced_at` before calling heavier tools.
- **No authentication**: the MCP server has no auth layer — it is designed for trusted LAN access only.
