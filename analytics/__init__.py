import os
import json
import pickle
from datetime import datetime
from flask import Blueprint, request, g, abort, jsonify
from sqlalchemy import text, and_
from models import Event, LegacyStats

bp = Blueprint("analytics", __name__, url_prefix="")

def _admin_ok():
    """Check if admin token is valid"""
    token = os.getenv("ADMIN_TOKEN", "")
    given = request.args.get("token") or request.headers.get("X-Admin-Token")
    return token and given == token

def ensure_database_schema():
    """Ensure database schema is up to date"""
    if not hasattr(g, 'db') or g.db is None:
        return False
        
    try:
        # Check if location column exists
        column_check = g.db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='events' AND column_name='location'
        """)).mappings().all()
        
        if not column_check:
            print("🔧 Adding location tracking columns to events table...")
            # Add location tracking columns
            g.db.execute(text("""
                ALTER TABLE events 
                ADD COLUMN IF NOT EXISTS location VARCHAR(64),
                ADD COLUMN IF NOT EXISTS country VARCHAR(8),
                ADD COLUMN IF NOT EXISTS lat FLOAT,
                ADD COLUMN IF NOT EXISTS lng FLOAT
            """))
            
            # Add index
            g.db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_events_location ON events(location)
            """))
            
            g.db.commit()
            print("✅ Database schema updated with location tracking")
        
        # Check if token tracking columns exist
        token_check = g.db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='events' AND column_name='openai_total_tokens'
        """)).mappings().all()
        
        if not token_check:
            print("🔧 Adding token usage tracking columns to events table...")
            # Add token tracking columns
            g.db.execute(text("""
                ALTER TABLE events 
                ADD COLUMN IF NOT EXISTS openai_prompt_tokens INTEGER,
                ADD COLUMN IF NOT EXISTS openai_completion_tokens INTEGER,
                ADD COLUMN IF NOT EXISTS openai_total_tokens INTEGER,
                ADD COLUMN IF NOT EXISTS pinecone_tokens INTEGER,
                ADD COLUMN IF NOT EXISTS model_used VARCHAR(64),
                ADD COLUMN IF NOT EXISTS api_provider VARCHAR(32)
            """))
            
            # Add indexes for token analysis
            g.db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_events_tokens ON events(openai_total_tokens) WHERE openai_total_tokens IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_events_model ON events(model_used) WHERE model_used IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_events_provider ON events(api_provider) WHERE api_provider IS NOT NULL;
            """))
            
            g.db.commit()
            print("✅ Database schema updated with token usage tracking")
        
        # Performance columns
        perf_check = g.db.execute(text("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='events' AND column_name='response_ms'
        """)).mappings().all()
        if not perf_check:
            print("🔧 Adding performance analytics columns to events table...")
            g.db.execute(text("""
                ALTER TABLE events
                ADD COLUMN IF NOT EXISTS response_ms INTEGER,
                ADD COLUMN IF NOT EXISTS prompt_chars INTEGER,
                ADD COLUMN IF NOT EXISTS answer_chars INTEGER,
                ADD COLUMN IF NOT EXISTS success INTEGER
            """))
            g.db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_events_response_ms ON events(response_ms) WHERE response_ms IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_events_success ON events(success) WHERE success IS NOT NULL;
            """))
            g.db.commit()
            print("✅ Database schema updated with performance analytics")
        
        return True
        
    except Exception as e:
        print(f"⚠️ Database schema update failed: {e}")
        if g.db:
            g.db.rollback()
        return False

def migrate_legacy_stats():
    """Migrate file-based stats to database if they exist"""
    if not hasattr(g, 'db') or g.db is None:
        return False
        
    try:
        # Ensure schema is up to date first
        ensure_database_schema()
        
        # Check if legacy stats table exists
        table_check = g.db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name='legacy_stats'
        """)).mappings().all()
        
        if not table_check:
            print("🔧 Creating legacy_stats table...")
            g.db.execute(text("""
                CREATE TABLE legacy_stats (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(64) UNIQUE NOT NULL,
                    value TEXT,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            g.db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_legacy_stats_key ON legacy_stats(key)
            """))
            g.db.commit()
        
        # Check if legacy stats file exists
        stats_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'stats.pkl')
        if not os.path.exists(stats_file):
            return False
            
        # Load legacy stats
        with open(stats_file, 'rb') as f:
            legacy_stats = pickle.load(f)
            
        # Check if already migrated
        existing = g.db.execute(text("SELECT COUNT(*) as count FROM legacy_stats")).mappings().one()
        if existing['count'] > 0:
            return False  # Already migrated
            
        # Migrate legacy stats to database
        for key, value in legacy_stats.items():
            if key == 'unique_visitors':
                # Convert set to list for JSON serialization
                value = list(value) if isinstance(value, set) else value
            
            g.db.execute(text("""
                INSERT INTO legacy_stats (key, value) 
                VALUES (:key, :value)
                ON CONFLICT (key) DO UPDATE SET 
                    value = EXCLUDED.value,
                    updated_at = NOW()
            """), {"key": key, "value": json.dumps(value) if not isinstance(value, str) else value})
            
        g.db.commit()
        print("✅ Successfully migrated legacy stats to database")
        return True
        
    except Exception as e:
        print(f"⚠️ Failed to migrate legacy stats: {e}")
        if g.db:
            g.db.rollback()
        return False

def track_visitor_location(ip_address, location_data):
    """Track visitor location in database"""
    if not hasattr(g, 'db') or g.db is None:
        return
        
    try:
        # Create location tracking event
        location_event = Event(
            type='visitor_location',
            sid=getattr(g, 'sid', None),
            ip=ip_address,
            location=location_data.get('location'),
            country=location_data.get('country'),
            lat=location_data.get('lat'),
            lng=location_data.get('lng'),
            meta=json.dumps(location_data)
        )
        g.db.add(location_event)
        g.db.commit()
        
    except Exception as e:
        print(f"⚠️ Failed to track visitor location: {e}")
        if g.db:
            g.db.rollback()

@bp.post("/api/analytics/event")
def collect_event():
    """Collect analytics events (pageviews, chat questions)"""
    data = request.get_json(silent=True) or {}
    typ = data.get("type")
    path = data.get("path") or None
    ref = data.get("ref") or None
    meta = data.get("meta")
    
    if meta and not isinstance(meta, str):
        # Store as small JSON string if provided
        try: 
            meta = json.dumps(meta)
        except Exception: 
            meta = None

    if typ not in ("pageview", "chat_question"):
        return jsonify({"error": "bad type"}), 400
    if path and len(path) > 2048:
        return jsonify({"error": "path too long"}), 400

    # Only proceed if database is available
    if not hasattr(g, 'db') or g.db is None:
        return jsonify({"ok": True})  # Silently succeed if no DB

    ev = Event(
        type=typ, 
        path=path, 
        ref=ref, 
        meta=meta,
        sid=getattr(g, "sid", None), 
        ip=getattr(g, "client_ip", None),
        ua=request.headers.get("User-Agent")
    )
    
    try:
        g.db.add(ev)
        g.db.commit()
        return jsonify({"ok": True})
    except Exception as e:
        g.db.rollback()
        return jsonify({"error": "database error"}), 500

@bp.get("/api/analytics/stats")
def stats():
    """Get comprehensive analytics statistics including visitor locations"""
    if not hasattr(g, 'db') or g.db is None:
        return jsonify({"error": "database not available"}), 503
        
    # Try to migrate legacy stats first
    try:
        migrate_legacy_stats()
    except Exception as e:
        print(f"⚠️ Legacy migration failed: {e}")
        # Reset transaction state
        g.db.rollback()
        
    try:
        days = int(request.args.get("days", 30))
    except Exception:
        days = 30
    
    db = g.db
    
    # Start fresh transaction
    try:
        db.rollback()  # Clear any previous transaction state
    except Exception:
        pass
    
    try:
        # Get totals (including legacy data)
        try:
            totals = db.execute(text("""
              with recent as (
                select * from events where ts >= now() - (:days || ' days')::interval
              )
              select
                (select count(*) from recent where type='pageview') as pageviews,
                (select count(distinct sid) from recent where type='pageview') as uniques,
                (select count(*) from recent where type='chat_question') as chat_questions,
                0 as legacy_ask_count,
                0 as legacy_visit_count,
                0 as legacy_unique_count
            """), {"days": days}).mappings().one()
            
            # Try to get legacy data separately to avoid JSON parsing issues
            try:
                legacy_data = db.execute(text("""
                  select key, value from legacy_stats 
                  where key in ('ask_count', 'visit_count', 'unique_visitors')
                """)).mappings().all()
                
                legacy_dict = {}
                for row in legacy_data:
                    try:
                        if row['key'] == 'unique_visitors':
                            # Handle JSON array for unique visitors
                            import json
                            visitors = json.loads(row['value'])
                            legacy_dict['legacy_unique_count'] = len(visitors) if isinstance(visitors, list) else 0
                        else:
                            # Handle simple integer values
                            legacy_dict[f"legacy_{row['key']}"] = int(row['value']) if row['value'].isdigit() else 0
                    except Exception as e:
                        print(f"⚠️ Error parsing legacy {row['key']}: {e}")
                        continue
                
                # Update totals with legacy data
                totals = dict(totals)
                totals.update(legacy_dict)
                
            except Exception as e:
                print(f"⚠️ Legacy data query failed: {e}")
                
        except Exception as e:
            print(f"⚠️ Main totals query failed: {e}")
            # Fallback to basic query
            totals = {
                'pageviews': 0, 'uniques': 0, 'chat_questions': 0,
                'legacy_ask_count': 0, 'legacy_visit_count': 0, 'legacy_unique_count': 0
            }

        # Get daily breakdown
        by_day = db.execute(text("""
          with recent as (
            select * from events where ts >= now() - (:days || ' days')::interval
          )
          select to_char(date_trunc('day', ts), 'YYYY-MM-DD') as day,
                 sum((type='pageview')::int) as pageviews,
                 sum((type='chat_question')::int) as chat_questions,
                 count(distinct case when type='pageview' then sid end) as uniques
          from recent
          group by 1
          order by 1 asc
        """), {"days": days}).mappings().all()

        # Get top pages
        top_pages = db.execute(text("""
          with recent as (
            select * from events where ts >= now() - (:days || ' days')::interval
          )
          select coalesce(path,'(none)') as path, count(*) as pageviews
          from recent where type='pageview'
          group by 1 order by 2 desc nulls last limit 10
        """), {"days": days}).mappings().all()

        # Get top referrers
        top_ref = db.execute(text("""
          with recent as (
            select * from events where ts >= now() - (:days || ' days')::interval
          )
          select coalesce(ref,'(direct)') as referrer, count(*) as visits
          from recent where type='pageview'
          group by 1 order by 2 desc nulls last limit 10
        """), {"days": days}).mappings().all()

        # Get visitor locations (handling case where location column doesn't exist yet)
        visitor_locations = []
        try:
            # Check if location column exists first
            column_check = db.execute(text("""
              SELECT column_name 
              FROM information_schema.columns 
              WHERE table_name='events' AND column_name='location'
            """)).mappings().all()
            
            if column_check:
                # Location column exists, use it
                visitor_locations = db.execute(text("""
                  select location, count(*) as count, 'db' as source
                  from events 
                  where type='visitor_location' and location is not null
                  group by location
                """)).mappings().all()
            else:
                print("📍 Location column not yet migrated - using legacy data only")
                
        except Exception as e:
            print(f"⚠️ Location query failed: {e}")
            # Reset transaction state
            db.rollback()
            
        # Always try to get legacy location data
        try:
            legacy_locations = db.execute(text("""
              select 
                locations.key as location,
                locations.value::integer as count,
                'legacy' as source
              from legacy_stats ls,
              json_each_text(cast(ls.value as json)) as locations(key, value)
              where ls.key = 'visitor_locations'
            """)).mappings().all()
            
            visitor_locations.extend(legacy_locations)
            
        except Exception as e:
            print(f"⚠️ Legacy location query failed: {e}")
            # Reset transaction state
            db.rollback()

        # Process visitor locations for heat map
        location_data = {}
        us_states = {}
        international_count = 0
        local_count = 0
        unknown_count = 0

        # Aggregate counts by location (combining db and legacy sources)
        location_totals = {}
        for row in visitor_locations:
            location = row['location']
            count = row.get('count', 0) or 0
            
            if location in location_totals:
                location_totals[location] += count
            else:
                location_totals[location] = count

        for location, total_count in location_totals.items():
            if total_count > 0:
                location_data[location] = total_count
                
                if location == 'Local':
                    local_count += total_count
                elif location == 'Unknown':
                    unknown_count += total_count
                elif location.startswith('International-'):
                    international_count += total_count
                elif len(location) == 2 and location.isalpha():  # US state codes
                    us_states[location.upper()] = total_count

        # Calculate combined totals (database + legacy)
        total_asks = (totals.get('chat_questions', 0) or 0) + (totals.get('legacy_ask_count', 0) or 0)
        total_visits = (totals.get('pageviews', 0) or 0) + (totals.get('legacy_visit_count', 0) or 0)
        total_uniques = (totals.get('uniques', 0) or 0) + (totals.get('legacy_unique_count', 0) or 0)

        # Get token usage analytics
        token_stats = {}
        try:
            # Check if token columns exist before querying
            token_column_check = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='events' AND column_name='openai_total_tokens'
            """)).mappings().all()
            
            if token_column_check:
                # Get token usage summary
                token_summary = db.execute(text("""
                    WITH recent AS (
                        SELECT * FROM events 
                        WHERE ts >= now() - (:days || ' days')::interval 
                        AND type='chat_question'
                        AND openai_total_tokens IS NOT NULL
                    )
                    SELECT 
                        COUNT(*) as queries_with_tokens,
                        SUM(openai_total_tokens) as total_tokens,
                        AVG(openai_total_tokens) as avg_tokens_per_query,
                        SUM(openai_prompt_tokens) as total_prompt_tokens,
                        SUM(openai_completion_tokens) as total_completion_tokens,
                        COUNT(DISTINCT model_used) as unique_models,
                        COUNT(DISTINCT api_provider) as unique_providers
                    FROM recent
                """), {"days": days}).mappings().one()
                
                # Get daily token usage
                daily_tokens = db.execute(text("""
                    WITH recent AS (
                        SELECT * FROM events 
                        WHERE ts >= now() - (:days || ' days')::interval 
                        AND type='chat_question'
                        AND openai_total_tokens IS NOT NULL
                    )
                    SELECT 
                        to_char(date_trunc('day', ts), 'YYYY-MM-DD') as day,
                        SUM(openai_total_tokens) as daily_tokens,
                        AVG(openai_total_tokens) as avg_tokens,
                        COUNT(*) as queries
                    FROM recent
                    GROUP BY date_trunc('day', ts)
                    ORDER BY day DESC
                    LIMIT 30
                """), {"days": days}).mappings().all()
                
                # Get model usage breakdown
                model_breakdown = db.execute(text("""
                    WITH recent AS (
                        SELECT * FROM events 
                        WHERE ts >= now() - (:days || ' days')::interval 
                        AND type='chat_question'
                        AND model_used IS NOT NULL
                    )
                    SELECT 
                        model_used,
                        api_provider,
                        COUNT(*) as usage_count,
                        SUM(openai_total_tokens) as total_tokens,
                        AVG(openai_total_tokens) as avg_tokens
                    FROM recent
                    GROUP BY model_used, api_provider
                    ORDER BY total_tokens DESC NULLS LAST
                    LIMIT 10
                """), {"days": days}).mappings().all()
                
                token_stats = {
                    "summary": dict(token_summary) if token_summary else {},
                    "daily_usage": [dict(d) for d in daily_tokens],
                    "model_breakdown": [dict(m) for m in model_breakdown],
                    "available": True
                }
            else:
                token_stats = {"available": False, "message": "Token tracking not yet available"}
                
        except Exception as e:
            print(f"⚠️ Token analytics query failed: {e}")
            db.rollback()
            token_stats = {"available": False, "error": str(e)}

        # Performance analytics
        performance = {}
        try:
            perf_col_check = db.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='events' AND column_name='response_ms'
            """ )).mappings().all()
            if perf_col_check:
                # summary
                perf_summary = db.execute(text("""
                    WITH recent AS (
                        SELECT * FROM events 
                        WHERE ts >= now() - (:days || ' days')::interval 
                          AND type='chat_question'
                          AND response_ms IS NOT NULL
                    )
                    SELECT 
                        COUNT(*) AS total_chats,
                        AVG(response_ms) AS avg_ms,
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY response_ms) AS p95_ms,
                        AVG(answer_chars) AS avg_answer_chars,
                        AVG(prompt_chars) AS avg_prompt_chars,
                        SUM(CASE WHEN success=1 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*),0) AS success_rate
                    FROM recent
                """), {"days": days}).mappings().one()
                
                # provider breakdown
                perf_by_provider = db.execute(text("""
                    WITH recent AS (
                        SELECT * FROM events 
                        WHERE ts >= now() - (:days || ' days')::interval 
                          AND type='chat_question'
                          AND response_ms IS NOT NULL
                    )
                    SELECT 
                        coalesce(api_provider,'unknown') AS provider,
                        COUNT(*) AS queries,
                        AVG(response_ms) AS avg_ms,
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY response_ms) AS p95_ms,
                        SUM(CASE WHEN success=1 THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*),0) AS success_rate,
                        AVG(answer_chars) AS avg_answer_chars
                    FROM recent
                    GROUP BY 1
                    ORDER BY queries DESC
                """), {"days": days}).mappings().all()
                
                # daily
                perf_daily = db.execute(text("""
                    WITH recent AS (
                        SELECT * FROM events 
                        WHERE ts >= now() - (:days || ' days')::interval 
                          AND type='chat_question'
                          AND response_ms IS NOT NULL
                    )
                    SELECT 
                        to_char(date_trunc('day', ts), 'YYYY-MM-DD') AS day,
                        AVG(response_ms) AS avg_ms,
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY response_ms) AS p95_ms,
                        COUNT(*) AS queries
                    FROM recent
                    GROUP BY date_trunc('day', ts)
                    ORDER BY day DESC
                    LIMIT 30
                """), {"days": days}).mappings().all()
                
                performance = {
                    "available": True,
                    "summary": dict(perf_summary) if perf_summary else {},
                    "by_provider": [dict(r) for r in perf_by_provider],
                    "daily": [dict(r) for r in perf_daily]
                }
            else:
                performance = {"available": False, "message": "Performance columns not available"}
        except Exception as e:
            print(f"⚠️ Performance analytics query failed: {e}")
            db.rollback()
            performance = {"available": False, "error": str(e)}

        # Get service start date
        try:
            service_start = db.execute(text("""
              select coalesce(
                (select min(ts) from events),
                now() - interval '30 days'
              ) as start_date
            """)).mappings().one()
        except Exception as e:
            print(f"⚠️ Service start date query failed: {e}")
            service_start = {'start_date': datetime.now()}

        return jsonify({
          "totals": {
            "pageviews": total_visits,
            "uniques": total_uniques,
            "chat_questions": total_asks,
            "ask_count": total_asks,  # For compatibility
            "visit_count": total_visits,  # For compatibility
            "unique_visitors": total_uniques  # For compatibility
          },
          "by_day": [dict(r) for r in by_day],
          "top_pages": [dict(r) for r in top_pages],
          "top_referrers": [dict(r) for r in top_ref],
          "visitor_locations": {
            "us_states": us_states,
            "international": international_count,
            "local": local_count,
            "unknown": unknown_count,
            "total_tracked": sum(location_data.values()),
            "raw_data": location_data  # For debugging
          },
          "service_info": {
            "first_visit": service_start['start_date'].isoformat() if service_start['start_date'] else None,
            "last_updated": datetime.now().isoformat(),
            "engagement_rate": (total_asks / max(total_visits, 1) * 100) if total_visits > 0 else 0,
            "questions_per_user": (total_asks / max(total_uniques, 1)) if total_uniques > 0 else 0
          },
          "token_usage": token_stats,
          "performance": performance
        })
        
    except Exception as e:
        print(f"❌ Analytics stats query failed: {e}")
        return jsonify({"error": "query failed", "details": str(e)}), 500


@bp.get("/api/analytics/timeline")
def timeline():
    """Get question timeline with cache performance and token usage"""
    if not hasattr(g, 'db') or g.db is None:
        return jsonify({"error": "database not available"}), 503
    
    db = g.db
    
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))
        cache_mode = request.args.get("cache_mode")  # 'exact_hit', 'semantic_hit', 'miss'
    except Exception:
        limit, offset, cache_mode = 50, 0, None
    
    try:
        # Build query with optional cache_mode filter
        query = """
            SELECT 
                id,
                ts as timestamp,
                COALESCE(meta::json->>'question', path) as question,
                COALESCE(meta::json->>'question_hash', '') as question_hash,
                COALESCE(meta::json->>'cache_hit', 'miss') as cache_mode,
                COALESCE((meta::json->>'semantic_similarity')::float, 0) as semantic_similarity,
                COALESCE(LEFT(meta::json->>'answer', 200), '') as answer_preview,
                COALESCE(meta::json->>'answer', '') as full_answer,
                COALESCE((meta::json->>'citations_count')::int, 0) as citations_count,
                COALESCE(meta::json->'token_usage', '{}') as token_usage,
                COALESCE(response_ms, 0) as latency_ms,
                COALESCE((meta::json->>'retrieved_docs')::int, 0) as retrieved_docs,
                COALESCE((meta::json->>'compressed_tokens')::int, 0) as compressed_tokens,
                COALESCE((meta::json->>'final_tokens')::int, 0) as final_tokens,
                COALESCE(ip, 'unknown') as user_ip,
                COALESCE(meta::json->>'error', '') as error_message,
                ts as created_at
            FROM events 
            WHERE type = 'chat_question'
        """
        
        params = {"limit": limit, "offset": offset}
        
        if cache_mode and cache_mode != 'all':
            query += " AND COALESCE(meta::json->>'cache_hit', 'miss') = :cache_mode"
            params["cache_mode"] = cache_mode
        
        query += " ORDER BY ts DESC LIMIT :limit OFFSET :offset"
        
        entries = db.execute(text(query), params).mappings().all()
        
        # Get stats for the last 24 hours
        stats_query = """
            SELECT 
                COUNT(*) as total_questions,
                SUM(CASE WHEN COALESCE(meta::json->>'cache_hit', 'miss') = 'exact' THEN 1 ELSE 0 END) as exact_hits,
                SUM(CASE WHEN COALESCE(meta::json->>'cache_hit', 'miss') = 'semantic' THEN 1 ELSE 0 END) as semantic_hits,
                SUM(CASE WHEN COALESCE(meta::json->>'cache_hit', 'miss') = 'miss' THEN 1 ELSE 0 END) as cache_misses,
                AVG(COALESCE(response_ms, 0)) as avg_latency,
                SUM(COALESCE(openai_total_tokens, 0)) as total_tokens_used,
                AVG(COALESCE((meta::json->>'semantic_similarity')::float, 0)) as avg_similarity
            FROM events 
            WHERE type = 'chat_question' 
            AND ts >= NOW() - INTERVAL '24 hours'
        """
        
        stats_result = db.execute(text(stats_query)).mappings().one()
        
        total_q = stats_result['total_questions'] or 0
        exact_h = stats_result['exact_hits'] or 0
        semantic_h = stats_result['semantic_hits'] or 0
        
        cache_hit_rate = ((exact_h + semantic_h) / total_q * 100) if total_q > 0 else 0
        
        # Hourly breakdown for the last 24 hours
        hourly_query = """
            SELECT 
                TO_CHAR(DATE_TRUNC('hour', ts), 'HH24:00') as hour,
                COUNT(*) as questions,
                SUM(CASE WHEN COALESCE(meta::json->>'cache_hit', 'miss') != 'miss' THEN 1 ELSE 0 END) as hits
            FROM events 
            WHERE type = 'chat_question' 
            AND ts >= NOW() - INTERVAL '24 hours'
            GROUP BY DATE_TRUNC('hour', ts)
            ORDER BY DATE_TRUNC('hour', ts)
        """
        
        hourly = db.execute(text(hourly_query)).mappings().all()
        
        # Format entries for response
        formatted_entries = []
        for entry in entries:
            formatted_entry = {
                "id": entry['id'],
                "timestamp": entry['timestamp'].isoformat() if entry['timestamp'] else None,
                "question": entry['question'] or "",
                "question_hash": entry['question_hash'] or "",
                "cache_mode": entry['cache_mode'] or "miss",
                "semantic_similarity": float(entry['semantic_similarity'] or 0),
                "answer_preview": entry['answer_preview'] or "",
                "full_answer": entry['full_answer'] or "",
                "citations_count": int(entry['citations_count'] or 0),
                "token_usage": entry['token_usage'] if isinstance(entry['token_usage'], dict) else {},
                "latency_ms": int(entry['latency_ms'] or 0),
                "retrieved_docs": int(entry['retrieved_docs'] or 0),
                "compressed_tokens": int(entry['compressed_tokens'] or 0),
                "final_tokens": int(entry['final_tokens'] or 0),
                "user_ip": entry['user_ip'] or "unknown",
                "error_message": entry['error_message'] or "",
                "created_at": entry['created_at'].isoformat() if entry['created_at'] else None
            }
            formatted_entries.append(formatted_entry)
        
        return jsonify({
            "status": "ok",
            "entries": formatted_entries,
            "stats": {
                "total_questions": int(stats_result['total_questions'] or 0),
                "exact_hits": int(exact_h),
                "semantic_hits": int(semantic_h),
                "cache_misses": int(stats_result['cache_misses'] or 0),
                "cache_hit_rate": round(cache_hit_rate, 1),
                "avg_latency": round(float(stats_result['avg_latency'] or 0), 1),
                "total_tokens_used": int(stats_result['total_tokens_used'] or 0),
                "avg_similarity": round(float(stats_result['avg_similarity'] or 0), 3),
                "hourly_breakdown": [dict(h) for h in hourly]
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total_returned": len(formatted_entries)
            }
        })
        
    except Exception as e:
        print(f"❌ Timeline query failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "query failed", "details": str(e)}), 500


@bp.delete("/api/analytics/timeline/<int:event_id>")
def delete_timeline_event(event_id: int):
    """Delete a specific question/event from the timeline"""
    if not _admin_ok():
        return jsonify({"error": "admin token required"}), 401
    
    if not hasattr(g, 'db') or g.db is None:
        return jsonify({"error": "database not available"}), 503
    
    db = g.db
    
    try:
        # First verify the event exists and is a chat_question
        result = db.execute(text("""
            SELECT id FROM events 
            WHERE id = :event_id AND type = 'chat_question'
        """), {"event_id": event_id}).mappings().first()
        
        if not result:
            return jsonify({"error": "Event not found"}), 404
        
        # Delete the event
        db.execute(text("""
            DELETE FROM events WHERE id = :event_id
        """), {"event_id": event_id})
        db.commit()
        
        print(f"🗑️ Deleted event {event_id}")
        return jsonify({"success": True, "deleted_id": event_id})
        
    except Exception as e:
        print(f"❌ Delete event failed: {e}")
        db.rollback()
        return jsonify({"error": "delete failed", "details": str(e)}), 500


@bp.get("/admin/analytics")
def admin_page():
    """Admin analytics dashboard - serve React SPA"""
    from flask import send_from_directory
    import os
    
    # Check admin token
    if not _admin_ok(): 
        abort(401)
    
    # Try to serve the SPA first (React will handle the admin analytics route)
    frontend_build_dir = os.getenv(
        "FRONTEND_BUILD_DIR",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
    )
    
    try:
        index_path = os.path.join(frontend_build_dir, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(frontend_build_dir, "index.html")
    except Exception:
        pass
    
    # Fallback: Simple redirect message with React component info
    return f"""
    <!doctype html><meta charset="utf-8">
    <title>Admin Analytics Dashboard</title>
    <style>
      body{{font-family:system-ui,-apple-system,sans-serif;padding:40px;max-width:600px;margin:auto;text-align:center}}
      .container{{background:#f8f9fa;padding:40px;border-radius:12px;margin:40px 0}}
      .success{{color:#28a745;font-size:18px;margin:20px 0}}
      .info{{color:#6c757d;margin:15px 0}}
      .token{{background:#e9ecef;padding:8px 12px;border-radius:4px;font-family:monospace;word-break:break-all}}
    </style>
    
    <div class="container">
      <h1>✅ Admin Access Verified</h1>
      <p class="success">Your admin token is valid!</p>
      
      <div class="info">
        <p><strong>React SPA Not Available</strong></p>
        <p>The React-based admin analytics dashboard requires the SPA build.</p>
        <p>Please build and deploy the frontend to access the full dashboard.</p>
      </div>
      
      <div class="info">
        <p><strong>Your Admin Token:</strong></p>
        <div class="token">{request.args.get('token', 'Not found')}</div>
      </div>
      
      <div class="info">
        <p>You can access the basic API stats at:</p>
        <a href="/api/analytics/stats?token={request.args.get('token', '')}" target="_blank">
          /api/analytics/stats
        </a>
      </div>
      
      <div style="margin-top:30px">
        <a href="/" style="text-decoration:none;background:#007bff;color:white;padding:10px 20px;border-radius:6px">
          ← Back to Home
        </a>
      </div>
    </div>
    """
