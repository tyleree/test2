from flask import Flask, render_template, request, jsonify, send_from_directory, g, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from threading import Lock
from pinecone import Pinecone
import os
from dotenv import load_dotenv
import requests
import json
import pickle
from datetime import datetime
import threading
import uuid

# Load environment variables
load_dotenv('env.txt')  # Using env.txt since .env is blocked

app = Flask(__name__)

# Set SECRET_KEY for sessions
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-change-in-production")

# Initialize database (gracefully handle missing DATABASE_URL)
try:
    from db import Base, engine, SessionLocal, DATABASE_URL
    from models import Event
    from analytics import bp as analytics_bp
    
    # Check if we have a valid database connection
    if engine and DATABASE_URL:
        DATABASE_AVAILABLE = True
        print("📊 Database connection established")
    else:
        DATABASE_AVAILABLE = False
        print("⚠️ DATABASE_URL not found - analytics will be disabled")
        
except Exception as e:
    print(f"⚠️ Database initialization failed: {e} - analytics will be disabled")
    DATABASE_AVAILABLE = False
    SessionLocal = None
    analytics_bp = None

# Initialize intelligent rate limiter (per-IP)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1000 per day", "100 per hour"],  # base per-IP guards
    storage_uri="memory://",  # swap to Redis in production: redis://host:6379
    strategy="fixed-window",
)

# Suspicious behavior tracking (in-memory)
suspicious_ips = {}
suspicious_lock = Lock()

def is_suspicious_request(ip_address: str, prompt: str):
    """Heuristics to flag abusive patterns for temporary throttling."""
    from datetime import datetime, timedelta
    now = datetime.now()
    with suspicious_lock:
        data = suspicious_ips.setdefault(ip_address, {
            "requests": [],
            "short_prompts": 0,
            "identical_prompts": [],
            "last_prompt": None,
            "last_request_time": None,
        })

        # Keep only last hour of requests
        data["requests"] = [t for t in data["requests"] if now - t < timedelta(hours=1)]
        data["requests"].append(now)

        # Burst detection: >5 in 60s
        recent_min = [t for t in data["requests"] if now - t < timedelta(minutes=1)]
        if len(recent_min) > 5:
            return True, "Burst requests detected"

        # Very short prompts: <5 chars repeatedly
        if len((prompt or "").strip()) < 5:
            data["short_prompts"] += 1
            if data["short_prompts"] > 3:
                return True, "Too many short prompts"

        # Identical prompts repeated within 10 minutes
        if data["last_prompt"] == prompt:
            data["identical_prompts"].append(now)
            data["identical_prompts"] = [t for t in data["identical_prompts"] if now - t < timedelta(minutes=10)]
            if len(data["identical_prompts"]) > 2:
                return True, "Identical prompts repeated"

        data["last_prompt"] = prompt
        data["last_request_time"] = now
        return False, ""

def get_rate_limit_for_ip(ip_address: str) -> str:
    """Dynamic per-IP limit; tightens if heavy recent usage detected."""
    from datetime import datetime, timedelta
    now = datetime.now()
    with suspicious_lock:
        data = suspicious_ips.get(ip_address)
        if data:
            recent_hour = [t for t in data.get("requests", []) if now - t < timedelta(hours=1)]
            if len(recent_hour) > 20:
                return "5 per hour"
            if len(recent_hour) > 10:
                return "15 per hour"
    # Normal users get generous limit to support ~5000/day aggregate
    return "250 per hour"

# Persistent counters with file-based storage
STATS_FILE = os.path.join(os.path.dirname(__file__), 'stats.pkl')
stats_lock = Lock()

def load_stats():
    """Load statistics from file"""
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'rb') as f:
                stats = pickle.load(f)
                return stats
    except Exception as e:
        print(f"Warning: Could not load stats file: {e}")
    
    # Return default stats if file doesn't exist or can't be loaded
    return {
        'ask_count': 0,
        'visit_count': 0,
        'unique_visitors': set(),
        'visitor_locations': {},  # {'state_code': count}
        'first_visit': datetime.now().isoformat(),
        'last_updated': datetime.now().isoformat()
    }

def save_stats(stats):
    """Save statistics to file"""
    try:
        stats['last_updated'] = datetime.now().isoformat()
        with open(STATS_FILE, 'wb') as f:
            pickle.dump(stats, f)
    except Exception as e:
        print(f"Error saving stats: {e}")

def get_real_ip():
    """Get the real client IP address, accounting for proxies and load balancers"""
    # Check various headers that proxies might use
    headers_to_check = [
        'X-Forwarded-For',
        'X-Real-IP', 
        'X-Client-IP',
        'CF-Connecting-IP',  # Cloudflare
        'True-Client-IP',
        'HTTP_X_FORWARDED_FOR',
        'HTTP_X_REAL_IP'
    ]
    
    for header in headers_to_check:
        ip = request.headers.get(header)
        if ip:
            # X-Forwarded-For can contain multiple IPs, take the first one
            if ',' in ip:
                ip = ip.split(',')[0].strip()
            print(f"🔍 Found IP in header {header}: {ip}")
            return ip
    
    # Fallback to remote_addr
    ip = request.remote_addr
    print(f"🔍 Using remote_addr: {ip}")
    return ip

def get_location_from_ip(ip_address):
    """Get location (state) from IP address using free ipapi service"""
    print(f"🌍 Getting location for IP: {ip_address}")
    
    # Check for local/private IPs
    if (ip_address in ['127.0.0.1', 'localhost', '::1'] or 
        ip_address.startswith('192.168.') or 
        ip_address.startswith('10.') or 
        ip_address.startswith('172.')):
        print(f"🏠 Local/private IP detected: {ip_address}")
        return 'Local'
    
    try:
        # Try multiple geolocation services for better reliability
        services = [
            {
                'name': 'ipapi.co',
                'url': f'http://ipapi.co/{ip_address}/json/',
                'region_key': 'region_code',
                'country_key': 'country_code'
            },
            {
                'name': 'ip-api.com',
                'url': f'http://ip-api.com/json/{ip_address}',
                'region_key': 'region',
                'country_key': 'countryCode'
            }
        ]
        
        for service in services:
            try:
                print(f"🔍 Querying {service['name']} for IP: {ip_address}")
                response = requests.get(service['url'], timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"📊 {service['name']} response: {data}")
                    
                    # Handle different API response formats
                    if service['name'] == 'ip-api.com' and data.get('status') == 'fail':
                        print(f"❌ {service['name']} failed: {data.get('message', 'Unknown error')}")
                        continue
                    
                    region = data.get(service['region_key'], 'Unknown')
                    country = data.get(service['country_key'], '')
                    city = data.get('city', '')
                    
                    # Only track US states
                    if country == 'US' and region:
                        print(f"🇺🇸 US location found: {region} ({city})")
                        return region
                    elif country and country != 'US':
                        print(f"🌍 International location: {country}")
                        return f'International-{country}'
                    else:
                        print(f"❓ Unknown location: country={country}, region={region}")
                        continue  # Try next service
                else:
                    print(f"❌ {service['name']} API error: {response.status_code}")
                    continue
                    
            except Exception as e:
                print(f"❌ Error with {service['name']}: {e}")
                continue
        
        # If all services failed
        print(f"❌ All geolocation services failed for IP: {ip_address}")
        return 'Unknown'
            
    except Exception as e:
        print(f"❌ Error getting location for IP {ip_address}: {e}")
        return 'Unknown'

def track_visitor_location_async(ip_address, stats):
    """Track visitor location asynchronously to avoid blocking requests"""
    def _track():
        location = get_location_from_ip(ip_address)
        with stats_lock:
            current_stats = app.config['STATS']
            if 'visitor_locations' not in current_stats:
                current_stats['visitor_locations'] = {}
            
            current_stats['visitor_locations'][location] = current_stats['visitor_locations'].get(location, 0) + 1
            save_stats(current_stats)
            app.config['STATS'] = current_stats
    
    # Run in background thread to avoid blocking the request
    thread = threading.Thread(target=_track)
    thread.daemon = True
    thread.start()

# Initialize stats
app.config['STATS'] = load_stats()

# Ensure visitor_locations field exists (for backward compatibility)
if 'visitor_locations' not in app.config['STATS']:
    app.config['STATS']['visitor_locations'] = {}
    save_stats(app.config['STATS'])

print(f"📊 Loaded stats: Ask count={app.config['STATS']['ask_count']}, Visit count={app.config['STATS']['visit_count']}")

# Legacy compatibility
ask_count_lock = stats_lock

# Register analytics blueprint if available
if analytics_bp:
    app.register_blueprint(analytics_bp)
    if DATABASE_AVAILABLE:
        print("📈 Analytics blueprint registered with database support")
    else:
        print("📈 Analytics blueprint registered (database not available)")
else:
    print("⚠️ Analytics blueprint not available")

# Initialize database tables on first request
def init_db():
    """Initialize database tables if available"""
    if DATABASE_AVAILABLE:
        try:
            Base.metadata.create_all(bind=engine)
            print("📊 Database tables initialized")
        except Exception as e:
            print(f"⚠️ Database table initialization failed: {e}")

# Call init_db on startup instead of using deprecated before_first_request
if DATABASE_AVAILABLE:
    init_db()

def client_ip(request):
    """Helper to get client IP respecting X-Forwarded-For"""
    xf = request.headers.get("X-Forwarded-For", "")
    return (xf.split(",")[0].strip() if xf else request.remote_addr) or ""

@app.before_request
def open_session():
    """Initialize database session and session ID for each request"""
    # Initialize database session if available
    if DATABASE_AVAILABLE and SessionLocal:
        g.db = SessionLocal()
    else:
        g.db = None
    
    # Handle session ID cookie
    sid = request.cookies.get("sid")
    if not sid:
        sid = uuid.uuid4().hex
        g._set_sid_cookie = sid
    g.sid = sid
    
    # Store client IP
    g.client_ip = client_ip(request)

@app.after_request
def set_headers(resp):
    """Set security headers and session cookie"""
    # Set strict Content Security Policy (no unsafe-eval)
    csp = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'; "
           "base-uri 'self'; form-action 'self'")
    resp.headers.setdefault("Content-Security-Policy", csp)
    
    # Set session ID cookie if needed
    if getattr(g, "_set_sid_cookie", None):
        resp.set_cookie(
            "sid", g._set_sid_cookie,
            httponly=True, samesite="Lax", 
            secure=request.is_secure, path="/"
        )
    
    return resp

@app.teardown_request
def close_session(exc):
    """Clean up database session"""
    db = getattr(g, 'db', None)
    if db is not None:
        if exc: 
            db.rollback()
        db.close()

def log_chat_question():
    """Log a chat question event to analytics"""
    if not DATABASE_AVAILABLE or not hasattr(g, 'db') or g.db is None:
        return
    
    try:
        ev = Event(
            type='chat_question',
            path=request.path,
            sid=getattr(g, 'sid', None),
            ip=getattr(g, 'client_ip', None),
            ua=request.headers.get('User-Agent')
        )
        g.db.add(ev)
        g.db.commit()
    except Exception as e:
        print(f"⚠️ Failed to log chat question: {e}")
        if g.db:
            g.db.rollback()

# Optional SPA build directory (for serving a built frontend)
FRONTEND_BUILD_DIR = os.getenv(
    "FRONTEND_BUILD_DIR",
    os.path.join(os.path.dirname(__file__), "frontend", "dist")
)

# Initialize Pinecone MCP Assistant
try:
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    # Use your existing MCP assistant
    assistant = pc.assistant.Assistant(assistant_name="vb")
    app.config['PINECONE_ASSISTANT'] = assistant
    print("✅ Pinecone MCP Assistant 'vb' connected successfully")
    
    # Also try to get the index for additional functionality
    try:
        index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "veterans-benefits"))
        app.config['PINECONE_INDEX'] = index
        print(f"✅ Pinecone Index '{os.getenv('PINECONE_INDEX_NAME', 'veterans-benefits')}' connected successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not connect to Pinecone index: {e}")
        index = None
        
except Exception as e:
    print(f"❌ Error initializing Pinecone MCP Assistant: {e}")
    assistant = None
    index = None

# MCP Server configuration (kept as fallback)
MCP_SERVER_URL = "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb"
MCP_API_KEY = os.getenv("PINECONE_API_KEY")

# OpenAI configuration for direct queries
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def call_mcp_server(prompt, options=None):
    """
    Clean JSON-based call to the MCP server endpoint
    
    Args:
        prompt (str): The user's question/prompt
        options (dict): Optional parameters like temperature, max_tokens, etc.
    
    Returns:
        dict: Clean JSON response with content and metadata
    """
    try:
        headers = {
            "Authorization": f"Bearer {MCP_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "VeteransBenefitsAssistant/1.0"
        }
        
        # Build the payload with clean JSON structure
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "include_highlights": True,
            "stream": False
        }
        
        # Add any additional options
        if options:
            payload.update(options)
        
        print(f"🔗 Calling MCP server: {MCP_SERVER_URL}")
        print(f"📝 Prompt: {prompt[:100]}...")
        
        response = requests.post(
            f"{MCP_SERVER_URL}/chat",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        print(f"📡 MCP Server response status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"✅ MCP Server response received successfully")
            return {
                "success": True,
                "data": response_data,
                "status_code": 200
            }
        elif response.status_code == 401:
            print("❌ MCP Server authentication failed - check API key")
            return {
                "success": False,
                "error": "Authentication failed",
                "code": 401,
                "message": "Invalid or missing API key"
            }
        elif response.status_code == 429:
            print("⚠️ MCP Server rate limit exceeded")
            return {
                "success": False,
                "error": "Rate limit exceeded",
                "code": 429,
                "message": "Too many requests, please try again later"
            }
        else:
            print(f"❌ MCP Server error: {response.status_code} - {response.text}")
            return {
                "success": False,
                "error": f"Server error: {response.status_code}",
                "code": response.status_code,
                "message": response.text
            }
            
    except requests.exceptions.Timeout:
        print("⏰ MCP Server request timed out")
        return {
            "success": False,
            "error": "Request timeout",
            "code": "timeout",
            "message": "Request took too long to complete"
        }
    except requests.exceptions.ConnectionError:
        print("🔌 MCP Server connection error")
        return {
            "success": False,
            "error": "Connection error",
            "code": "connection",
            "message": "Unable to connect to MCP server"
        }
    except Exception as e:
        print(f"❌ Error calling MCP server: {e}")
        return {
            "success": False,
            "error": str(e),
            "code": "unknown",
            "message": "An unexpected error occurred"
        }

def process_mcp_response(mcp_response):
    """
    Process and format MCP server response with clean JSON structure
    
    Args:
        mcp_response (dict): Response from call_mcp_server function
    
    Returns:
        tuple: (content, citations, metadata) or (None, None, None) if error
    """
    if not mcp_response or not mcp_response.get("success"):
        return None, None, None
    
    try:
        response_data = mcp_response.get("data", {})
        content = ""
        citations = []
        metadata = {}
        
        # Extract content from various possible response formats
        if "message" in response_data:
            content = response_data["message"].get("content", "")
        elif "content" in response_data:
            content = response_data["content"]
        elif "response" in response_data:
            content = response_data["response"]
        elif "choices" in response_data and response_data["choices"]:
            # Handle OpenAI-style responses
            content = response_data["choices"][0].get("message", {}).get("content", "")
        
        # Extract citations if available
        if "citations" in response_data and response_data["citations"]:
            for citation in response_data["citations"]:
                try:
                    # Extract source text from various possible fields
                    source_text = ""
                    if citation.get("text"):
                        source_text = citation.get("text")
                    elif citation.get("content"):
                        source_text = citation.get("content")
                    elif citation.get("snippet"):
                        source_text = citation.get("snippet")
                    elif citation.get("highlight"):
                        source_text = citation.get("highlight")
                    
                    # Clean up source text
                    if source_text:
                        source_text = source_text.strip()
                        if len(source_text) > 500:  # Limit to 500 characters
                            source_text = source_text[:500] + "..."
                    
                    # Prefer explicit source_url if provided, then url, then nested file.signed_url
                    file_obj = citation.get("file", {}) or {}
                    source_url = (
                        citation.get("source_url")
                        or citation.get("url")
                        or file_obj.get("signed_url")
                        or "#"
                    )

                    citation_data = {
                        "file": file_obj.get("name", "Unknown"),
                        "page": citation.get("page", 1),
                        "url": citation.get("url", "#"),
                        "source_url": source_url,
                        "source_text": source_text,
                        "confidence": citation.get("confidence", 0.0)
                    }
                    citations.append(citation_data)
                except Exception as e:
                    print(f"Error processing citation: {e}")
                    continue
        
        # Extract metadata
        metadata = {
            "model": response_data.get("model", "unknown"),
            "usage": response_data.get("usage", {}),
            "created": response_data.get("created"),
            "id": response_data.get("id"),
            "response_time": mcp_response.get("response_time")
        }
        
        return content, citations, metadata
        
    except Exception as e:
        print(f"Error processing MCP response: {e}")
        return None, None, None


def query_direct_pinecone(prompt, index):
    """
    Query Pinecone index directly using OpenAI embeddings and GPT-4
    
    Args:
        prompt (str): User's question
        index: Pinecone index object
        
    Returns:
        dict: Response with content, citations, and metadata
    """
    try:
        from openai import OpenAI
        
        # Initialize OpenAI client with proper v1.0+ syntax
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        print(f"🔍 Generating embedding for query: {prompt[:50]}...")
        
        # Generate embedding for the user's question
        # Note: Using text-embedding-ada-002 which produces 1536 dims, but we need to truncate to 1024
        # or use a different model that matches your index dimensions
        embed_response = client.embeddings.create(
            model="text-embedding-3-small",
            input=prompt,
            dimensions=1024  # Truncate to match your index
        )
        query_vector = embed_response.data[0].embedding
        
        print(f"📊 Querying Pinecone index with {len(query_vector)}-dimensional vector...")
        
        # Query Pinecone index
        results = index.query(
            vector=query_vector,
            top_k=5,
            include_metadata=True
        )
        
        if not results.matches:
            print("⚠️ No matches found in Pinecone index")
            return None
            
        print(f"✅ Found {len(results.matches)} matches")
        for i, match in enumerate(results.matches):
            print(f"  Match {i+1}: Score={match.score:.4f}, ID={match.id}, Metadata keys={list(match.metadata.keys()) if match.metadata else 'None'}")
        
        # Build context from top matches
        context_chunks = []
        context_text_parts = []
        
        for i, match in enumerate(results.matches):
            if match.score > 0.02:  # Lower threshold for this index (scores seem to be lower)
                # Extract text content from different possible fields
                chunk_text = (
                    match.metadata.get('context', '') or 
                    match.metadata.get('text', '') or 
                    match.metadata.get('preview', '')
                )
                
                heading = match.metadata.get('heading', '')
                source_url = match.metadata.get('source_url', 'https://veteransbenefitskb.com')  # Default source
                
                if chunk_text:
                    context_chunks.append({
                        'text': chunk_text,
                        'source_url': source_url,
                        'score': match.score,
                        'rank': i + 1,
                        'heading': heading
                    })
                    
                    # Include heading in context if available
                    context_part = f"Section: {heading}\n{chunk_text}" if heading else chunk_text
                    context_text_parts.append(f"Source {i+1}: {context_part}")
        
        if not context_chunks:
            print("⚠️ No relevant chunks found (all below threshold)")
            print(f"  Threshold: 0.02, Best score: {max(match.score for match in results.matches) if results.matches else 'N/A'}")
            return None
            
        # Limit context to top 3 chunks to avoid token limits
        context_text = '\n\n'.join(context_text_parts[:3])
        
        print(f"🤖 Generating answer with GPT-4 using {len(context_chunks)} context chunks...")
        
        # Generate answer using GPT-4
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system", 
                    "content": """You are a Veterans Benefits AI assistant. Answer questions based only on the provided context from the 38 CFR (Code of Federal Regulations). 

Instructions:
- Be accurate and cite your sources
- Only use information from the provided context
- If the context doesn't contain enough information, say so
- Provide detailed, helpful answers
- Use a professional but friendly tone"""
                },
                {
                    "role": "user", 
                    "content": f"""Context from 38 CFR:
{context_text}

Question: {prompt}

Please provide a detailed answer based on the context above."""
                }
            ],
            temperature=0.3,
            max_tokens=800,
            top_p=1.0
        )
        
        answer_content = response.choices[0].message.content
        
        print(f"✅ Generated answer with {len(answer_content)} characters")
        
        return {
            'success': True,
            'content': answer_content,
            'citations': context_chunks,
            'source': 'direct_pinecone_gpt4',
            'metadata': {
                'model': 'gpt-4',
                'embedding_model': 'text-embedding-3-small',
                'chunks_used': len(context_chunks),
                'total_matches': len(results.matches),
                'usage': {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens
                }
            }
        }
        
    except Exception as e:
        print(f"❌ Error in direct Pinecone query: {e}")
        print(f"❌ Error type: {type(e)}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return None


@app.route("/")
def home():
    # Track visit
    client_ip = get_real_ip()  # Use improved IP detection
    with stats_lock:
        stats = app.config['STATS']
        stats['visit_count'] += 1
        
        # Track unique visitors (basic IP-based tracking)
        if client_ip not in stats['unique_visitors']:
            stats['unique_visitors'].add(client_ip)
        
        save_stats(stats)
        app.config['STATS'] = stats
    
    # Track visitor location asynchronously (don't block the request)
    track_visitor_location_async(client_ip, stats)
    
    # Prefer serving built SPA if available
    try:
        index_path = os.path.join(FRONTEND_BUILD_DIR, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(FRONTEND_BUILD_DIR, "index.html")
    except Exception:
        pass

    # Fallback: inline HTML (legacy UI)
    html_content = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Veterans Benefits AI - Trusted data, free forever</title>
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self';">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="/static/analytics.js" defer></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        primary: {
                            50: '#f0fdf4',
                            100: '#dcfce7',
                            500: '#22c55e',
                            600: '#16a34a',
                            700: '#15803d',
                            900: '#14532d'
                        }
                    },
                    animation: {
                        'fade-in': 'fadeIn 0.5s ease-in-out',
                        'slide-up': 'slideUp 0.6s ease-out',
                        'pulse-slow': 'pulse 3s infinite',
                        'glow': 'glow 2s ease-in-out infinite alternate',
                        'float': 'float 3s ease-in-out infinite'
                    },
                    keyframes: {
                        fadeIn: {
                            '0%': { opacity: '0' },
                            '100%': { opacity: '1' }
                        },
                        slideUp: {
                            '0%': { transform: 'translateY(20px)', opacity: '0' },
                            '100%': { transform: 'translateY(0)', opacity: '1' }
                        },
                        glow: {
                            '0%': { textShadow: '0 0 2px #22c55e, 0 0 4px #22c55e, 0 0 6px #22c55e' },
                            '100%': { textShadow: '0 0 4px #22c55e, 0 0 8px #22c55e, 0 0 12px #22c55e' }
                        },
                        float: {
                            '0%, 100%': { transform: 'translateY(0px)' },
                            '50%': { transform: 'translateY(-10px)' }
                        }
                    }
                }
            }
        }
    </script>
    <style>
        .gradient-bg {
            background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
        }
        .hero-gradient {
            background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
        }
        .card-gradient {
            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
        }
        .typing-dot {
            animation: typing 1.4s infinite ease-in-out;
        }
        .typing-dot:nth-child(1) { animation-delay: -0.32s; }
        .typing-dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typing {
            0%, 80%, 100% {
                transform: scale(0.8);
                opacity: 0.5;
            }
            40% {
                transform: scale(1);
                opacity: 1;
            }
        }
        .loading-spinner {
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .title-shadow {
            text-shadow: 0 4px 8px rgba(0, 0, 0, 0.5), 0 8px 16px rgba(0, 0, 0, 0.3);
        }
        .tagline-shadow {
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.4), 0 4px 8px rgba(0, 0, 0, 0.2);
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #ffffff;
            color: #000000;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 {
            color: #2c3e50;
            text-align: center;
            margin-bottom: 30px;
        }
        .input-group {
            margin-bottom: 20px;
        }
        textarea {
            width: 100%;
            height: 100px;
            padding: 15px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            resize: vertical;
            font-family: inherit;
        }
        textarea:focus {
            outline: none;
            border-color: #3498db;
        }
        button {
            background-color: #3498db;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
            transition: background-color 0.3s;
        }
        button:hover {
            background-color: #2980b9;
        }
        button:disabled {
            background-color: #bdc3c7;
            cursor: not-allowed;
        }
        .response {
            margin-top: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #3498db;
            line-height: 1.6;
        }
        .response h1, .response h2, .response h3 {
            margin-top: 20px;
            margin-bottom: 10px;
            color: #2c3e50;
        }
        .response h1 {
            font-size: 24px;
            border-bottom: 2px solid #3498db;
            padding-bottom: 5px;
        }
        .response h2 {
            font-size: 20px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 3px;
        }
        .response h3 {
            font-size: 18px;
            color: #34495e;
        }
        .response ul, .response ol {
            margin: 15px 0;
            padding-left: 30px;
        }
        .response li {
            margin-bottom: 8px;
            padding-left: 5px;
        }
        .response ol {
            counter-reset: item;
        }
        .response ol li {
            display: block;
            position: relative;
        }
        .response ol li:before {
            content: counter(item) ". ";
            counter-increment: item;
            font-weight: bold;
            color: #3498db;
            position: absolute;
            left: -25px;
        }
        .response strong {
            color: #2c3e50;
        }
        .response em {
            color: #7f8c8d;
        }
        .citations {
            margin-top: 20px;
        }
        .citations h3 {
            color: #2c3e50;
            margin-bottom: 15px;
        }
        .citation-item {
            background: white;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 6px;
            border: 1px solid #ddd;
        }
        .citation-item a {
            color: #3498db;
            text-decoration: none;
            font-weight: 500;
        }
        .citation-item a:hover {
            text-decoration: underline;
        }
        .source-content {
            margin-top: 8px;
            padding: 12px;
            background-color: #f8f9fa;
            border-left: 3px solid #3498db;
            border-radius: 4px;
            font-size: 14px;
            color: #555;
            font-style: italic;
            line-height: 1.4;
        }
        .source-content strong {
            color: #2c3e50;
            font-style: normal;
        }
        .loading {
            text-align: center;
            color: #7f8c8d;
            font-style: italic;
        }
        .status {
            text-align: center;
            padding: 10px;
            margin-bottom: 20px;
            border-radius: 6px;
            font-weight: bold;
        }
        .status.success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.warning {
            background-color: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        .mcp-info {
            background-color: #e3f2fd;
            color: #1565c0;
            border: 1px solid #bbdefb;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body class="bg-white min-h-screen">
    <div class="container">
        <h1 class="text-5xl md:text-7xl font-bold mb-3 animate-fade-in text-black">Veterans benifits ai.</h1>
        <p class="text-xl md:text-2xl mb-2 text-black text-center animate-slide-up">
            "Advanced rag based ai that sses the 38 CFR as its source"
        </p>
        <p class="text-base md:text-lg mb-8 text-black text-center animate-slide-up">
            38 CFR is the governing laws for veterans benifits.
        </p>

        <!-- Main Interface Card -->
        <div class="bg-white rounded-3xl shadow-2xl p-8 max-w-4xl mx-auto border border-gray-200">
            <!-- Input Section -->
            <div class="space-y-6">
                <div class="relative">
                    <textarea id="prompt" 
                              placeholder="Ask a question about veterans benefits..."
                              class="w-full h-32 p-6 text-lg border-2 border-gray-300 rounded-2xl resize-none focus:border-black focus:ring-4 focus:ring-black/10 transition-all duration-300 font-medium bg-white text-black placeholder-gray-500"></textarea>
                    
                    <!-- Typing Indicator -->
                    <div id="typingIndicator" class="absolute top-6 right-6 hidden">
                        <div class="flex space-x-1">
                            <div class="w-2 h-2 bg-green-500 rounded-full typing-dot"></div>
                            <div class="w-2 h-2 bg-green-500 rounded-full typing-dot"></div>
                            <div class="w-2 h-2 bg-green-500 rounded-full typing-dot"></div>
                        </div>
                    </div>
                </div>

                <div class="text-center">
                    <button onclick="ask()" id="askButton" 
                            class="px-8 py-4 bg-white text-black text-lg font-semibold rounded-2xl border-2 border-black hover:bg-black hover:text-white transform hover:scale-105 transition-all duration-300 shadow-sm">
                        Ask Question
                    </button>
                    <div class="mt-3 text-center">
                        <span id="askCountBadge" class="inline-block px-3 py-1 rounded-full bg-gray-100 text-gray-800 text-sm">
                            Asked <span id="askCountValue">0</span> times
                        </span>
                    </div>
                </div>
            </div>

            <!-- Sample Questions -->
            <div class="mt-8 pt-6 border-t border-gray-200">
                <p class="text-center text-black mb-4 font-medium">Try these sample questions:</p>
                <div class="flex flex-wrap justify-center gap-3">
                    <button onclick="setSampleQuestion('How do I apply for VA disability benefits?')" 
                            class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-full text-sm font-medium transition-colors duration-200">
                        Disability Benefits
                    </button>
                    <button onclick="setSampleQuestion('What are the requirements for VA pension?')" 
                            class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-full text-sm font-medium transition-colors duration-200">
                        Pension Requirements
                    </button>
                    <button onclick="setSampleQuestion('How do I use my GI Bill for education?')" 
                            class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-full text-sm font-medium transition-colors duration-200">
                        GI Bill Education
                    </button>
                </div>
            </div>
        </div>

        <!-- Response Section -->
        <div id="response" class="mt-12 max-w-4xl mx-auto hidden">
            <div class="bg-white rounded-3xl shadow-xl p-8 border border-gray-200">
                <div class="prose prose-lg max-w-none text-black">
                    <!-- Response content will be inserted here -->
                </div>
            </div>
        </div>

        <!-- Citations Section -->
        <div id="refs" class="mt-8 max-w-4xl mx-auto hidden">
            <div class="bg-white rounded-3xl shadow-xl p-8 border border-gray-200">
                <h3 class="text-2xl font-bold text-black mb-6 text-center">Sources & Footnotes</h3>
                <div class="space-y-4">
                    <!-- Citations will be inserted here -->
                </div>
            </div>
        </div>
    </div>

    <!-- Footer -->
    <div class="bg-white text-black py-12 mt-20 border-t border-gray-200">
        <div class="container mx-auto px-4 text-center">
            <h3 class="text-2xl font-bold mb-4 text-black">Veterans Benefits AI</h3>
            <p class="text-black mb-6">Empowering veterans with trusted information and AI assistance</p>
            <div class="flex justify-center space-x-6 text-sm text-black">
                <span>© 2024 Veterans Benefits AI</span>
                <span>•</span>
                <span>Free Forever</span>
                <span>•</span>
                <span>Trusted Data</span>
                <span>•</span>
                <a href="/stats" class="underline hover:opacity-80">Statistics</a>
            </div>
        </div>
    </div>

    <script>
        // Global variables and functions
        let mockDataMode = false;
        
        // Make functions globally accessible
        window.setSampleQuestion = function(question) {
            document.getElementById('prompt').value = question;
        };
        
        window.ask = async function() {
            const prompt = document.getElementById('prompt').value.trim();
            if (!prompt) {
                alert('Please enter a question');
                return;
            }

            const button = document.getElementById('askButton');
            const responseDiv = document.getElementById('response');
            const refsDiv = document.getElementById('refs');

            // Track chat question in analytics
            if (window.analyticsChatHit) {
                window.analyticsChatHit({prompt_length: prompt.length});
            }

            // Show loading state
            button.disabled = true;
            button.innerHTML = '<svg class="loading-spinner w-5 h-5 mr-2 inline" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Processing...';
            responseDiv.style.display = 'block';
            responseDiv.querySelector('.prose').innerHTML = '<div class="text-center text-black italic">Processing your question...</div>';
            refsDiv.style.display = 'none';

            try {
                const res = await fetch('/ask', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({prompt})
                });
                
                if (!res.ok) {
                    throw new Error(`HTTP error! status: ${res.status}`);
                }
                
                const data = await res.json();
                if (typeof data.ask_count === 'number') {
                    const badge = document.getElementById('askCountValue');
                    if (badge) badge.textContent = data.ask_count;
                }
                
                // Display response with proper formatting
                let formattedContent = data.content;
                
                // Convert markdown headers
                formattedContent = formattedContent
                    .replace(/### (.*?)(?=\n|$)/g, '<h3 class="text-2xl font-bold text-black mt-8 mb-4">$1</h3>')
                    .replace(/#### (.*?)(?=\n|$)/g, '<h4 class="text-xl font-semibold text-black mt-6 mb-3">$1</h4>');
                
                            // Convert numbered lists - Fixed regex
            formattedContent = formattedContent.replace(/(\d+)\.\s+(.*?)(?=\n\d+\.|$)/gs, function(match, number, content) {
                return `<li class="mb-2 text-black">${content}</li>`;
            });
            
            // Wrap numbered lists in ol tags
            formattedContent = formattedContent.replace(/(<li class="mb-2 text-black">.*?<\/li>)+/gs, function(match) {
                return `<ol class="list-decimal list-inside space-y-2 my-4 text-black">${match}</ol>`;
            });
            
            // Convert bullet lists - Fixed regex
            formattedContent = formattedContent.replace(/- (.*?)(?=\n-|$)/gs, function(match, content) {
                return `<li class="mb-2 text-black">${content}</li>`;
            });
            
            // Wrap bullet lists in ul tags
            formattedContent = formattedContent.replace(/(<li class="mb-2 text-black">.*?<\/li>)+/gs, function(match) {
                return `<ul class="list-disc list-inside space-y-2 my-4 text-black">${match}</ul>`;
            });
            
            // Convert bold and italic text
            formattedContent = formattedContent
                .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-black">$1</strong>')
                .replace(/\*(.*?)\*/g, '<em class="italic text-black">$1</em>');
            
            // Convert line breaks
            formattedContent = formattedContent
                .replace(/\n\n/g, '<br><br>')
                .replace(/\n/g, '<br>');
                
                // Append footnote-style sources (URLs only) at the end of the answer
                let footnotes = '';
                if (data.citations && data.citations.length > 0) {
                    const uniqueUrls = Array.from(new Set(
                        data.citations
                            .map(c => c.source_url)
                            .filter(u => !!u && u !== '#')
                    ));
                    if (uniqueUrls.length > 0) {
                        footnotes = '<hr class="my-6 border-gray-200">' +
                            '<div class="text-sm text-black"><div class="font-semibold text-black mb-2">Sources<\/div>' +
                            '<ol class="list-decimal list-inside space-y-1">' +
                            uniqueUrls.map((u, idx) => `<li><a class="text-black underline hover:opacity-80 break-words" href="${u}" target="_blank">${u}<\/a><\/li>`).join('') +
                            '<\/ol><\/div>';
                    }
                }

                responseDiv.querySelector('.prose').innerHTML = `
                    <h2 class="text-3xl font-bold text-black mb-6 text-center">Answer<\/h2>
                    <div class="text-black leading-relaxed">
                        ${formattedContent}
                        ${footnotes}
                    <\/div>
                `;
                
                // Hide the detailed citation cards section; we now show URLs as footnotes only
                refsDiv.style.display = 'none';
            } catch (error) {
                responseDiv.querySelector('.prose').innerHTML = `<div class="text-red-400 font-semibold">Error: ${error.message}</div>`;
                console.error('Error:', error);
            } finally {
                // Reset button state
                button.disabled = false;
                button.innerHTML = 'Ask Question';
            }
        }

        // Event listeners
        document.addEventListener('DOMContentLoaded', async function() {
            document.getElementById('prompt').addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && e.ctrlKey) {
                    ask();
                }
            });
            
            document.getElementById('prompt').addEventListener('input', function(e) {
                const typingIndicator = document.getElementById('typingIndicator');
                if (e.target.value.length > 0) {
                    typingIndicator.classList.remove('hidden');
                } else {
                    typingIndicator.classList.add('hidden');
                }
            });
            
            document.getElementById('prompt').addEventListener('blur', function() {
                const typingIndicator = document.getElementById('typingIndicator');
                typingIndicator.classList.add('hidden');
            });

            // Initialize ask counter from metrics endpoint
            try {
                const m = await fetch('/metrics').then(r => r.json());
                if (m && typeof m.ask_count === 'number') {
                    document.getElementById('askCountValue').textContent = m.ask_count;
                }
            } catch (err) {
                // ignore metrics init errors in UI
            }
        });
        
        // Error handling for message channel issues
        window.addEventListener('error', function(e) {
            if (e.message.includes('message channel closed')) {
                console.warn('Message channel error detected, this is likely harmless for local testing');
            }
        });
    </script>
</body>
</html>
    """
    return html_content

@app.route('/favicon.ico')
def favicon():
    try:
        # Serve our custom logo as the favicon
        target = os.path.join(FRONTEND_BUILD_DIR, 'logo.svg')
        if os.path.exists(target):
            return send_from_directory(FRONTEND_BUILD_DIR, 'logo.svg')
        # Fallback to placeholder if logo not present
        fallback = os.path.join(FRONTEND_BUILD_DIR, 'placeholder.svg')
        if os.path.exists(fallback):
            return send_from_directory(FRONTEND_BUILD_DIR, 'placeholder.svg')
    except Exception:
        pass
    return jsonify({"error": "favicon not available"}), 404

@app.route("/ask", methods=["POST"])
@limiter.limit(lambda: get_rate_limit_for_ip(get_remote_address()))
def ask():
    try:
        client_ip = get_remote_address()
        prompt = request.json.get("prompt", "")
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        # Intelligent throttling for suspicious behavior
        suspicious, reason = is_suspicious_request(client_ip, prompt)
        if suspicious:
            print(f"🚨 Suspicious request from {client_ip}: {reason}")
            return jsonify({
                "error": "Rate limit exceeded due to suspicious activity",
                "reason": reason,
                "retry_after": 300,
            }), 429
        # Increment ask counter (persistent)
        with stats_lock:
            stats = app.config['STATS']
            stats['ask_count'] += 1
            save_stats(stats)
            app.config['STATS'] = stats
            current_ask_count = stats['ask_count']
        
        # Resolve Pinecone assistant/index from app config if available
        assistant_ref = app.config.get('PINECONE_ASSISTANT') or assistant
        index_ref = app.config.get('PINECONE_INDEX') or index
        
        # Try direct Pinecone query first (cost-effective, high-performance)
        if index_ref and OPENAI_API_KEY:
            print(f"🚀 Attempting direct Pinecone + GPT-4 query for prompt: {prompt[:50]}...")
            
            direct_response = query_direct_pinecone(prompt, index_ref)
            
            if direct_response and direct_response.get("success"):
                print("✅ Successfully processed direct Pinecone query")
                # Log chat question to analytics
                log_chat_question()
                return jsonify({
                    "success": True,
                    "content": direct_response["content"],
                    "citations": direct_response.get("citations", []),
                    "source": direct_response["source"],
                    "metadata": direct_response.get("metadata", {}),
                    "ask_count": current_ask_count
                })
            else:
                print("⚠️ Direct Pinecone query failed, falling back to MCP")
        else:
            if not index_ref:
                print("⚠️ No Pinecone index available for direct query")
            if not OPENAI_API_KEY:
                print("⚠️ No OpenAI API key available for direct query")
        
        # Fallback to MCP server if direct query fails
        print(f"🔄 Falling back to MCP server for prompt: {prompt[:50]}...")
        
        mcp_response = call_mcp_server(prompt)
        
        if mcp_response and mcp_response.get("success"):
            # Process MCP server response
            content, citations, metadata = process_mcp_response(mcp_response)
            
            if content:
                print("✅ Successfully processed MCP server response")
                # Log chat question to analytics
                log_chat_question()
                return jsonify({
                    "success": True,
                    "content": content,
                    "citations": citations or [],
                    "source": "mcp_server",
                    "metadata": metadata,
                    "ask_count": current_ask_count
                })
        else:
            print(f"⚠️ MCP server failed: {mcp_response.get('error', 'Unknown error')}")
        
        # Final fallback to Pinecone SDK if both direct and MCP fail
        if assistant_ref:
            print("🔄 Falling back to Pinecone SDK...")
            try:
                from pinecone_plugins.assistant.models.chat import Message
                
                resp = assistant_ref.chat(
                    messages=[Message(role="user", content=prompt)], 
                    include_highlights=True
                )
                
                # Debug: Log the response structure
                print(f"🔍 Pinecone SDK response type: {type(resp)}")
                print(f"🔍 Response attributes: {dir(resp)}")
                if hasattr(resp, 'citations'):
                    print(f"🔍 Citations type: {type(resp.citations)}")
                    print(f"🔍 Citations count: {len(resp.citations) if resp.citations else 0}")
                    if resp.citations:
                        print(f"🔍 First citation type: {type(resp.citations[0])}")
                        print(f"🔍 First citation attributes: {dir(resp.citations[0])}")
                        if hasattr(resp.citations[0], 'references'):
                            print(f"🔍 First citation references: {resp.citations[0].references}")
                        
                        # Log all available attributes and their values
                        print(f"🔍 First citation full details:")
                        for attr in dir(resp.citations[0]):
                            if not attr.startswith('_'):
                                try:
                                    value = getattr(resp.citations[0], attr)
                                    if not callable(value):
                                        print(f"  {attr}: {value}")
                                except:
                                    pass
                
                # Process citations from the response
                citations = []
                try:
                    if hasattr(resp, 'citations') and resp.citations:
                        print(f"🔍 Processing {len(resp.citations)} citations...")
                        for i, citation in enumerate(resp.citations):
                            try:
                                print(f"🔍 Processing citation {i+1}: {type(citation)}")
                                print(f"🔍 Citation attributes: {dir(citation)}")
                                
                                # Handle different citation structures
                                file_name = "Unknown"
                                page_num = 1
                                url = "#"
                                
                                # Try to extract file information from different possible structures
                                if hasattr(citation, 'references') and citation.references:
                                    print(f"🔍 Citation has references: {citation.references}")
                                    ref = citation.references[0]
                                    if hasattr(ref, 'file') and ref.file:
                                        if hasattr(ref.file, 'name'):
                                            file_name = ref.file.name
                                        if hasattr(ref.file, 'signed_url'):
                                            url = ref.file.signed_url
                                            source_url = ref.file.signed_url
                                    
                                    # Try to get page information
                                    if hasattr(ref, 'pages') and ref.pages:
                                        page_num = ref.pages[0] if ref.pages else 1
                                    elif hasattr(ref, 'page'):
                                        page_num = ref.page
                                
                                # Alternative structure: direct file access
                                elif hasattr(citation, 'file') and citation.file:
                                    print(f"🔍 Citation has direct file: {citation.file}")
                                    if hasattr(citation.file, 'name'):
                                        file_name = citation.file.name
                                    if hasattr(citation.file, 'signed_url'):
                                        url = citation.file.signed_url
                                        source_url = citation.file.signed_url
                                
                                # Alternative structure: direct page access
                                if hasattr(citation, 'pages') and citation.pages:
                                    page_num = citation.pages[0] if citation.pages else 1
                                elif hasattr(citation, 'page'):
                                    page_num = citation.page
                                
                                # Try to extract the actual source content/text
                                source_text = ""
                                try:
                                    # Look for text content in various possible locations
                                    if hasattr(citation, 'text'):
                                        source_text = citation.text
                                    elif hasattr(citation, 'content'):
                                        source_text = citation.content
                                    elif hasattr(citation, 'snippet'):
                                        source_text = citation.snippet
                                    elif hasattr(citation, 'highlight'):
                                        source_text = citation.highlight
                                    elif hasattr(ref, 'text'):
                                        source_text = ref.text
                                    elif hasattr(ref, 'content'):
                                        source_text = ref.content
                                    elif hasattr(ref, 'snippet'):
                                        source_text = ref.snippet
                                    
                                    # If we found text, clean it up
                                    if source_text:
                                        # Limit length and clean up whitespace
                                        source_text = source_text.strip()
                                        if len(source_text) > 500:  # Limit to 500 characters
                                            source_text = source_text[:500] + "..."
                                except Exception as e:
                                    print(f"⚠️ Could not extract source text: {e}")
                                    source_text = "Source content not available"
                                
                                citation_data = {
                                    "file": file_name,
                                    "page": page_num,
                                    "url": url,
                                    "source_url": source_url or url,
                                    "source_text": source_text
                                }
                                citations.append(citation_data)
                                print(f"✅ Successfully processed citation {i+1}: {citation_data}")
                                
                            except Exception as e:
                                print(f"❌ Error processing citation {i+1}: {e}")
                                # Add a basic citation entry to avoid breaking the response
                                citations.append({
                                    "file": "Document",
                                    "page": 1,
                                    "url": "#",
                                    "source_text": "Source content not available"
                                })
                                continue
                    else:
                        print("⚠️ No citations found in response")
                        
                except Exception as e:
                    print(f"❌ Error in citation processing loop: {e}")
                    # Continue without citations rather than failing completely
                
                # Log chat question to analytics
                log_chat_question()
                return jsonify({
                    "content": resp.message.content,
                    "citations": citations,
                    "source": "pinecone_sdk",
                    "ask_count": current_ask_count,
                    "debug_info": {
                        "response_type": str(type(resp)),
                        "has_citations": hasattr(resp, 'citations'),
                        "citations_count": len(citations) if citations else 0
                    }
                })
                
            except Exception as e:
                print(f"Error with Pinecone SDK fallback: {e}")
                return jsonify({"error": f"Both MCP server and Pinecone SDK failed: {str(e)}"}), 500
        else:
            return jsonify({
                "error": "Neither MCP server nor Pinecone SDK available",
                "details": {
                    "mcp_api_key_configured": bool(MCP_API_KEY),
                    "assistant_ready": bool(assistant_ref),
                    "index_ready": bool(index_ref)
                }
            }), 500
        
    except Exception as e:
        print(f"Error in ask endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "pinecone_available": assistant is not None,
        "index_available": index is not None,
        "mcp_endpoint": MCP_SERVER_URL,
        "mcp_api_key_configured": bool(MCP_API_KEY),
        "environment": os.getenv("FLASK_ENV", "production"),
                    "endpoints": {
            "main": "/",
            "ask": "/ask",
            "health": "/health",
            "metrics": "/metrics",
            "stats": "/stats",
            "rate_limit_status": "/rate-limit-status",
            "mcp_test": "/mcp/test",
            "mcp_status": "/mcp/status",
            "mcp_chat": "/mcp/chat",
            "debug": "/debug"
        }
    })

@app.route("/metrics")
def metrics():
    with stats_lock:
        stats = app.config['STATS']
        return jsonify({
            "ask_count": stats['ask_count'],
            "visit_count": stats['visit_count'],
            "unique_visitors": len(stats['unique_visitors']),
            "visitor_locations": stats.get('visitor_locations', {}),
            "first_visit": stats['first_visit'],
            "last_updated": stats['last_updated']
        })

@app.route("/api/locations")
def get_visitor_locations():
    """API endpoint specifically for location data used by heat map"""
    with stats_lock:
        stats = app.config['STATS']
        locations = stats.get('visitor_locations', {})
        
        # Filter out non-US locations for the US heat map
        us_locations = {}
        international_count = 0
        local_count = 0
        unknown_count = 0
        
        for location, count in locations.items():
            if location == 'Local':
                local_count += count
            elif location == 'Unknown':
                unknown_count += count
            elif location.startswith('International-'):
                international_count += count
            elif len(location) == 2 and location.isalpha():  # US state codes
                us_locations[location.upper()] = count
        
        result = {
            "us_states": us_locations,
            "international": international_count,
            "local": local_count,
            "unknown": unknown_count,
            "total_tracked": sum(locations.values())
        }
        
        print(f"🗺️ API /api/locations returning: {result}")
        return jsonify(result)

@app.route("/debug/ip")
def debug_ip():
    """Debug endpoint to check IP detection and geolocation"""
    client_ip = get_real_ip()
    
    # Get all headers for debugging
    headers_info = {}
    for header in ['X-Forwarded-For', 'X-Real-IP', 'X-Client-IP', 'CF-Connecting-IP', 'True-Client-IP']:
        value = request.headers.get(header)
        if value:
            headers_info[header] = value
    
    # Test geolocation
    location = get_location_from_ip(client_ip)
    
    return jsonify({
        "detected_ip": client_ip,
        "remote_addr": request.remote_addr,
        "headers": headers_info,
        "all_headers": dict(request.headers),
        "location": location,
        "is_local": client_ip in ['127.0.0.1', 'localhost', '::1'] or client_ip.startswith(('192.168.', '10.', '172.'))
    })

@app.route("/debug/api-comparison")
def debug_api_comparison():
    """Debug endpoint to compare raw data vs API format"""
    with stats_lock:
        stats = app.config['STATS']
        raw_locations = stats.get('visitor_locations', {})
        
        # Process the same way as /api/locations
        us_locations = {}
        international_count = 0
        local_count = 0
        unknown_count = 0
        
        for location, count in raw_locations.items():
            if location == 'Local':
                local_count += count
            elif location == 'Unknown':
                unknown_count += count
            elif location.startswith('International-'):
                international_count += count
            elif len(location) == 2 and location.isalpha():  # US state codes
                us_locations[location.upper()] = count
        
        api_format = {
            "us_states": us_locations,
            "international": international_count,
            "local": local_count,
            "unknown": unknown_count,
            "total_tracked": sum(raw_locations.values())
        }
        
        return jsonify({
            "raw_visitor_locations": raw_locations,
            "api_formatted_response": api_format,
            "data_comparison": {
                "raw_total_entries": len(raw_locations),
                "us_states_count": len(us_locations),
                "has_us_data": len(us_locations) > 0,
                "sample_us_states": list(us_locations.keys())[:5]
            },
            "frontend_expects": {
                "structure": "{ us_states: { 'CA': 45, 'NY': 32, ... }, international: 8, local: 12, unknown: 5 }",
                "note": "Frontend looks for 'us_states' object with 2-letter state codes as keys"
            }
        })

@app.route("/debug/populate-sample-locations")
def populate_sample_locations():
    """Populate sample location data for testing (development only)"""
    sample_locations = {
        'CA': 45,  # California
        'NY': 32,  # New York
        'TX': 28,  # Texas
        'FL': 22,  # Florida
        'WA': 18,  # Washington
        'IL': 15,  # Illinois
        'PA': 12,  # Pennsylvania
        'OH': 10,  # Ohio
        'GA': 8,   # Georgia
        'NC': 7,   # North Carolina
        'VA': 6,   # Virginia
        'MI': 5,   # Michigan
        'CO': 4,   # Colorado
        'OR': 3,   # Oregon
        'AZ': 2,   # Arizona
        'NV': 1,   # Nevada
        'International-CA': 8,  # Canada
        'International-UK': 5,  # United Kingdom
        'International-DE': 3,  # Germany
        'Local': 12,
        'Unknown': 5
    }
    
    with stats_lock:
        stats = app.config['STATS']
        stats['visitor_locations'] = sample_locations
        save_stats(stats)
        app.config['STATS'] = stats
    
    # Filter and format the response to match /api/locations format
    us_locations = {}
    international_count = 0
    local_count = 0
    unknown_count = 0
    
    for location, count in sample_locations.items():
        if location == 'Local':
            local_count += count
        elif location == 'Unknown':
            unknown_count += count
        elif location.startswith('International-'):
            international_count += count
        elif len(location) == 2 and location.isalpha():  # US state codes
            us_locations[location.upper()] = count
    
    return jsonify({
        "message": "Sample location data populated successfully",
        "locations": sample_locations,  # Raw data for debugging
        "formatted_for_heatmap": {      # Properly formatted data
            "us_states": us_locations,
            "international": international_count,
            "local": local_count,
            "unknown": unknown_count,
            "total_tracked": sum(sample_locations.values())
        },
        "total": sum(sample_locations.values())
    })

@app.route("/stats")
def stats_page():
    """Serve the stats page - either SPA component or fallback HTML"""
    try:
        # Try to serve the SPA first (it will handle the /stats route)
        index_path = os.path.join(FRONTEND_BUILD_DIR, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(FRONTEND_BUILD_DIR, "index.html")
    except Exception:
        pass
    
    # Fallback: inline HTML stats page
    with stats_lock:
        stats = app.config['STATS']
        
    stats_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Veterans Benefits AI - Statistics</title>
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self';">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #ffffff;
            color: #000000;
        }}
    </style>
</head>
<body class="bg-white min-h-screen">
    <div class="container mx-auto px-4 py-12 max-w-4xl">
        <div class="text-center mb-12">
            <h1 class="text-5xl md:text-6xl font-bold mb-4 text-black">Statistics</h1>
            <p class="text-xl text-gray-600">Veterans Benefits AI Usage Analytics</p>
            <div class="mt-6">
                <a href="/" class="inline-block px-6 py-3 bg-black text-white rounded-lg hover:bg-gray-800 transition-colors">
                    ← Back to Home
                </a>
            </div>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
            <!-- Questions Asked -->
            <div class="bg-white rounded-3xl shadow-xl p-8 border border-gray-200 text-center">
                <div class="text-6xl font-bold text-blue-600 mb-4">{stats['ask_count']:,}</div>
                <h3 class="text-2xl font-semibold text-black mb-2">Questions Asked</h3>
                <p class="text-gray-600">Total questions processed by our AI</p>
            </div>
            
            <!-- Website Visits -->
            <div class="bg-white rounded-3xl shadow-xl p-8 border border-gray-200 text-center">
                <div class="text-6xl font-bold text-green-600 mb-4">{stats['visit_count']:,}</div>
                <h3 class="text-2xl font-semibold text-black mb-2">Website Visits</h3>
                <p class="text-gray-600">Total page views since launch</p>
            </div>
            
            <!-- Unique Visitors -->
            <div class="bg-white rounded-3xl shadow-xl p-8 border border-gray-200 text-center">
                <div class="text-6xl font-bold text-purple-600 mb-4">{len(stats['unique_visitors']):,}</div>
                <h3 class="text-2xl font-semibold text-black mb-2">Unique Visitors</h3>
                <p class="text-gray-600">Different users who visited our site</p>
            </div>
            
            <!-- Engagement Rate -->
            <div class="bg-white rounded-3xl shadow-xl p-8 border border-gray-200 text-center">
                <div class="text-6xl font-bold text-orange-600 mb-4">{(stats['ask_count'] / max(stats['visit_count'], 1) * 100):.1f}%</div>
                <h3 class="text-2xl font-semibold text-black mb-2">Engagement Rate</h3>
                <p class="text-gray-600">Percentage of visits that asked questions</p>
            </div>
        </div>
        
        <!-- Additional Info -->
        <div class="bg-white rounded-3xl shadow-xl p-8 border border-gray-200">
            <h3 class="text-2xl font-semibold text-black mb-6 text-center">Service Information</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
                <div>
                    <span class="font-semibold text-gray-700">Service Started:</span>
                    <span class="text-gray-600 ml-2">{datetime.fromisoformat(stats['first_visit']).strftime('%B %d, %Y at %I:%M %p')}</span>
                </div>
                <div>
                    <span class="font-semibold text-gray-700">Last Updated:</span>
                    <span class="text-gray-600 ml-2">{datetime.fromisoformat(stats['last_updated']).strftime('%B %d, %Y at %I:%M %p')}</span>
                </div>
                <div>
                    <span class="font-semibold text-gray-700">Questions per Visit:</span>
                    <span class="text-gray-600 ml-2">{(stats['ask_count'] / max(stats['visit_count'], 1)):.2f}</span>
                </div>
                <div>
                    <span class="font-semibold text-gray-700">Questions per Unique User:</span>
                    <span class="text-gray-600 ml-2">{(stats['ask_count'] / max(len(stats['unique_visitors']), 1)):.2f}</span>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="text-center mt-12 text-gray-500">
            <p>Statistics are updated in real-time and persist across server restarts</p>
            <p class="mt-2">Veterans Benefits AI - Trusted data, free forever</p>
        </div>
    </div>
    
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(() => {{
            window.location.reload();
        }}, 30000);
    </script>
</body>
</html>
    """
    return stats_html

# Rate limit status for debugging/ops
@app.route("/rate-limit-status")
def rate_limit_status():
    from datetime import datetime, timedelta
    ip = get_remote_address()
    now = datetime.now()
    with suspicious_lock:
        data = suspicious_ips.get(ip, {"requests": []})
        recent = [t for t in data.get("requests", []) if now - t < timedelta(hours=1)]
    return jsonify({
        "ip": ip,
        "current_limit": get_rate_limit_for_ip(ip),
        "requests_last_hour": len(recent),
        "tracked": ip in suspicious_ips,
        "total_requests": app.config['STATS']['ask_count'],
    })

@app.errorhandler(429)
def ratelimit_handler(e):
    ip = get_remote_address()
    print(f"🚨 Rate limit exceeded for {ip}: {getattr(e, 'description', '')}")
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please wait before retrying.",
        "retry_after": getattr(e, 'retry_after', 60),
        "limit": getattr(e, 'description', 'n/a'),
    }), 429

# Debug routes to help troubleshoot
@app.route("/debug")
def debug():
    return jsonify({
        "app_name": app.name,
        "template_folder": app.template_folder,
        "static_folder": app.static_folder,
        "frontend_build_dir": FRONTEND_BUILD_DIR,
        "frontend_build_present": os.path.exists(os.path.join(FRONTEND_BUILD_DIR, "index.html")),
        "routes": [str(rule) for rule in app.url_map.iter_rules()],
        "current_working_directory": os.getcwd(),
        "files_in_cwd": os.listdir(".") if os.path.exists(".") else "Directory not accessible",
        "pinecone_assistant_status": "connected" if assistant else "disconnected",
        "pinecone_index_status": "connected" if index else "disconnected"
    })

@app.route("/test")
def test():
    return "Test route working! Flask is running correctly."

@app.route("/ping")
def ping():
    return jsonify({"message": "pong", "status": "ok"})

# Serve SPA static assets and enable client-side routing fallback
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files (analytics.js, etc.)"""
    try:
        return send_from_directory('static', filename)
    except Exception:
        return jsonify({"error": "Static file not found"}), 404

@app.route('/<path:path>')
def serve_spa_assets(path):
    try:
        # If SPA build exists and the requested file exists, serve it
        target_path = os.path.join(FRONTEND_BUILD_DIR, path)
        if os.path.exists(target_path) and os.path.isfile(target_path):
            return send_from_directory(FRONTEND_BUILD_DIR, path)
        # Otherwise, if SPA build exists, return index.html for client-side routing
        index_path = os.path.join(FRONTEND_BUILD_DIR, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(FRONTEND_BUILD_DIR, 'index.html')
    except Exception:
        pass
    # If no SPA, 404 for unknown paths
    return jsonify({"error": "Not found"}), 404

@app.route("/mcp/test", methods=["POST"])
def test_mcp():
    """Test endpoint specifically for MCP server functionality"""
    try:
        test_prompt = request.json.get("prompt", "Hello, can you tell me about veterans benefits?")
        
        print(f"🧪 Testing MCP server with prompt: {test_prompt}")
        
        # Test the MCP server
        mcp_response = call_mcp_server(test_prompt)
        
        if mcp_response and mcp_response.get("success"):
            content, citations, metadata = process_mcp_response(mcp_response)
            return jsonify({
                "success": True,
                "mcp_server_status": "working",
                "response": {
                    "content": content,
                    "citations": citations or [],
                    "metadata": metadata
                },
                "raw_response": mcp_response
            })
        else:
            return jsonify({
                "success": False,
                "mcp_server_status": "failed",
                "error": mcp_response.get("error", "Unknown error"),
                "code": mcp_response.get("code", "unknown"),
                "message": mcp_response.get("message", "No additional details")
            })
            
    except Exception as e:
        print(f"Error testing MCP server: {e}")
        return jsonify({
            "success": False,
            "mcp_server_status": "error",
            "error": str(e)
        }), 500

@app.route("/mcp/status")
def mcp_status():
    """Get detailed status of MCP server connection"""
    try:
        # Test a simple connection
        test_response = call_mcp_server("Test connection")
        
        status_info = {
            "mcp_server_url": MCP_SERVER_URL,
            "api_key_configured": bool(MCP_API_KEY),
            "connection_test": "success" if test_response and test_response.get("success") else "failed",
            "last_test_time": "now",
            "pinecone_sdk_status": "connected" if assistant else "disconnected",
            "pinecone_index_status": "connected" if index else "disconnected"
        }
        
        if test_response and test_response.get("success"):
            content, citations, metadata = process_mcp_response(test_response)
            status_info["mcp_response_sample"] = {
                "has_content": bool(content),
                "has_citations": bool(citations),
                "has_metadata": bool(metadata)
            }
        
        return jsonify(status_info)
        
    except Exception as e:
        return jsonify({
            "mcp_server_url": MCP_SERVER_URL,
            "api_key_configured": bool(MCP_API_KEY),
            "connection_test": "error",
            "error": str(e)
        }), 500

@app.route("/debug/direct", methods=["POST"])
def debug_direct():
    """Debug endpoint to test direct Pinecone query"""
    try:
        prompt = request.json.get("prompt", "What are VA disability benefits?")
        index_ref = app.config.get('PINECONE_INDEX') or index
        
        if not index_ref:
            return jsonify({"error": "No Pinecone index available"}), 500
            
        if not OPENAI_API_KEY:
            return jsonify({"error": "No OpenAI API key available"}), 500
            
        print(f"🔧 DEBUG: Testing direct query with prompt: {prompt}")
        print(f"🔧 DEBUG: OpenAI API key available: {bool(OPENAI_API_KEY)}")
        print(f"🔧 DEBUG: Pinecone index available: {bool(index_ref)}")
        
        # Test OpenAI directly first
        embed_success = False
        embed_error = None
        embed_dims = None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            test_embed = client.embeddings.create(model="text-embedding-3-small", input="test", dimensions=1024)
            embed_success = True
            embed_dims = len(test_embed.data[0].embedding)
        except Exception as e:
            embed_success = False
            embed_error = str(e)
        
        result = query_direct_pinecone(prompt, index_ref)
        
        if result:
            return jsonify({
                "success": True,
                "result": result,
                "debug": {
                    "openai_key_set": bool(OPENAI_API_KEY),
                    "index_available": bool(index_ref),
                    "embed_test_success": embed_success,
                    "embed_dims": embed_dims if embed_success else None
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Direct query returned None",
                "debug": {
                    "openai_key_set": bool(OPENAI_API_KEY),
                    "index_available": bool(index_ref),
                    "embed_test_success": embed_success,
                    "embed_error": embed_error if not embed_success else None,
                    "embed_dims": embed_dims if embed_success else None
                }
            })
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "debug": {
                "openai_key_set": bool(OPENAI_API_KEY),
                "index_available": bool(index_ref)
            }
        }), 500

@app.route("/mcp/chat", methods=["POST"])
def mcp_chat():
    """
    Advanced MCP chat endpoint with JSON configuration
    
    Expected JSON payload:
    {
        "prompt": "User's question",
        "options": {
            "temperature": 0.7,
            "max_tokens": 1000,
            "include_highlights": true
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No JSON data provided",
                "code": 400
            }), 400
        
        prompt = data.get("prompt")
        if not prompt:
            return jsonify({
                "success": False,
                "error": "No prompt provided",
                "code": 400
            }), 400
        
        # Extract options
        options = data.get("options", {})
        
        print(f"💬 Advanced MCP chat request: {prompt[:100]}...")
        print(f"⚙️ Options: {options}")
        
        # Call MCP server with options
        mcp_response = call_mcp_server(prompt, options)
        
        if mcp_response and mcp_response.get("success"):
            content, citations, metadata = process_mcp_response(mcp_response)
            
            return jsonify({
                "success": True,
                "content": content,
                "citations": citations or [],
                "metadata": metadata,
                "source": "mcp_server_advanced"
            })
        else:
            return jsonify({
                "success": False,
                "error": mcp_response.get("error", "Unknown error"),
                "code": mcp_response.get("code", "unknown"),
                "message": mcp_response.get("message", "No additional details")
            }), 500
            
    except Exception as e:
        print(f"Error in advanced MCP chat: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "code": "exception"
        }), 500

if __name__ == "__main__":
    print("🚀 Starting Veterans Benefits Assistant...")
    print(f"📁 Templates folder: {app.template_folder}")
    print(f"🔑 Pinecone API Key: {'✅ Set' if os.getenv('PINECONE_API_KEY') else '❌ Missing'}")
    print(f"📊 Pinecone Index: {os.getenv('PINECONE_INDEX_NAME', 'veterans-benefits')}")
    print(f"📍 Current working directory: {os.getcwd()}")
    print(f"📂 Files in current directory: {os.listdir('.') if os.path.exists('.') else 'Directory not accessible'}")
    print(f"🔗 MCP Endpoint: https://prod-1-data.ke.pinecone.io/mcp/assistants/vb")
    try:
        spa_index = os.path.join(FRONTEND_BUILD_DIR, 'index.html')
        if os.path.exists(spa_index):
            print(f"🧩 SPA build detected at: {spa_index}. Serving frontend from build directory.")
        else:
            print("ℹ️ No SPA build detected. Serving inline fallback UI.")
    except Exception as e:
        print(f"⚠️ Could not check SPA build: {e}")
    
    # Get port from environment variable (for cloud deployment)
    port = int(os.environ.get("PORT", 5000))
    
    app.run(debug=True, host='0.0.0.0', port=port)
