# 🚀 Production Deployment Guide

## Render.com Deployment

### 1. Fix Vector Dimension Mismatch

**CRITICAL**: Your current error shows Pinecone expects 1024D vectors but you're sending 1536D.

#### Option A: Update Embedding Model (Recommended)
```bash
# In your .env or Render environment variables:
EMBEDDING_MODEL=text-embedding-3-large
```

#### Option B: Recreate Pinecone Index  
If you prefer to use 1536D embeddings:
```python
# Recreate your Pinecone index with 1536 dimensions
# Use text-embedding-ada-002 or text-embedding-3-small
EMBEDDING_MODEL=text-embedding-3-small
```

### 2. Set Up Render.com Environment

#### A. Create New Web Service
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Use these settings:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Starter (upgrade to Standard for production)

#### B. Add Environment Variables
In Render dashboard, add these environment variables:

**Required:**
```
OPENAI_API_KEY=sk-your-key-here
PINECONE_API_KEY=your-pinecone-key
PINECONE_ENV=your-pinecone-environment  
PINECONE_INDEX=your-index-name
EMBEDDING_MODEL=text-embedding-3-large
```

**Optional (with defaults):**
```
MODEL_BIG=gpt-4o
MODEL_SMALL=gpt-4o-mini
SIM_THRESHOLD=0.92
CACHE_DB_PATH=/opt/render/project/data/cache.sqlite
FAISS_PATH=/opt/render/project/data/query_cache.faiss
```

#### C. Add Persistent Disk
1. In your service settings, add a **Disk**:
   - **Name**: `rag-cache-disk`
   - **Mount Path**: `/opt/render/project/data`
   - **Size**: 1GB (sufficient for cache)

### 3. Deploy Flask Frontend (Optional)

If you want to deploy the Flask frontend separately:

1. Create another Web Service
2. **Build Command**: `pip install -r requirements.txt`
3. **Start Command**: `python app.py`
4. **Environment Variables**:
   ```
   RAG_PIPELINE_URL=https://your-fastapi-service.onrender.com
   ```

### 4. Test Production Deployment

Once deployed, test these endpoints:

```bash
# Health check
curl https://your-service.onrender.com/healthz

# Should return: {"status":"ok","faiss_index_exists":true}

# Test question
curl -X POST https://your-service.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is machine learning?"}'

# Check metrics  
curl https://your-service.onrender.com/metrics
```

### 5. Production Considerations

#### Performance
- **Starter Plan**: Good for testing, limited resources
- **Standard Plan**: Recommended for production (more CPU/memory)
- **Pro Plan**: For high-traffic applications

#### Monitoring
- Enable **Health Checks**: `/healthz` endpoint
- Monitor **Logs**: Check for embedding dimension errors
- Track **Cache Performance**: Use `/metrics` endpoint

#### Security
- Set `ADMIN_TOKEN` for admin endpoints
- Use HTTPS (automatic on Render)
- Rotate API keys regularly

### 6. Cost Optimization

The semantic cache will significantly reduce costs:
- **Cache Hit Ratio**: Target >80% for 60% token savings
- **Monitor Usage**: Check `/metrics` for token usage
- **Tune Thresholds**: Adjust `SIM_THRESHOLD` based on performance

### 7. Troubleshooting

#### Vector Dimension Error
```
Vector dimension 1536 does not match the dimension of the index 1024
```
**Fix**: Set `EMBEDDING_MODEL=text-embedding-3-large` in environment variables

#### Cache Not Persisting
**Fix**: Ensure persistent disk is mounted at `/opt/render/project/data`

#### High Latency
**Fix**: Upgrade to Standard plan, tune `RETRIEVE_K` and `RERANK_K` parameters

---

## Alternative: Docker Deployment

If you prefer Docker, use this `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Create data directory for cache
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 🎯 Quick Checklist

- [ ] Fix embedding model dimension mismatch
- [ ] Set all required environment variables in Render
- [ ] Add persistent disk for cache storage
- [ ] Test health endpoint after deployment
- [ ] Verify cache is working with `/cache/stats`
- [ ] Monitor token usage and cache hit ratio
- [ ] Set up proper logging and monitoring

Your RAG pipeline will work perfectly on Render.com once the vector dimension issue is resolved! 🚀
