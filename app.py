from flask import Flask, render_template, request, jsonify
from pinecone import Pinecone
import os
from dotenv import load_dotenv
import requests
import json

# Load environment variables
load_dotenv('env.txt')  # Using env.txt since .env is blocked

app = Flask(__name__)

# Initialize Pinecone MCP Assistant
try:
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    # Use your existing MCP assistant
    assistant = pc.assistant.Assistant(assistant_name="vb")
    print("✅ Pinecone MCP Assistant 'vb' connected successfully")
    
    # Also try to get the index for additional functionality
    try:
        index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "veterans-benefits"))
        print(f"✅ Pinecone Index '{os.getenv('PINECONE_INDEX_NAME', 'veterans-benefits')}' connected successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not connect to Pinecone index: {e}")
        index = None
        
except Exception as e:
    print(f"❌ Error initializing Pinecone MCP Assistant: {e}")
    assistant = None
    index = None

# MCP Server configuration
MCP_SERVER_URL = "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb"
MCP_API_KEY = os.getenv("PINECONE_API_KEY")

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
                    
                    citation_data = {
                        "file": citation.get("file", {}).get("name", "Unknown"),
                        "page": citation.get("page", 1),
                        "url": citation.get("url", "#"),
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

@app.route("/")
def home():
    # Temporary inline HTML to fix template issue
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Veterans Benefits Assistant</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
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
<body>
    <div class="container">
        <h1>Veterans Benefits Knowledge Base Assistant</h1>
        
        <div class="status success">
            ✅ App is running successfully on Render!
        </div>
        
        <div class="mcp-info">
            🔗 Connected to Pinecone MCP Assistant: <strong>vb</strong><br>
            📍 Endpoint: <code>https://prod-1-data.ke.pinecone.io/mcp/assistants/vb</code>
        </div>
        
        <div class="input-group">
            <textarea id="prompt" placeholder="Ask a question about veterans benefits..."></textarea>
        </div>
        
        <button onclick="ask()" id="askButton">Ask Question</button>
        
        <div id="response" class="response" style="display: none;"></div>
        
        <div id="refs" class="citations" style="display: none;"></div>
    </div>

    <script>
        async function ask() {
            const prompt = document.getElementById('prompt').value.trim();
            if (!prompt) {
                alert('Please enter a question');
                return;
            }

            const button = document.getElementById('askButton');
            const responseDiv = document.getElementById('response');
            const refsDiv = document.getElementById('refs');

            // Show loading state
            button.disabled = true;
            button.textContent = 'Processing...';
            responseDiv.style.display = 'block';
            responseDiv.innerHTML = '<div class="loading">Processing your question...</div>';
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
                
                // Display response with proper formatting
                let formattedContent = data.content;
                
                // Convert markdown headers
                formattedContent = formattedContent
                    .replace(/### (.*?)(?=\\n|$)/g, '<h3>$1</h3>')     // H3 headers
                    .replace(/## (.*?)(?=\\n|$)/g, '<h2>$1</h2>')      // H2 headers
                    .replace(/# (.*?)(?=\\n|$)/g, '<h1>$1</h1>');     // H1 headers
                
                // Convert numbered lists
                formattedContent = formattedContent.replace(/(\\d+\\.\\s+.*?)(?=\\n\\d+\\.|$)/gs, function(match) {
                    const items = match.split('\\n').filter(line => line.trim());
                    if (items.length > 0) {
                        const listItems = items.map(item => 
                            item.replace(/^\\d+\\.\\s+/, '<li>') + '</li>'
                        ).join('');
                        return `<ol>${listItems}</ol>`;
                    }
                    return match;
                });
                
                // Convert bullet lists
                formattedContent = formattedContent.replace(/(- .*?)(?=\\n-|$)/gs, function(match) {
                    const items = match.split('\\n').filter(line => line.trim());
                    if (items.length > 0) {
                        const listItems = items.map(item => 
                            item.replace(/^- /, '<li>') + '</li>'
                        ).join('');
                        return `<ul>${listItems}</ul>`;
                    }
                    return match;
                });
                
                // Convert bold and italic text
                formattedContent = formattedContent
                    .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')  // Bold text
                    .replace(/\\*(.*?)\\*/g, '<em>$1</em>');              // Italic text
                
                // Convert line breaks
                formattedContent = formattedContent
                    .replace(/\\n\\n/g, '<br><br>')  // Double line breaks become <br><br>
                    .replace(/\\n/g, '<br>');         // Single line breaks become <br>
                
                responseDiv.innerHTML = `<strong>Answer:</strong><br><br>${formattedContent}`;
                
                // Display citations if available
                if (data.citations && data.citations.length > 0) {
                    refsDiv.style.display = 'block';
                    refsDiv.innerHTML = '<h3>Sources & Footnotes:</h3>';
                    
                    data.citations.forEach((c, i) => {
                        const div = document.createElement('div');
                        div.className = 'citation-item';
                        
                        // Create the reference link
                        const a = document.createElement('a');
                        a.href = c.url;
                        a.target = '_blank';
                        a.textContent = `[${i+1}] ${c.file} (Page ${c.page})`;
                        a.style.fontWeight = 'bold';
                        a.style.color = '#3498db';
                        div.appendChild(a);
                        
                        // Add the source content as a footnote
                        if (c.source_text && c.source_text !== 'Source content not available') {
                            const sourceDiv = document.createElement('div');
                            sourceDiv.className = 'source-content';
                            sourceDiv.style.marginTop = '8px';
                            sourceDiv.style.padding = '10px';
                            sourceDiv.style.backgroundColor = '#f8f9fa';
                            sourceDiv.style.borderLeft = '3px solid #3498db';
                            sourceDiv.style.fontSize = '14px';
                            sourceDiv.style.color = '#555';
                            sourceDiv.style.fontStyle = 'italic';
                            sourceDiv.innerHTML = `<strong>Source:</strong> ${c.source_text}`;
                            div.appendChild(sourceDiv);
                        }
                        
                        refsDiv.appendChild(div);
                    });
                }
            } catch (error) {
                responseDiv.innerHTML = `<strong>Error:</strong> ${error.message}`;
                console.error('Error:', error);
            } finally {
                // Reset button state
                button.disabled = false;
                button.textContent = 'Ask Question';
            }
        }

        // Allow Enter key to submit
        document.getElementById('prompt').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && e.ctrlKey) {
                ask();
            }
        });
    </script>
</body>
</html>
    """
    return html_content

@app.route("/ask", methods=["POST"])
def ask():
    try:
        prompt = request.json.get("prompt", "")
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        
        # Try using the MCP server first (more direct integration)
        print(f"🔄 Attempting to use MCP server for prompt: {prompt[:50]}...")
        
        # Call the MCP server directly
        mcp_response = call_mcp_server(prompt)
        
        if mcp_response and mcp_response.get("success"):
            # Process MCP server response
            content, citations, metadata = process_mcp_response(mcp_response)
            
            if content:
                print("✅ Successfully processed MCP server response")
                return jsonify({
                    "success": True,
                    "content": content,
                    "citations": citations or [],
                    "source": "mcp_server",
                    "metadata": metadata
                })
        else:
            print(f"⚠️ MCP server failed: {mcp_response.get('error', 'Unknown error')}")
        
        # Fallback to Pinecone SDK if MCP server fails
        if assistant:
            print("🔄 Falling back to Pinecone SDK...")
            try:
                from pinecone_plugins.assistant.models.chat import Message
                
                resp = assistant.chat(
                    messages=[Message(role="user", content=prompt)], 
                    include_highlights=True,
                    include_citations=True
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
                
                return jsonify({
                    "content": resp.message.content,
                    "citations": citations,
                    "source": "pinecone_sdk",
                    "debug_info": {
                        "response_type": str(type(resp)),
                        "has_citations": hasattr(resp, 'citations'),
                        "citations_count": len(citations) if citations else 0
                    }
                })
                
            except Exception as e:
                print(f"Error with Pinecone SDK fallback: {e}")
                # Even if citations fail, try to return the content if available
                try:
                    if hasattr(resp, 'message') and hasattr(resp.message, 'content'):
                        return jsonify({
                            "content": resp.message.content,
                            "citations": [],
                            "source": "pinecone_sdk_fallback",
                            "warning": "Citations could not be processed, but content is available"
                        })
                except:
                    pass
                return jsonify({"error": f"Both MCP server and Pinecone SDK failed: {str(e)}"}), 500
        else:
            return jsonify({"error": "Neither MCP server nor Pinecone SDK available"}), 500
        
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
            "mcp_test": "/mcp/test",
            "mcp_status": "/mcp/status",
            "mcp_chat": "/mcp/chat",
            "debug": "/debug"
        }
    })

# Debug routes to help troubleshoot
@app.route("/debug")
def debug():
    return jsonify({
        "app_name": app.name,
        "template_folder": app.template_folder,
        "static_folder": app.static_folder,
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
    
    # Get port from environment variable (for cloud deployment)
    port = int(os.environ.get("PORT", 5000))
    
    app.run(debug=True, host='0.0.0.0', port=port)
