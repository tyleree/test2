<<<<<<< HEAD
# MCP Integration API Documentation

Your Flask application now has a clean, JSON-based API for integrating with the Pinecone MCP server at `https://prod-1-data.ke.pinecone.io/mcp/assistants/vb`.

## 🚀 Quick Start

### 1. Basic Question Asking
```bash
curl -X POST http://localhost:5000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are VA disability benefits?"}'
```

**Response:**
```json
{
  "success": true,
  "content": "VA disability benefits are...",
  "citations": [
    {
      "file": "VA_Handbook.pdf",
      "page": 15,
      "url": "https://...",
      "text": "Relevant text excerpt...",
      "confidence": 0.95
    }
  ],
  "source": "mcp_server",
  "metadata": {
    "model": "gpt-4",
    "usage": {"tokens": 150},
    "created": "2024-01-01T00:00:00Z"
  }
}
```

### 2. Advanced MCP Chat with Options
```bash
curl -X POST http://localhost:5000/mcp/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain VA healthcare enrollment",
    "options": {
      "temperature": 0.7,
      "max_tokens": 1000,
      "include_highlights": true
    }
  }'
```

## 📋 Available Endpoints

### POST `/ask`
Simple question asking with automatic fallback to Pinecone SDK if MCP fails.

**Request:**
```json
{
  "prompt": "Your question here"
}
```

**Response:**
```json
{
  "success": true,
  "content": "Answer content...",
  "citations": [...],
  "source": "mcp_server" | "pinecone_sdk",
  "metadata": {...}
}
```

### POST `/mcp/chat`
Advanced MCP chat with configurable options.

**Request:**
```json
{
  "prompt": "Your question here",
  "options": {
    "temperature": 0.7,
    "max_tokens": 1000,
    "include_highlights": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "content": "Answer content...",
  "citations": [...],
  "metadata": {...},
  "source": "mcp_server_advanced"
}
```

### GET `/mcp/status`
Check MCP server connection status.

**Response:**
```json
{
  "mcp_server_url": "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb",
  "api_key_configured": true,
  "connection_test": "success",
  "last_test_time": "now",
  "pinecone_sdk_status": "connected",
  "pinecone_index_status": "connected",
  "mcp_response_sample": {
    "has_content": true,
    "has_citations": true,
    "has_metadata": true
  }
}
```

### POST `/mcp/test`
Test MCP functionality with a specific prompt.

**Request:**
```json
{
  "prompt": "Test question"
}
```

**Response:**
```json
{
  "success": true,
  "mcp_server_status": "working",
  "response": {
    "content": "Test response...",
    "citations": [...],
    "metadata": {...}
  },
  "raw_response": {...}
}
```

### GET `/health`
Overall application health including MCP status.

**Response:**
```json
{
  "status": "healthy",
  "pinecone_available": true,
  "index_available": true,
  "mcp_endpoint": "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb",
  "mcp_api_key_configured": true,
  "environment": "production",
  "endpoints": {
    "main": "/",
    "ask": "/ask",
    "health": "/health",
    "mcp_test": "/mcp/test",
    "mcp_status": "/mcp/status",
    "mcp_chat": "/mcp/chat",
    "debug": "/debug"
  }
}
```

## 🔧 Configuration

### Environment Variables
Make sure your `env.txt` file contains:
```
PINECONE_API_KEY=your_api_key_here
PINECONE_INDEX_NAME=veterans-benefits
```

### MCP Server URL
The MCP server URL is configured in your `app.py`:
```python
MCP_SERVER_URL = "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb"
```

## 🧪 Testing

### Run the JSON Test Suite
```bash
python test_mcp_json.py
```

This will test all endpoints and show you exactly what's working.

### Manual Testing with curl
```bash
# Test health
curl http://localhost:5000/health

# Test MCP status
curl http://localhost:5000/mcp/status

# Test simple ask
curl -X POST http://localhost:5000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
```

## 🎯 Key Benefits of This Approach

1. **Clean JSON**: No HTML parsing, just pure JSON in/out
2. **Consistent Structure**: All responses follow the same format
3. **Error Handling**: Clear error messages with codes
4. **Fallback Support**: Automatic fallback to Pinecone SDK if MCP fails
5. **Metadata**: Rich response metadata including model info and usage
6. **Flexible Options**: Advanced chat endpoint with configurable parameters
7. **Easy Testing**: Comprehensive test suite included

## 🚨 Error Handling

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error description",
  "code": "error_code",
  "message": "Human-readable message"
}
```

Common error codes:
- `400`: Bad request (missing prompt, invalid JSON)
- `401`: Authentication failed
- `429`: Rate limit exceeded
- `500`: Server error
- `timeout`: Request timeout
- `connection`: Connection error

## 🔄 Fallback Strategy

The `/ask` endpoint uses a smart fallback strategy:

1. **Primary**: Try MCP server first
2. **Fallback**: If MCP fails, use Pinecone SDK
3. **Response**: Always indicate which source was used

This ensures your application stays functional even if the MCP server has issues.

## 📊 Response Structure

All successful responses include:
- `success`: Boolean indicating success
- `content`: The main answer text
- `citations`: Array of source references
- `source`: Which system provided the answer
- `metadata`: Additional response information

Citations include:
- `file`: Source document name
- `page`: Page number
- `url`: Direct link to source
- `text`: Relevant text excerpt
- `confidence`: Confidence score (if available)

This clean JSON approach makes it much easier to integrate with other systems, mobile apps, or frontend frameworks!

=======
# MCP Integration API Documentation

Your Flask application now has a clean, JSON-based API for integrating with the Pinecone MCP server at `https://prod-1-data.ke.pinecone.io/mcp/assistants/vb`.

## 🚀 Quick Start

### 1. Basic Question Asking
```bash
curl -X POST http://localhost:5000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What are VA disability benefits?"}'
```

**Response:**
```json
{
  "success": true,
  "content": "VA disability benefits are...",
  "citations": [
    {
      "file": "VA_Handbook.pdf",
      "page": 15,
      "url": "https://...",
      "text": "Relevant text excerpt...",
      "confidence": 0.95
    }
  ],
  "source": "mcp_server",
  "metadata": {
    "model": "gpt-4",
    "usage": {"tokens": 150},
    "created": "2024-01-01T00:00:00Z"
  }
}
```

### 2. Advanced MCP Chat with Options
```bash
curl -X POST http://localhost:5000/mcp/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain VA healthcare enrollment",
    "options": {
      "temperature": 0.7,
      "max_tokens": 1000,
      "include_highlights": true
    }
  }'
```

## 📋 Available Endpoints

### POST `/ask`
Simple question asking with automatic fallback to Pinecone SDK if MCP fails.

**Request:**
```json
{
  "prompt": "Your question here"
}
```

**Response:**
```json
{
  "success": true,
  "content": "Answer content...",
  "citations": [...],
  "source": "mcp_server" | "pinecone_sdk",
  "metadata": {...}
}
```

### POST `/mcp/chat`
Advanced MCP chat with configurable options.

**Request:**
```json
{
  "prompt": "Your question here",
  "options": {
    "temperature": 0.7,
    "max_tokens": 1000,
    "include_highlights": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "content": "Answer content...",
  "citations": [...],
  "metadata": {...},
  "source": "mcp_server_advanced"
}
```

### GET `/mcp/status`
Check MCP server connection status.

**Response:**
```json
{
  "mcp_server_url": "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb",
  "api_key_configured": true,
  "connection_test": "success",
  "last_test_time": "now",
  "pinecone_sdk_status": "connected",
  "pinecone_index_status": "connected",
  "mcp_response_sample": {
    "has_content": true,
    "has_citations": true,
    "has_metadata": true
  }
}
```

### POST `/mcp/test`
Test MCP functionality with a specific prompt.

**Request:**
```json
{
  "prompt": "Test question"
}
```

**Response:**
```json
{
  "success": true,
  "mcp_server_status": "working",
  "response": {
    "content": "Test response...",
    "citations": [...],
    "metadata": {...}
  },
  "raw_response": {...}
}
```

### GET `/health`
Overall application health including MCP status.

**Response:**
```json
{
  "status": "healthy",
  "pinecone_available": true,
  "index_available": true,
  "mcp_endpoint": "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb",
  "mcp_api_key_configured": true,
  "environment": "production",
  "endpoints": {
    "main": "/",
    "ask": "/ask",
    "health": "/health",
    "mcp_test": "/mcp/test",
    "mcp_status": "/mcp/status",
    "mcp_chat": "/mcp/chat",
    "debug": "/debug"
  }
}
```

## 🔧 Configuration

### Environment Variables
Make sure your `env.txt` file contains:
```
PINECONE_API_KEY=your_api_key_here
PINECONE_INDEX_NAME=veterans-benefits
```

### MCP Server URL
The MCP server URL is configured in your `app.py`:
```python
MCP_SERVER_URL = "https://prod-1-data.ke.pinecone.io/mcp/assistants/vb"
```

## 🧪 Testing

### Run the JSON Test Suite
```bash
python test_mcp_json.py
```

This will test all endpoints and show you exactly what's working.

### Manual Testing with curl
```bash
# Test health
curl http://localhost:5000/health

# Test MCP status
curl http://localhost:5000/mcp/status

# Test simple ask
curl -X POST http://localhost:5000/ask \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
```

## 🎯 Key Benefits of This Approach

1. **Clean JSON**: No HTML parsing, just pure JSON in/out
2. **Consistent Structure**: All responses follow the same format
3. **Error Handling**: Clear error messages with codes
4. **Fallback Support**: Automatic fallback to Pinecone SDK if MCP fails
5. **Metadata**: Rich response metadata including model info and usage
6. **Flexible Options**: Advanced chat endpoint with configurable parameters
7. **Easy Testing**: Comprehensive test suite included

## 🚨 Error Handling

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error description",
  "code": "error_code",
  "message": "Human-readable message"
}
```

Common error codes:
- `400`: Bad request (missing prompt, invalid JSON)
- `401`: Authentication failed
- `429`: Rate limit exceeded
- `500`: Server error
- `timeout`: Request timeout
- `connection`: Connection error

## 🔄 Fallback Strategy

The `/ask` endpoint uses a smart fallback strategy:

1. **Primary**: Try MCP server first
2. **Fallback**: If MCP fails, use Pinecone SDK
3. **Response**: Always indicate which source was used

This ensures your application stays functional even if the MCP server has issues.

## 📊 Response Structure

All successful responses include:
- `success`: Boolean indicating success
- `content`: The main answer text
- `citations`: Array of source references
- `source`: Which system provided the answer
- `metadata`: Additional response information

Citations include:
- `file`: Source document name
- `page`: Page number
- `url`: Direct link to source
- `text`: Relevant text excerpt
- `confidence`: Confidence score (if available)

This clean JSON approach makes it much easier to integrate with other systems, mobile apps, or frontend frameworks!

>>>>>>> b6374a9 (Add new features and fix bugs)
