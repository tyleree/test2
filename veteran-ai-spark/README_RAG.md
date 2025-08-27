# FastAPI RAG Pipeline with Multi-Layer Semantic Cache

High-performance RAG pipeline with semantic caching to deliver answers at a fraction of token cost.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Fill in your OPENAI_API_KEY, PINECONE_API_KEY, etc.

# Run server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Test API
curl -X POST localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is machine learning?"}'
```

## Key Features

- **Multi-layer caching**: Exact + semantic similarity with FAISS
- **Token optimization**: Cache final answers + compressed contexts
- **Safety validation**: Check source relevance before cache hits  
- **Hybrid retrieval**: Pinecone + optional BM25
- **Admin integration**: Metrics for existing analytics dashboard

## API Endpoints

- `POST /ask` - Ask questions with caching
- `GET /healthz` - Health check
- `GET /cache/stats` - Cache performance 
- `GET /metrics` - Comprehensive metrics
- `POST /cache/clear` - Clear cache (admin only)
- `GET /admin/analytics` - Dashboard integration

## Cost Math

- Small model: ~300-600 tokens (rewrite + compress)
- Big model: ~1.8-2.3k input, ~300-700 output  
- Cache saves: ~2x full pipeline cost on hits

## Configuration

Key environment variables:
- `SIM_THRESHOLD=0.92` - Semantic similarity threshold
- `DOC_OVERLAP_MIN=0.6` - Validation overlap requirement
- `COMPRESS_BUDGET_TOKENS=2200` - Context compression limit
- `MAX_SOURCES=6` - Maximum sources per answer

## Testing

```bash
pytest tests/test_semantic_cache.py    # Cache functionality
pytest tests/test_end_to_end.py        # Full pipeline
```

## Cache Strategy

1. **Exact hit**: Hash-based lookup for identical queries
2. **Semantic hit**: FAISS cosine similarity ≥ 0.92 + validation
3. **Cache miss**: Full pipeline with result caching

## Integration Notes

- Integrates with existing AdminAnalytics component via `/admin/analytics`
- Shares Pinecone index with Flask app
- Metrics formatted for token usage dashboard section
- Run alongside existing Flask server (different ports)








