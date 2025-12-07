#!/usr/bin/env python3
"""
RAG QA Testing Script

Executes test questions against the RAG chatbot API and generates
a markdown report with all Q&A pairs for manual review.

Uses only built-in Python libraries (no pip install required).
"""

import urllib.request
import urllib.error
import json
import time
import re
import ssl
from datetime import datetime
from pathlib import Path

# Configuration
API_URL = "https://veteransbenefits.ai/ask"
QUESTIONS_FILE = Path(__file__).parent.parent / "qa_test_questions.txt"
RESULTS_JSON = Path(__file__).parent.parent / "qa_test_results.json"
RESULTS_MD = Path(__file__).parent.parent / "qa_test_results.md"

# Rate limiting - add delay to avoid hitting OpenAI TPM limits
# With gpt-4.1-mini at 200K TPM and ~3K tokens/query, we can do ~66/min
# Using 1.5s delay = 40 queries/min = safe margin under the limit
DELAY_BETWEEN_REQUESTS = 1.5  # seconds - prevents rate limiting

# Resume from specific question (0 = start from beginning)
START_FROM_QUESTION = 0  # Start from beginning

# Create SSL context - use unverified for macOS compatibility
# (The API is served over HTTPS from Render, a trusted provider)
ssl_context = ssl._create_unverified_context()


def load_questions(filepath: Path) -> list:
    """Load questions from the questions file, parsing category tags."""
    questions = []
    
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Try format: CATEGORY-N | Question
            if ' | ' in line:
                parts = line.split(' | ', 1)
                if len(parts) == 2:
                    category_id = parts[0].strip()
                    question = parts[1].strip()
                    # Extract category from ID (e.g., "CARDIO-1" -> "CARDIO")
                    category = category_id.rsplit('-', 1)[0] if '-' in category_id else category_id
                    questions.append({
                        "id": category_id,
                        "category": category,
                        "question": question
                    })
                    continue
            
            # Fallback: Parse [CATEGORY-N] question format
            match = re.match(r'\[([A-Z0-9-]+)\]\s*(.+)', line)
            if match:
                category_id = match.group(1)
                question = match.group(2)
                category = category_id.rsplit('-', 1)[0] if '-' in category_id else category_id
                questions.append({
                    "id": category_id,
                    "category": category,
                    "question": question
                })
    
    return questions


def ask_question(question: str) -> dict:
    """Send a question to the RAG API and return the response."""
    try:
        # Prepare request
        data = json.dumps({"prompt": question}).encode('utf-8')
        req = urllib.request.Request(
            API_URL,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            method='POST'
        )
        
        # Make request
        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
            response_data = response.read().decode('utf-8')
            data = json.loads(response_data)
            
            return {
                "success": data.get("success", False),
                "content": data.get("content", ""),
                "citations": data.get("citations", []),
                "source": data.get("source", ""),
                "metadata": data.get("metadata", {}),
                "status_code": response.status,
                "error": None
            }
    
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode('utf-8')[:200]
        except:
            pass
        return {
            "success": False,
            "content": "",
            "citations": [],
            "source": "",
            "metadata": {},
            "status_code": e.code,
            "error": f"HTTP {e.code}: {error_body}"
        }
    
    except urllib.error.URLError as e:
        return {
            "success": False,
            "content": "",
            "citations": [],
            "source": "",
            "metadata": {},
            "status_code": 0,
            "error": f"URL Error: {str(e.reason)}"
        }
    
    except TimeoutError:
        return {
            "success": False,
            "content": "",
            "citations": [],
            "source": "",
            "metadata": {},
            "status_code": 0,
            "error": "Request timed out after 60 seconds"
        }
    
    except Exception as e:
        return {
            "success": False,
            "content": "",
            "citations": [],
            "source": "",
            "metadata": {},
            "status_code": 0,
            "error": str(e)
        }


def run_tests(questions: list, start_from: int = 0) -> list:
    """Execute all test questions and collect results.
    
    Args:
        questions: List of question dictionaries
        start_from: 1-indexed question number to start from (0 = start from beginning)
    """
    results = []
    total = len(questions)
    
    # Adjust for 1-indexed start_from
    skip_count = max(0, start_from - 1) if start_from > 0 else 0
    questions_to_run = questions[skip_count:]
    
    print(f"\n{'='*60}")
    print(f"RAG QA Testing - {len(questions_to_run)} Questions")
    if skip_count > 0:
        print(f"(Resuming from question {start_from}, skipping first {skip_count})")
    print(f"API: {API_URL}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    for i, q in enumerate(questions_to_run, start_from if start_from > 0 else 1):
        print(f"[{i:3d}/{total}] {q['id']}: {q['question'][:50]}...")
        
        start_time = time.time()
        response = ask_question(q['question'])
        elapsed = time.time() - start_time
        
        result = {
            "number": i,
            "id": q['id'],
            "category": q['category'],
            "question": q['question'],
            "response": response,
            "elapsed_seconds": round(elapsed, 2)
        }
        results.append(result)
        
        if response['success']:
            content_preview = response['content'][:80].replace('\n', ' ')
            print(f"    ✓ Success ({elapsed:.1f}s): {content_preview}...")
        else:
            print(f"    ✗ Failed ({elapsed:.1f}s): {response['error']}")
        
        # Rate limiting
        if i < total:
            time.sleep(DELAY_BETWEEN_REQUESTS)
    
    print(f"\n{'='*60}")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    success_count = sum(1 for r in results if r['response']['success'])
    print(f"Results: {success_count}/{len(questions_to_run)} successful")
    print(f"{'='*60}\n")
    
    return results


def save_results_json(results: list, filepath: Path):
    """Save raw results to JSON for later analysis."""
    with open(filepath, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "api_url": API_URL,
            "total_questions": len(results),
            "results": results
        }, f, indent=2)
    print(f"Saved JSON results to: {filepath}")


def generate_markdown_report(results: list, filepath: Path):
    """Generate a formatted markdown report for manual review."""
    
    lines = [
        "# RAG QA Test Results",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**API:** {API_URL}",
        f"**Total Questions:** {len(results)}",
        "",
        "## Summary",
        "",
    ]
    
    # Calculate summary stats
    success_count = sum(1 for r in results if r['response']['success'])
    failed_count = len(results) - success_count
    
    # Group by category
    categories = {}
    for r in results:
        cat = r['category']
        if cat not in categories:
            categories[cat] = {'total': 0, 'success': 0}
        categories[cat]['total'] += 1
        if r['response']['success']:
            categories[cat]['success'] += 1
    
    lines.extend([
        f"- **Successful:** {success_count}/{len(results)}",
        f"- **Failed:** {failed_count}/{len(results)}",
        "",
        "### By Category",
        "",
        "| Category | Success | Total |",
        "|----------|---------|-------|",
    ])
    
    for cat in sorted(categories.keys()):
        stats = categories[cat]
        lines.append(f"| {cat} | {stats['success']} | {stats['total']} |")
    
    lines.extend([
        "",
        "---",
        "",
        "## Detailed Results",
        "",
        "Review each response and check the boxes for any problems identified.",
        "",
    ])
    
    # Individual results
    for r in results:
        resp = r['response']
        
        lines.extend([
            f"### Question {r['number']}: {r['id']}",
            "",
            f"**Query:** {r['question']}",
            "",
            f"**Category:** {r['category']}",
            "",
            f"**Response Time:** {r['elapsed_seconds']}s",
            "",
        ])
        
        if resp['success']:
            # Answer
            lines.extend([
                "**Answer:**",
                "",
                resp['content'],
                "",
            ])
            
            # Sources
            if resp['citations']:
                lines.append("**Sources Cited:**")
                for cite in resp['citations']:
                    if isinstance(cite, dict):
                        url = cite.get('url', cite.get('source_url', 'N/A'))
                        topic = cite.get('topic', cite.get('title', 'Unknown'))
                        lines.append(f"- [{topic}]({url})")
                    else:
                        lines.append(f"- {cite}")
                lines.append("")
            else:
                lines.append("**Sources Cited:** None")
                lines.append("")
            
            # Metadata
            meta = resp.get('metadata', {})
            if meta:
                confidence = meta.get('confidence', meta.get('semantic_similarity', 'N/A'))
                chunks = meta.get('chunks_retrieved', 'N/A')
                lines.extend([
                    f"**Confidence:** {confidence}",
                    f"**Chunks Retrieved:** {chunks}",
                    "",
                ])
        else:
            lines.extend([
                f"**Error:** {resp['error']}",
                "",
            ])
        
        # Problem checklist
        lines.extend([
            "**Problems Identified:**",
            "- [ ] Incorrect information",
            "- [ ] Wrong sources cited",
            "- [ ] Missing key information",
            "- [ ] Hallucinated content",
            "- [ ] Low confidence / poor retrieval",
            "- [ ] Response too vague",
            "- [ ] Response too verbose",
            "",
            "**Notes:**",
            "",
            "_Add observations here_",
            "",
            "---",
            "",
        ])
    
    # Write the file
    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Saved Markdown report to: {filepath}")


def main():
    """Main entry point."""
    # Load questions
    if not QUESTIONS_FILE.exists():
        print(f"Error: Questions file not found: {QUESTIONS_FILE}")
        return 1
    
    questions = load_questions(QUESTIONS_FILE)
    print(f"Loaded {len(questions)} questions from {QUESTIONS_FILE}")
    
    if not questions:
        print("Error: No questions loaded!")
        return 1
    
    # Run tests (with optional resume from specific question)
    results = run_tests(questions, start_from=START_FROM_QUESTION)
    
    # Save results (append mode if resuming)
    if START_FROM_QUESTION > 1:
        # Try to load existing results and merge
        try:
            with open(RESULTS_JSON, 'r') as f:
                existing = json.load(f)
                existing_results = existing.get('results', [])
                # Keep results up to resume point
                kept = [r for r in existing_results if r['number'] < START_FROM_QUESTION]
                results = kept + results
                print(f"Merged {len(kept)} existing results with {len(results) - len(kept)} new results")
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    save_results_json(results, RESULTS_JSON)
    generate_markdown_report(results, RESULTS_MD)
    
    print(f"\nDone! Review the results in:")
    print(f"  - {RESULTS_MD} (formatted report)")
    print(f"  - {RESULTS_JSON} (raw data)")
    
    return 0


if __name__ == "__main__":
    exit(main())
