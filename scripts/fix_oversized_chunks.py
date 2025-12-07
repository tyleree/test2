#!/usr/bin/env python3
"""
Fix Oversized Chunks in Corpus

This script identifies and fixes chunks that are too large for the OpenAI
embedding API (8192 token limit). It specifically handles:
- appeals_remands (BoardRemands) - splits by subsection (7.G.x.y format)
- Any other oversized chunks

Run this after chunk_corpus_v2.py to fix size issues.
"""

import re
import json
from pathlib import Path
from datetime import datetime

# Configuration
CORPUS_DIR = Path(__file__).parent.parent / "veteran-ai-spark" / "corpus"
OUTPUT_FILE = CORPUS_DIR / "vbkb_restructured.json"
MAX_CHUNK_SIZE = 6000  # Characters (~1500 tokens, well under 8192 limit)

SOURCE_URL = "https://www.knowva.ebenefits.va.gov/system/templates/selfservice/va_ssnew/help/customer/locale/en-US/portal/554400000001018/content/554400000140917/M21-5-Chapter-7-Section-G-Board-of-Veterans-Appeals-Board-Decisions-and-Remands"


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough: 1 token ≈ 4 chars)"""
    return len(text) // 4


def load_corpus():
    """Load the existing corpus."""
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_corpus(chunks):
    """Save the corpus."""
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(chunks)} chunks to {OUTPUT_FILE}")


def analyze_corpus():
    """Analyze corpus for oversized chunks."""
    chunks = load_corpus()
    
    print("\n" + "=" * 70)
    print("CORPUS ANALYSIS - Identifying Oversized Chunks")
    print("=" * 70)
    
    oversized = []
    for i, chunk in enumerate(chunks):
        content = chunk.get("content", "")
        tokens = estimate_tokens(content)
        
        if tokens > 1500:  # Flag anything over ~1500 tokens
            entry_id = chunk.get("entry_id", f"unknown_{i}")
            topic = chunk.get("topic", "Unknown")
            print(f"\n🔴 [{i}] {entry_id}")
            print(f"   Topic: {topic}")
            print(f"   Size: {len(content):,} chars / ~{tokens:,} tokens")
            oversized.append({
                "index": i,
                "entry_id": entry_id,
                "tokens": tokens,
                "chars": len(content)
            })
    
    print(f"\n\n📊 SUMMARY: Found {len(oversized)} oversized chunks")
    return oversized


def clean_content(text: str) -> str:
    """Clean markdown content by removing navigation junk."""
    lines = text.split('\n')
    cleaned = []
    
    skip_patterns = [
        r'^\[<-- Previous Section\]',
        r'^\[Next Section -->\]',
        r'^\[To Top\]',
        r'^> Article ID:',
        r'^You can view this article at:',
        r'^Article added to bookmarks',
        r'^Was this article useful\?',
        r'^\[Yes\].*\[No\]',
        r'^- ###### Attachments',
        r'^- ###### Related Articles',
        r'^\[View All\]',
        r'^Heading Level six',
        r'^\[.*\.docx\]',
        r'^- \[M21-5',
    ]
    
    for line in lines:
        skip = False
        for pattern in skip_patterns:
            if re.match(pattern, line.strip()):
                skip = True
                break
        if not skip:
            cleaned.append(line)
    
    return '\n'.join(cleaned)


def chunk_appeals_remands():
    """
    Special chunker for appeals_remands that splits by subsection.
    
    The document has this structure:
    - Section 1: 7.G.1.a through 7.G.1.j (Reviewing and Processing Board Decisions)
    - Section 2: 7.G.2.a through 7.G.2.f (Disagreements With Board Decisions)
    - Section 3: 7.G.3.a through 7.G.3.g (Remands)
    - Section 4: 7.G.4.a through 7.G.4.g (Developing, Reviewing, and Transferring Remands)
    """
    file_path = CORPUS_DIR / "appeals_remands"
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        raw_content = f.read()
    
    content = clean_content(raw_content)
    
    print("\n📚 Chunking appeals_remands by subsections...")
    
    chunks = []
    
    # Define section info
    sections = {
        "1": {
            "title": "Reviewing and Processing Board Decisions",
            "pattern": r'## \*\*1\.\s+Reviewing and Processing Board Decisions\*\*',
        },
        "2": {
            "title": "Disagreements With Board Decisions", 
            "pattern": r'## \*\*2\.\s+Disagreements With Board Decisions\*\*',
        },
        "3": {
            "title": "Remands",
            "pattern": r'## \*\*3\.\s+Remands\*\*',
        },
        "4": {
            "title": "Developing, Reviewing, and Transferring Remands",
            "pattern": r'4\.\s+Developing, Reviewing, and Transferring Remands',
        }
    }
    
    # Find all subsection markers (### **7.G.x.y. Title** or similar)
    # Pattern matches: ### **7.G.1.a. Title** or ### ****7.G.1.a. Title****
    subsection_pattern = r'###\s+\*{2,4}(7\.G\.\d+\.[a-z](?:\.\s+|\.\s*\*{2,4}\s+)?)([^*\n]+)'
    
    matches = list(re.finditer(subsection_pattern, content))
    print(f"   Found {len(matches)} subsections")
    
    # Also find Introduction and Change Date entries
    intro_pattern = r'###\s+\*{2,4}Introduction\*{2,4}\s+\|\s+\|([^|]+)\|'
    change_pattern = r'###\s+\*{2,4}Change Date\*{2,4}\s+\|\s+\|([^|]+)\|'
    
    for i, match in enumerate(matches):
        subsection_id = match.group(1).strip().rstrip('.*')  # e.g., "7.G.1.a"
        subsection_title = match.group(2).strip().rstrip('*').strip()
        
        start = match.start()
        
        # Find end (next subsection or end of content)
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            # Look for next main section or end
            next_section = re.search(r'\n## \*\*\d+\.', content[match.end():])
            if next_section:
                end = match.end() + next_section.start()
            else:
                end = len(content)
        
        chunk_content = content[start:end].strip()
        chunk_content = clean_content(chunk_content)
        
        # Remove excessive whitespace
        chunk_content = re.sub(r'\n{4,}', '\n\n\n', chunk_content)
        chunk_content = re.sub(r'\|\s+\|\s+\|\s+\|', '', chunk_content)  # Empty table rows
        
        tokens = estimate_tokens(chunk_content)
        
        # If still too large, split further
        if tokens > 2000:
            print(f"   ⚠️  {subsection_id} is {tokens} tokens - splitting further...")
            sub_chunks = split_large_chunk(chunk_content, subsection_id, subsection_title)
            chunks.extend(sub_chunks)
        else:
            # Determine parent section
            section_num = subsection_id.split('.')[2] if '.' in subsection_id else "1"
            section_title = sections.get(section_num, {}).get("title", "Board Decisions and Remands")
            
            chunks.append({
                "entry_id": f"BoardRemands-{subsection_id}",
                "topic": f"{subsection_title} ({subsection_id})",
                "content": chunk_content,
                "source_url": SOURCE_URL + f"#{subsection_id.replace('.', '')}",
                "aliases": ["remand", "board remand", "BVA", "appeals", subsection_id.lower()],
                "type": "appeals",
                "section": section_title,
            })
            print(f"   ✅ {subsection_id}: {subsection_title[:50]}... ({tokens} tokens)")
    
    # Also add introduction chunks for each section
    section_intros = [
        ("1", "Reviewing and Processing Board Decisions", r'## \*\*1\.\s+Reviewing'),
        ("2", "Disagreements With Board Decisions", r'## \*\*2\.\s+Disagreements'),  
        ("3", "Remands", r'## \*\*3\.\s+Remands'),
        ("4", "Developing, Reviewing, and Transferring Remands", r'\*\*4\.\s+Developing'),
    ]
    
    for sec_num, sec_title, pattern in section_intros:
        match = re.search(pattern, content)
        if match:
            # Get intro content (between section header and first subsection)
            start = match.start()
            # Find first ### header
            first_sub = re.search(r'\n###\s+\*{2,4}', content[match.end():])
            if first_sub:
                end = match.end() + first_sub.start()
                intro_content = content[start:end].strip()
                intro_content = clean_content(intro_content)
                
                if len(intro_content) > 100:  # Only add if there's meaningful content
                    chunks.append({
                        "entry_id": f"BoardRemands-Section{sec_num}-Intro",
                        "topic": f"{sec_title} - Overview",
                        "content": intro_content[:MAX_CHUNK_SIZE],
                        "source_url": SOURCE_URL + f"#{sec_num}",
                        "aliases": ["remand", "board remand", "BVA", "appeals"],
                        "type": "appeals",
                        "section": sec_title,
                    })
    
    print(f"\n   📊 Created {len(chunks)} chunks from appeals_remands")
    return chunks


def split_large_chunk(content: str, base_id: str, base_title: str) -> list:
    """Split a large chunk by table rows or paragraphs."""
    chunks = []
    
    # Try to split by major table boundaries or horizontal rules
    parts = re.split(r'\n\* \* \*\n|\n---\n|\n\|\s*\*\*Step\*\*', content)
    
    if len(parts) > 1:
        for i, part in enumerate(parts):
            if len(part.strip()) > 100:  # Only keep meaningful parts
                chunks.append({
                    "entry_id": f"BoardRemands-{base_id}-part{i+1}",
                    "topic": f"{base_title} (Part {i+1})",
                    "content": part.strip()[:MAX_CHUNK_SIZE],
                    "source_url": SOURCE_URL,
                    "aliases": ["remand", "board remand", "BVA"],
                    "type": "appeals",
                })
    else:
        # Just truncate if can't split
        chunks.append({
            "entry_id": f"BoardRemands-{base_id}",
            "topic": base_title,
            "content": content[:MAX_CHUNK_SIZE],
            "source_url": SOURCE_URL,
            "aliases": ["remand", "board remand", "BVA"],
            "type": "appeals",
        })
    
    return chunks


def remove_old_board_remands(chunks: list) -> list:
    """Remove old BoardRemands chunks from the corpus."""
    original_count = len(chunks)
    chunks = [c for c in chunks if not c.get("entry_id", "").startswith("BoardRemands")]
    removed = original_count - len(chunks)
    print(f"🗑️  Removed {removed} old BoardRemands chunks")
    return chunks


def main():
    print("\n" + "=" * 70)
    print("FIX OVERSIZED CHUNKS")
    print("=" * 70)
    
    # Step 1: Load corpus and analyze
    print("\n📖 Loading corpus...")
    chunks = load_corpus()
    print(f"   Loaded {len(chunks)} chunks")
    
    # Step 2: Remove old BoardRemands chunks
    chunks = remove_old_board_remands(chunks)
    
    # Step 3: Re-chunk appeals_remands properly
    new_chunks = chunk_appeals_remands()
    
    # Step 4: Add new chunks
    chunks.extend(new_chunks)
    print(f"\n✅ Total chunks: {len(chunks)}")
    
    # Step 5: Verify no oversized chunks
    print("\n🔍 Verifying chunk sizes...")
    oversized = []
    for chunk in chunks:
        tokens = estimate_tokens(chunk.get("content", ""))
        if tokens > 2000:
            oversized.append(chunk.get("entry_id"))
    
    if oversized:
        print(f"⚠️  Still have {len(oversized)} oversized chunks:")
        for eid in oversized:
            print(f"   - {eid}")
    else:
        print("✅ All chunks are within size limits!")
    
    # Step 6: Save
    save_corpus(chunks)
    
    # Step 7: Update corpus version to force cache invalidation
    print("\n📝 Note: Update SOURCE_ID_PREFIX in chunk_corpus_v2.py to force cache refresh")
    
    print("\n✅ Done! Deploy to Render to test.")


if __name__ == "__main__":
    main()

