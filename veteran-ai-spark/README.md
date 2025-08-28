# RAG Flask Backend

Production-ready Flask RAG backend with hybrid retrieval, semantic caching, and evaluation capabilities.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Configure
cp env.example .env
# Edit .env with your API keys

# Ingest documents
python -m app.ingestion --src ./corpus --index your-index-name

# Run server
python wsgi.py
```

## API Usage

```bash
# Ask a question
curl -X POST http://localhost:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are VA disability benefits?"}'

# Health check
curl http://localhost:5000/api/healthz

# Metrics
curl http://localhost:5000/api/metrics
```

## Features

- **Hybrid Retrieval**: Pinecone vector + BM25 search
- **CrossEncoder Reranking**: Precise relevance scoring  
- **Quote Compression**: Minimal verbatim spans
- **Semantic Caching**: FAISS-based similarity matching
- **Structured Output**: Clean JSON + sanitized HTML
- **Evaluation Harness**: Recall@K, MRR, Quote-F1 metrics
- **Debug Endpoints**: Detailed pipeline inspection

## Configuration

Key environment variables:

```bash
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
PINECONE_INDEX=your-index-name
SECRET_KEY=your-secret-key

# Optional tuning
RETRIEVAL_TOP_K=50
RERANK_TOP_K=8
COMPRESS_BUDGET_TOKENS=2200
SEMANTIC_THRESHOLD=0.92
```

## Evaluation

```bash
python -m app.eval.harness --qas app/eval/qas.csv
```

## Testing

```bash
pytest
```

## Deployment

Render.com ready - set environment variables in dashboard and deploy.