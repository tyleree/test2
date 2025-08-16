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
    <title>Veterans Benefits AI - Trusted data, free forever</title>
    <script src="https://cdn.tailwindcss.com"></script>
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
                            '0%': { textShadow: '0 0 5px #22c55e, 0 0 10px #22c55e, 0 0 15px #22c55e' },
                            '100%': { textShadow: '0 0 10px #22c55e, 0 0 20px #22c55e, 0 0 30px #22c55e' }
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
            background-color: #111827;
            color: #f9fafb;
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
<body>
    <div class="container">
        <h1 class="text-5xl md:text-7xl font-bold mb-6 animate-fade-in title-shadow">
            <span class="bg-gradient-to-r from-green-400 to-green-600 bg-clip-text text-transparent animate-glow">
                Veterans Benefits AI
            </span>
        </h1>
        <p class="text-xl md:text-2xl mb-8 text-green-300 animate-slide-up tagline-shadow animate-float">
            Trusted data, free forever
        </p>
        
        <div class="bg-gray-800/50 backdrop-blur-sm rounded-2xl p-6 max-w-2xl mx-auto animate-slide-up border border-gray-700">
            <p class="text-lg text-gray-200">
                Get instant, accurate answers about VA benefits with AI-powered assistance backed by official sources.
            </p>
        </div>
        
        <!-- Status Cards -->
        <div class="grid md:grid-cols-3 gap-6 mb-12 mt-12">
            <div class="bg-gray-800 rounded-2xl shadow-lg p-6 border border-gray-700 hover:shadow-xl hover:shadow-green-500/20 transition-all duration-300 hover:scale-105">
                <div class="flex items-center space-x-3">
                    <div class="w-12 h-12 bg-green-900 rounded-full flex items-center justify-center">
                        <span class="text-2xl">✅</span>
                    </div>
                    <div>
                        <h3 class="font-semibold text-gray-100">AI Powered</h3>
                        <p class="text-gray-400 text-sm">Advanced AI assistance</p>
                    </div>
                </div>
            </div>
            
            <div class="bg-gray-800 rounded-2xl shadow-lg p-6 border border-gray-700 hover:shadow-xl hover:shadow-green-500/20 transition-all duration-300 hover:scale-105">
                <div class="flex items-center space-x-3">
                    <div class="w-12 h-12 bg-green-900 rounded-full flex items-center justify-center">
                        <span class="text-2xl">🏠</span>
                    </div>
                    <div>
                        <h3 class="font-semibold text-gray-100">Trusted Sources</h3>
                        <p class="text-gray-400 text-sm">Official VA documentation</p>
                    </div>
                </div>
            </div>
            
            <div class="bg-gray-800 rounded-2xl shadow-lg p-6 border border-gray-700 hover:shadow-xl hover:shadow-green-500/20 transition-all duration-300 hover:scale-105">
                <div class="flex items-center space-x-3">
                    <div class="w-12 h-12 bg-green-900 rounded-full flex items-center justify-center">
                        <span class="text-2xl">🚀</span>
                    </div>
                    <div>
                        <h3 class="font-semibold text-gray-100">Instant Results</h3>
                        <p class="text-gray-400 text-sm">Real-time responses</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Main Interface Card -->
        <div class="bg-gray-800 rounded-3xl shadow-2xl p-8 max-w-4xl mx-auto border border-gray-700">
            <!-- Input Section -->
            <div class="space-y-6">
                <div class="relative">
                    <textarea id="prompt" 
                              placeholder="Ask a question about veterans benefits..."
                              class="w-full h-32 p-6 text-lg border-2 border-gray-600 rounded-2xl resize-none focus:border-green-500 focus:ring-4 focus:ring-green-500/20 transition-all duration-300 font-medium bg-gray-700 text-gray-100 placeholder-gray-400"></textarea>
                    
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
                            class="px-8 py-4 bg-gradient-to-r from-green-600 to-green-700 text-white text-lg font-semibold rounded-2xl hover:from-green-700 hover:to-green-800 transform hover:scale-105 transition-all duration-300 shadow-lg hover:shadow-xl hover:shadow-green-500/30">
                        Ask Question
                    </button>
                </div>
            </div>

            <!-- Sample Questions -->
            <div class="mt-8 pt-6 border-t border-gray-700">
                <p class="text-center text-gray-400 mb-4 font-medium">Try these sample questions:</p>
                <div class="flex flex-wrap justify-center gap-3">
                    <button onclick="setSampleQuestion('How do I apply for VA disability benefits?')" 
                            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-full text-sm font-medium transition-colors duration-200 hover:shadow-lg hover:shadow-green-500/20">
                        Disability Benefits
                    </button>
                    <button onclick="setSampleQuestion('What are the requirements for VA pension?')" 
                            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-full text-sm font-medium transition-colors duration-200 hover:shadow-lg hover:shadow-green-500/20">
                        Pension Requirements
                    </button>
                    <button onclick="setSampleQuestion('How do I use my GI Bill for education?')" 
                            class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-full text-sm font-medium transition-colors duration-200 hover:shadow-lg hover:shadow-green-500/20">
                        GI Bill Education
                    </button>
                </div>
            </div>
        </div>

        <!-- Response Section -->
        <div id="response" class="mt-12 max-w-4xl mx-auto hidden">
            <div class="bg-gray-800 rounded-3xl shadow-xl p-8 border border-gray-700">
                <div class="prose prose-lg max-w-none prose-invert">
                    <!-- Response content will be inserted here -->
                </div>
            </div>
        </div>

        <!-- Citations Section -->
        <div id="refs" class="mt-8 max-w-4xl mx-auto hidden">
            <div class="bg-gray-800 rounded-3xl shadow-xl p-8 border border-gray-700">
                <h3 class="text-2xl font-bold text-gray-100 mb-6 text-center">Sources & Footnotes</h3>
                <div class="space-y-4">
                    <!-- Citations will be inserted here -->
                </div>
            </div>
        </div>
    </div>

    <!-- Footer -->
    <div class="bg-gray-950 text-white py-12 mt-20 border-t border-gray-800">
        <div class="container mx-auto px-4 text-center">
            <h3 class="text-2xl font-bold mb-4 text-green-400">Veterans Benefits AI</h3>
            <p class="text-gray-400 mb-6">Empowering veterans with trusted information and AI assistance</p>
            <div class="flex justify-center space-x-6 text-sm text-gray-500">
                <span>© 2024 Veterans Benefits AI</span>
                <span>•</span>
                <span>Free Forever</span>
                <span>•</span>
                <span>Trusted Data</span>
            </div>
        </div>
    </div>

    <script>
        function setSampleQuestion(question) {
            document.getElementById('prompt').value = question;
        }
        
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
                    .replace(/### (.*?)(?=\n|$)/g, '<h3 class="text-2xl font-bold text-green-400 mt-8 mb-4">$1</h3>')
                    .replace(/#### (.*?)(?=\n|$)/g, '<h4 class="text-xl font-semibold text-green-300 mt-6 mb-3">$1</h4>');
                
                // Convert numbered lists
                formattedContent = formattedContent.replace(/\d+\.\s+(.*?)(?=\n\d+\.|$)/gs, function(match, content) {
                    return `<li class="mb-2 text-gray-200">${content}</li>`;
                });
                formattedContent = formattedContent.replace(/(<li.*?<\/li>)+/gs, function(match) {
                    return `<ol class="list-decimal list-inside space-y-2 my-4 text-gray-200">${match}</ol>`;
                });
                
                // Convert bullet lists
                formattedContent = formattedContent.replace(/- (.*?)(?=\n-|$)/gs, function(match, content) {
                    return `<li class="mb-2 text-gray-200">${content}</li>`;
                });
                formattedContent = formattedContent.replace(/(<li.*?<\/li>)+/gs, function(match) {
                    return `<ul class="list-disc list-inside space-y-2 my-4 text-gray-200">${match}</ul>`;
                });
                
                // Convert bold and italic text
                formattedContent = formattedContent
                    .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-green-300">$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em class="italic text-gray-300">$1</em>');
                
                // Convert line breaks
                formattedContent = formattedContent
                    .replace(/\n\n/g, '<br><br>')
                    .replace(/\n/g, '<br>');
                
                responseDiv.querySelector('.prose').innerHTML = `
                    <h2 class="text-3xl font-bold text-green-400 mb-6 text-center">Answer</h2>
                    <div class="text-gray-200 leading-relaxed">
                        ${formattedContent}
                    </div>
                `;
                
                // Display citations if available
                if (data.citations && data.citations.length > 0) {
                    refsDiv.style.display = 'block';
                    refsDiv.querySelector('.space-y-4').innerHTML = '';
                    
                    data.citations.forEach((c, i) => {
                        const citationDiv = document.createElement('div');
                        citationDiv.className = 'bg-gray-700 rounded-2xl p-6 border border-gray-600';
                        citationDiv.innerHTML = `
                            <div class="flex items-start space-x-4">
                                <div class="w-8 h-8 bg-green-900 rounded-full flex items-center justify-center flex-shrink-0">
                                    <span class="text-green-400 font-bold text-sm">${i+1}</span>
                                </div>
                                <div class="flex-1">
                                    <a href="${c.url}" target="_blank" class="text-lg font-semibold text-green-400 hover:text-green-300 transition-colors">
                                        ${c.file} (Page ${c.page})
                                    </a>
                                    ${c.source_text && c.source_text !== 'Source content not available' ? 
                                        `<div class="mt-3 p-4 bg-gray-800 rounded-xl border-l-4 border-green-500">
                                            <p class="text-gray-300 italic">${c.source_text}</p>
                                        </div>` : ''
                                    }
                                </div>
                            </div>
                        `;
                        refsDiv.querySelector('.space-y-4').appendChild(citationDiv);
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

        // Event listeners
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
