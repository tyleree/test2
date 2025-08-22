import os
import json
from flask import Blueprint, request, g, abort, jsonify
from sqlalchemy import text
from models import Event

bp = Blueprint("analytics", __name__, url_prefix="")

def _admin_ok():
    """Check if admin token is valid"""
    token = os.getenv("ADMIN_TOKEN", "")
    given = request.args.get("token") or request.headers.get("X-Admin-Token")
    return token and given == token

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
    """Get analytics statistics"""
    if not hasattr(g, 'db') or g.db is None:
        return jsonify({"error": "database not available"}), 503
        
    try:
        days = int(request.args.get("days", 30))
    except Exception:
        days = 30
    
    db = g.db
    
    try:
        # Get totals
        totals = db.execute(text("""
          with recent as (
            select * from events where ts >= now() - (:days || ' days')::interval
          )
          select
            (select count(*) from recent where type='pageview') as pageviews,
            (select count(distinct sid) from recent where type='pageview') as uniques,
            (select count(*) from recent where type='chat_question') as chat_questions
        """), {"days": days}).mappings().one()

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

        return jsonify({
          "totals": dict(totals),
          "by_day": [dict(r) for r in by_day],
          "top_pages": [dict(r) for r in top_pages],
          "top_referrers": [dict(r) for r in top_ref],
        })
        
    except Exception as e:
        return jsonify({"error": "query failed"}), 500

@bp.get("/admin/analytics")
def admin_page():
    """Admin analytics dashboard"""
    if not _admin_ok(): 
        abort(401)
    
    # Simple self-contained HTML (no external CDNs, no eval)
    return """
    <!doctype html><meta charset="utf-8">
    <title>Analytics Dashboard</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;padding:20px;max-width:980px;margin:auto;background:#f8f9fa}
      h1,h2{margin:0 0 12px;color:#333} 
      table{border-collapse:collapse;width:100%;margin:12px 0;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 4px rgba(0,0,0,0.1)}
      th,td{border:1px solid #ddd;padding:12px;text-align:left} 
      th{background:#f1f3f5;font-weight:600}
      .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:20px 0}
      .card{border:1px solid #e9ecef;border-radius:12px;padding:20px;background:#fff;box-shadow:0 2px 8px rgba(0,0,0,0.05)}
      .big{font-size:32px;font-weight:700;color:#495057;margin-top:8px}
      .label{font-size:14px;color:#6c757d;font-weight:500}
      .loading{color:#6c757d;font-style:italic}
      .error{color:#dc3545;background:#f8d7da;padding:12px;border-radius:6px;margin:12px 0}
    </style>
    
    <h1>📊 Site Analytics</h1>
    
    <div class="cards">
      <div class="card">
        <div class="label">Total Pageviews</div>
        <div id="pv" class="big loading">Loading...</div>
      </div>
      <div class="card">
        <div class="label">Unique Visitors</div>
        <div id="uv" class="big loading">Loading...</div>
      </div>
      <div class="card">
        <div class="label">Chat Questions</div>
        <div id="cq" class="big loading">Loading...</div>
      </div>
    </div>

    <div id="error-msg" class="error" style="display:none"></div>

    <h2>📈 Daily Breakdown</h2>
    <table id="daily">
      <thead>
        <tr><th>Date</th><th>Pageviews</th><th>Uniques</th><th>Chat Questions</th></tr>
      </thead>
      <tbody>
        <tr><td colspan="4" class="loading">Loading daily data...</td></tr>
      </tbody>
    </table>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px">
      <div>
        <h2>📄 Top Pages</h2>
        <table id="pages">
          <thead>
            <tr><th>Path</th><th>Views</th></tr>
          </thead>
          <tbody>
            <tr><td colspan="2" class="loading">Loading pages...</td></tr>
          </tbody>
        </table>
      </div>

      <div>
        <h2>🔗 Top Referrers</h2>
        <table id="refs">
          <thead>
            <tr><th>Referrer</th><th>Visits</th></tr>
          </thead>
          <tbody>
            <tr><td colspan="2" class="loading">Loading referrers...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <script>
      function showError(msg) {
        const errorEl = document.getElementById('error-msg');
        errorEl.textContent = 'Error: ' + msg;
        errorEl.style.display = 'block';
      }
      
      function formatNumber(num) {
        return new Intl.NumberFormat().format(num || 0);
      }
      
      fetch('/api/analytics/stats?days=30').then(r => {
        if (!r.ok) throw new Error('Failed to fetch stats');
        return r.json();
      }).then(d => {
        // Update totals
        document.getElementById('pv').textContent = formatNumber(d.totals.pageviews);
        document.getElementById('uv').textContent = formatNumber(d.totals.uniques);
        document.getElementById('cq').textContent = formatNumber(d.totals.chat_questions);

        // Update daily table
        const daily = document.querySelector('#daily tbody');
        daily.innerHTML = '';
        if (d.by_day.length === 0) {
          daily.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#6c757d">No data available</td></tr>';
        } else {
          d.by_day.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td>' + r.day + '</td><td>' + formatNumber(r.pageviews) + '</td><td>' + formatNumber(r.uniques) + '</td><td>' + formatNumber(r.chat_questions) + '</td>';
            daily.appendChild(tr);
          });
        }

        // Update pages table
        const pages = document.querySelector('#pages tbody');
        pages.innerHTML = '';
        if (d.top_pages.length === 0) {
          pages.innerHTML = '<tr><td colspan="2" style="text-align:center;color:#6c757d">No pages tracked</td></tr>';
        } else {
          d.top_pages.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td>' + (r.path || '(none)') + '</td><td>' + formatNumber(r.pageviews) + '</td>';
            pages.appendChild(tr);
          });
        }

        // Update referrers table
        const refs = document.querySelector('#refs tbody');
        refs.innerHTML = '';
        if (d.top_referrers.length === 0) {
          refs.innerHTML = '<tr><td colspan="2" style="text-align:center;color:#6c757d">No referrers tracked</td></tr>';
        } else {
          d.top_referrers.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td>' + (r.referrer || '(direct)') + '</td><td>' + formatNumber(r.visits) + '</td>';
            refs.appendChild(tr);
          });
        }
      }).catch(err => {
        showError(err.message);
        // Reset loading states
        document.getElementById('pv').textContent = 'Error';
        document.getElementById('uv').textContent = 'Error';
        document.getElementById('cq').textContent = 'Error';
      });
    </script>
    """
