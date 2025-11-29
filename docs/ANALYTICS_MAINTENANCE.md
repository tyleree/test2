# Analytics System Maintenance Guide

## Overview

The Veterans Benefits AI analytics system tracks user interactions, performance metrics, and visitor locations using a dual-storage approach:

1. **File-based storage** (`stats.pkl`) - Simple pickle file for basic counters and location data
2. **PostgreSQL database** - Full event tracking with detailed analytics

---

## Data Storage Structure

### 1. File-Based Stats (`stats.pkl`)

Located at project root. Stores basic counters that persist between restarts.

```python
{
    'ask_count': int,           # Total questions asked
    'visit_count': int,         # Total page visits
    'unique_visitors': set(),   # Set of unique IP hashes
    'visitor_locations': {      # Heat map data
        'CA': 45,               # State code -> count
        'TX': 32,
        'NY': 28,
        'Local': 15,            # Local/dev requests
        'Unknown': 8,           # Unresolvable IPs
        'International-UK': 5   # International visitors
    },
    'first_visit': str,         # ISO timestamp
    'last_updated': str         # ISO timestamp
}
```

**Key Functions in `app.py`:**
- `load_stats()` - Load from file on startup
- `save_stats(stats)` - Persist to file
- `track_visitor_location(ip)` - Add location data

### 2. PostgreSQL Database

Required env var: `DATABASE_URL`

#### Events Table (`events`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `ts` | TIMESTAMP | Event timestamp |
| `type` | VARCHAR(32) | `'pageview'`, `'chat_question'`, `'visitor_location'` |
| `path` | TEXT | Page URL path |
| `sid` | VARCHAR(64) | Session ID |
| `ip` | VARCHAR(64) | Client IP |
| `ua` | TEXT | User agent |
| `ref` | TEXT | Referrer URL |
| `meta` | TEXT | JSON metadata |
| `location` | VARCHAR(64) | State code or location type |
| `country` | VARCHAR(8) | Country code |
| `lat`, `lng` | FLOAT | Coordinates |
| `openai_prompt_tokens` | INTEGER | Input tokens |
| `openai_completion_tokens` | INTEGER | Output tokens |
| `openai_total_tokens` | INTEGER | Total tokens |
| `model_used` | VARCHAR(64) | Model name (e.g., `gpt-4.1-mini`) |
| `api_provider` | VARCHAR(32) | `'openai'` |
| `response_ms` | INTEGER | Response time in ms |
| `prompt_chars` | INTEGER | Question length |
| `answer_chars` | INTEGER | Answer length |
| `success` | INTEGER | 1=success, 0=failure |

#### Legacy Stats Table (`legacy_stats`)

Stores migrated file-based stats for historical continuity.

| Column | Type | Description |
|--------|------|-------------|
| `key` | VARCHAR(64) | Stat name |
| `value` | TEXT | JSON value |
| `updated_at` | TIMESTAMP | Last update |

---

## Maintenance Tasks

### Clearing/Resetting Stats

#### Reset File-Based Stats
```bash
# Delete the pickle file (will reset to zeros on restart)
rm stats.pkl
```

#### Reset via Python
```python
from app import save_stats
from datetime import datetime

# Reset to fresh state
save_stats({
    'ask_count': 0,
    'visit_count': 0,
    'unique_visitors': set(),
    'visitor_locations': {},
    'first_visit': datetime.now().isoformat(),
    'last_updated': datetime.now().isoformat()
})
```

#### Clear Database Events
```sql
-- Clear all events (DANGER: irreversible)
TRUNCATE TABLE events;

-- Clear legacy stats
TRUNCATE TABLE legacy_stats;

-- Or delete specific date range
DELETE FROM events WHERE ts < NOW() - INTERVAL '90 days';
```

### Removing Fake/Test Data

#### From Heat Map (visitor_locations)

```python
import pickle

# Load current stats
with open('stats.pkl', 'rb') as f:
    stats = pickle.load(f)

# View current data
print(stats['visitor_locations'])

# Remove specific entries
del stats['visitor_locations']['FAKE_STATE']

# Or reset entirely
stats['visitor_locations'] = {}

# Save
with open('stats.pkl', 'wb') as f:
    pickle.dump(stats, f)
```

#### Clear Sample Data Endpoint
The `/debug/populate-sample-locations` endpoint adds fake data for testing.
To clear it, reset `visitor_locations` as shown above.

### Adjusting Counters

```python
import pickle

with open('stats.pkl', 'rb') as f:
    stats = pickle.load(f)

# Adjust ask count
stats['ask_count'] = 1000  # Set to specific value

# Adjust visit count  
stats['visit_count'] = 5000

# Save
with open('stats.pkl', 'wb') as f:
    pickle.dump(stats, f)
```

---

## API Endpoints

### Public Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/metrics` | GET | Basic stats (ask_count, visit_count, visitor_locations) |
| `/api/locations` | GET | Heat map data (US states only, formatted) |
| `/stats` | GET | Stats page (React SPA) |

### Admin Endpoints (require `?token=ADMIN_TOKEN` or `X-Admin-Token` header)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/analytics` | GET | Full analytics dashboard |
| `/api/analytics/stats` | GET | Detailed JSON analytics |
| `/cache/metrics` | GET | Cache hit/miss rates |
| `/cache/clear` | POST | Clear response cache |

### Debug Endpoints

| Endpoint | Description |
|----------|-------------|
| `/debug/locations-data` | Raw location data comparison |
| `/debug/populate-sample-locations` | Add fake US state data for testing |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | No | PostgreSQL connection string |
| `ADMIN_TOKEN` | Yes | Token for admin endpoints |
| `FRONTEND_BUILD_DIR` | No | Path to React build (default: `frontend/dist`) |

---

## Data Flow

```
User Request
    │
    ├─► app.py increments ask_count in stats.pkl
    │
    ├─► track_visitor_location() updates visitor_locations
    │
    └─► If DATABASE_URL set:
            analytics/__init__.py creates Event record
            with full details (tokens, timing, etc.)
```

---

## Heat Map Data Format

The `/api/locations` endpoint returns:

```json
{
  "us_states": {
    "CA": 45,
    "TX": 32,
    "NY": 28
  },
  "total": 150,
  "data_source": "file_stats"
}
```

The React `USHeatMap` component expects:
- Keys: 2-letter US state codes (uppercase)
- Values: Integer counts
- Uses FIPS-to-state-code mapping internally

---

## Troubleshooting

### Heat Map Not Showing Data

1. Check `/api/locations` returns data
2. Verify `visitor_locations` in stats.pkl has valid state codes
3. Check browser console for TopoJSON loading errors
4. Ensure `/static/us-states.json` exists

### Stats Not Persisting

1. Check file permissions on `stats.pkl`
2. Verify `stats_lock` is working (thread safety)
3. Check for exceptions in `save_stats()`

### Database Analytics Missing

1. Verify `DATABASE_URL` is set correctly
2. Check PostgreSQL connection in Render logs
3. Run schema migration: `ensure_database_schema()` is called automatically

### Admin Dashboard 401

1. Verify `ADMIN_TOKEN` env var is set
2. Use `?token=YOUR_TOKEN` in URL or `X-Admin-Token` header

---

## Files Reference

| File | Purpose |
|------|---------|
| `app.py` | Main Flask app, stats loading/saving |
| `analytics/__init__.py` | Analytics blueprint, database queries |
| `models.py` | SQLAlchemy models (Event, LegacyStats) |
| `db.py` | Database connection setup |
| `stats.pkl` | File-based stats storage |
| `veteran-ai-spark/src/pages/Stats.tsx` | React stats page |
| `veteran-ai-spark/src/components/USHeatMap.tsx` | Heat map component |
| `static/us-states.json` | TopoJSON for US map |

