#!/usr/bin/env python3
"""
Fix ALL Oversized Chunks in Corpus

This script identifies and splits ALL chunks that exceed the token limit.
It handles:
- PTSDStressor chunks (split by subsection markers)
- BlueWaterNavy (split by Q&A pairs)
- LayEvidence (split by subsection markers)
- GIBill (split by topic)
- GEN references (split by groups of references)

IMPORTANT: This script now uses the CORRECT schema matching chunk_corpus_v2.py
to ensure all chunks have proper fields for retrieval and citation.
"""

import re
import json
from datetime import datetime
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent / "veteran-ai-spark" / "corpus"
OUTPUT_FILE = CORPUS_DIR / "vbkb_restructured.json"
MAX_TOKENS = 1500  # Target max tokens per chunk

# Source ID must match the main chunking script
SOURCE_ID = "veteransbenefitskb_2025_12_07_v2"

# Default URLs for topics that were missing them
DEFAULT_URLS = {
    "BlueWater": "https://www.veteransbenefitskb.com/bluewater",
    "PTSD": "https://www.veteransbenefitskb.com/ptsd",
    "Stressor": "https://www.veteransbenefitskb.com/ptsd#stressor",
    "LayEvidence": "https://www.veteransbenefitskb.com/layevidence",
    "GEN": "https://www.veteransbenefitskb.com/faq",
    "Bilateral": "https://www.veteransbenefitskb.com/vamath#bilateral",
    "Appeal": "https://www.veteransbenefitskb.com/appeals",
}


def estimate_tokens(text: str) -> int:
    """Estimate token count (1 token ≈ 4 chars)"""
    return len(text) // 4


def load_corpus():
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_corpus(chunks):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(chunks)} chunks to {OUTPUT_FILE}")


def get_default_url(entry_id: str) -> str:
    """Get default URL based on entry_id prefix."""
    for prefix, url in DEFAULT_URLS.items():
        if prefix in entry_id:
            return url
    return "https://www.veteransbenefitskb.com"


def create_chunk(entry_id: str, topic: str, content: str, 
                 url: str, aliases: list, chunk_type: str, 
                 parent_topic: str, original_heading: str = None) -> dict:
    """
    Create a chunk with the CORRECT schema matching chunk_corpus_v2.py.
    
    Required fields:
    - source_id: For tracking source
    - entry_id: Unique identifier
    - topic: Display topic
    - original_heading: Original section heading
    - type: Content type
    - url: For citations (NOT source_url!)
    - last_updated: For cache management
    - content: The actual content
    - parent_topic: Parent topic for context
    - aliases: Search aliases
    """
    return {
        "source_id": SOURCE_ID,
        "entry_id": entry_id,
        "topic": topic,
        "original_heading": original_heading or topic,
        "type": chunk_type,
        "url": url if url else get_default_url(entry_id),
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "content": content,
        "parent_topic": parent_topic,
        "aliases": aliases
    }


def split_by_subsections(content: str, base_id: str, base_topic: str, 
                         url: str, aliases: list, chunk_type: str,
                         parent_topic: str) -> list:
    """Split content by ### subsection markers."""
    chunks = []
    
    # Find subsection markers like ### IV.ii.2.E.3.a or ### **8.C.4.a.
    subsection_pattern = r'###\s+\*{0,4}(\d+\.[A-Za-z]+\.\d+\.[a-z](?:\.\s+|\.\s*\*{2,4}\s+)?)'
    
    matches = list(re.finditer(subsection_pattern, content))
    
    if len(matches) > 1:
        for i, match in enumerate(matches):
            sub_id = match.group(1).strip().rstrip('.*')
            
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            
            chunk_content = content[start:end].strip()
            tokens = estimate_tokens(chunk_content)
            
            # If still too large, split by paragraph
            if tokens > MAX_TOKENS * 2:
                sub_chunks = split_by_paragraphs(
                    chunk_content, f"{base_id}-{sub_id}", 
                    base_topic, url, aliases, chunk_type, parent_topic
                )
                chunks.extend(sub_chunks)
            else:
                chunks.append(create_chunk(
                    entry_id=f"{base_id}-{sub_id}",
                    topic=f"{base_topic} ({sub_id})",
                    content=chunk_content,
                    url=url,
                    aliases=aliases,
                    chunk_type=chunk_type,
                    parent_topic=parent_topic,
                    original_heading=f"{base_topic} - Section {sub_id}"
                ))
        return chunks
    
    # Fall back to splitting by horizontal rules
    return split_by_rules(content, base_id, base_topic, url, aliases, chunk_type, parent_topic)


def split_by_rules(content: str, base_id: str, base_topic: str,
                   url: str, aliases: list, chunk_type: str,
                   parent_topic: str) -> list:
    """Split content by horizontal rules (* * * or ---)"""
    chunks = []
    
    parts = re.split(r'\n\* \* \*\n|\n---\n', content)
    
    current_chunk = ""
    part_num = 1
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        potential = current_chunk + "\n\n" + part if current_chunk else part
        
        if estimate_tokens(potential) > MAX_TOKENS and current_chunk:
            chunks.append(create_chunk(
                entry_id=f"{base_id}-part{part_num}",
                topic=f"{base_topic} (Part {part_num})",
                content=current_chunk.strip(),
                url=url,
                aliases=aliases,
                chunk_type=chunk_type,
                parent_topic=parent_topic,
                original_heading=base_topic
            ))
            part_num += 1
            current_chunk = part
        else:
            current_chunk = potential
    
    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(create_chunk(
            entry_id=f"{base_id}-part{part_num}",
            topic=f"{base_topic} (Part {part_num})",
            content=current_chunk.strip(),
            url=url,
            aliases=aliases,
            chunk_type=chunk_type,
            parent_topic=parent_topic,
            original_heading=base_topic
        ))
    
    return chunks


def split_by_paragraphs(content: str, base_id: str, base_topic: str,
                        url: str, aliases: list, chunk_type: str,
                        parent_topic: str) -> list:
    """Split content by paragraphs when other methods fail."""
    chunks = []
    
    paragraphs = re.split(r'\n\n+', content)
    
    current_chunk = ""
    part_num = 1
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        potential = current_chunk + "\n\n" + para if current_chunk else para
        
        if estimate_tokens(potential) > MAX_TOKENS and current_chunk:
            chunks.append(create_chunk(
                entry_id=f"{base_id}-part{part_num}",
                topic=f"{base_topic} (Part {part_num})",
                content=current_chunk.strip(),
                url=url,
                aliases=aliases,
                chunk_type=chunk_type,
                parent_topic=parent_topic,
                original_heading=base_topic
            ))
            part_num += 1
            current_chunk = para
        else:
            current_chunk = potential
    
    if current_chunk.strip():
        chunks.append(create_chunk(
            entry_id=f"{base_id}-part{part_num}",
            topic=f"{base_topic} (Part {part_num})",
            content=current_chunk.strip(),
            url=url,
            aliases=aliases,
            chunk_type=chunk_type,
            parent_topic=parent_topic,
            original_heading=base_topic
        ))
    
    return chunks


def split_by_qa(content: str, base_id: str, base_topic: str,
                url: str, aliases: list, chunk_type: str,
                parent_topic: str) -> list:
    """Split Q&A content by questions."""
    chunks = []
    
    # Split by Q: markers
    qa_parts = re.split(r'\n(?=# \d+\.\s*Q:|\n\d+\.\s*Q:)', content)
    
    current_chunk = ""
    part_num = 1
    
    for part in qa_parts:
        part = part.strip()
        if not part:
            continue
        
        # Extract question number if present
        q_match = re.match(r'#?\s*(\d+)\.\s*Q:', part)
        q_num = q_match.group(1) if q_match else str(part_num)
        
        if estimate_tokens(part) > MAX_TOKENS:
            # Q&A is too long, just truncate
            chunks.append(create_chunk(
                entry_id=f"{base_id}-Q{q_num}",
                topic=f"{base_topic} - Question {q_num}",
                content=part[:MAX_TOKENS * 4],
                url=url,
                aliases=aliases,
                chunk_type=chunk_type,
                parent_topic=parent_topic,
                original_heading=f"Question {q_num}"
            ))
        else:
            # Group small Q&As together
            potential = current_chunk + "\n\n" + part if current_chunk else part
            if estimate_tokens(potential) > MAX_TOKENS and current_chunk:
                chunks.append(create_chunk(
                    entry_id=f"{base_id}-part{part_num}",
                    topic=f"{base_topic} (Part {part_num})",
                    content=current_chunk.strip(),
                    url=url,
                    aliases=aliases,
                    chunk_type=chunk_type,
                    parent_topic=parent_topic,
                    original_heading=base_topic
                ))
                part_num += 1
                current_chunk = part
            else:
                current_chunk = potential
    
    if current_chunk.strip():
        chunks.append(create_chunk(
            entry_id=f"{base_id}-part{part_num}",
            topic=f"{base_topic} (Part {part_num})",
            content=current_chunk.strip(),
            url=url,
            aliases=aliases,
            chunk_type=chunk_type,
            parent_topic=parent_topic,
            original_heading=base_topic
        ))
    
    return chunks


def split_references(content: str, base_id: str, base_topic: str,
                     url: str, aliases: list, chunk_type: str,
                     parent_topic: str) -> list:
    """Split reference lists into smaller groups."""
    chunks = []
    
    # Split by individual references (lines starting with -)
    lines = content.split('\n')
    
    current_chunk = ""
    part_num = 1
    
    for line in lines:
        potential = current_chunk + "\n" + line if current_chunk else line
        
        if estimate_tokens(potential) > MAX_TOKENS and current_chunk:
            chunks.append(create_chunk(
                entry_id=f"{base_id}-refs{part_num}",
                topic=f"{base_topic} (Group {part_num})",
                content=current_chunk.strip(),
                url=url,
                aliases=aliases,
                chunk_type=chunk_type,
                parent_topic=parent_topic,
                original_heading="References and Legal Citations"
            ))
            part_num += 1
            current_chunk = line
        else:
            current_chunk = potential
    
    if current_chunk.strip():
        chunks.append(create_chunk(
            entry_id=f"{base_id}-refs{part_num}",
            topic=f"{base_topic} (Group {part_num})",
            content=current_chunk.strip(),
            url=url,
            aliases=aliases,
            chunk_type=chunk_type,
            parent_topic=parent_topic,
            original_heading="References and Legal Citations"
        ))
    
    return chunks


def fix_malformed_chunk(chunk: dict) -> dict:
    """Fix a chunk that has the old/wrong schema."""
    entry_id = chunk.get("entry_id", "")
    
    # Check if chunk uses old schema (has source_url instead of url, or missing fields)
    if "source_url" in chunk and "url" not in chunk:
        # This chunk needs fixing
        old_url = chunk.get("source_url", "")
        new_url = old_url if old_url else get_default_url(entry_id)
        
        return {
            "source_id": chunk.get("source_id", SOURCE_ID),
            "entry_id": entry_id,
            "topic": chunk.get("topic", ""),
            "original_heading": chunk.get("original_heading", chunk.get("topic", "")),
            "type": chunk.get("type", ""),
            "url": new_url,
            "last_updated": chunk.get("last_updated", datetime.now().strftime("%Y-%m-%d")),
            "content": chunk.get("content", ""),
            "parent_topic": chunk.get("parent_topic", chunk.get("topic", "").split(" (")[0]),
            "aliases": chunk.get("aliases", [])
        }
    
    # Chunk is already in correct format
    return chunk


def main():
    print("\n" + "=" * 70)
    print("FIX ALL OVERSIZED CHUNKS (v2 - Correct Schema)")
    print("=" * 70)
    
    chunks = load_corpus()
    print(f"📖 Loaded {len(chunks)} chunks")
    
    # First pass: Fix malformed chunks (wrong schema)
    print("\n🔧 Phase 1: Fixing malformed chunk schemas...")
    fixed_count = 0
    for i, chunk in enumerate(chunks):
        if "source_url" in chunk and "url" not in chunk:
            chunks[i] = fix_malformed_chunk(chunk)
            fixed_count += 1
    print(f"   Fixed {fixed_count} chunks with wrong schema")
    
    # Second pass: Split oversized chunks
    print("\n🔧 Phase 2: Splitting oversized chunks...")
    new_chunks = []
    removed_ids = []
    
    for chunk in chunks:
        entry_id = chunk.get("entry_id", "")
        content = chunk.get("content", "")
        tokens = estimate_tokens(content)
        topic = chunk.get("topic", "")
        url = chunk.get("url", "") or chunk.get("source_url", "")
        aliases = chunk.get("aliases", [])
        chunk_type = chunk.get("type", "")
        parent_topic = chunk.get("parent_topic", topic.split(" (")[0])
        
        if tokens <= MAX_TOKENS:
            new_chunks.append(chunk)
            continue
        
        print(f"\n   Splitting {entry_id} ({tokens} tokens)...")
        removed_ids.append(entry_id)
        
        # Get proper URL
        if not url:
            url = get_default_url(entry_id)
        
        # Choose splitting strategy based on content type
        if "PTSD" in entry_id or "Stressor" in entry_id:
            splits = split_by_subsections(content, entry_id, topic, url, aliases, chunk_type, parent_topic)
        elif "BlueWater" in entry_id:
            splits = split_by_qa(content, entry_id, topic, url, aliases, chunk_type, parent_topic)
        elif "GEN-" in entry_id or "References" in topic:
            splits = split_references(content, entry_id, topic, url, aliases, chunk_type, parent_topic)
        elif "LayEvidence" in entry_id:
            splits = split_by_subsections(content, entry_id, topic, url, aliases, chunk_type, parent_topic)
        else:
            # Default: split by rules or paragraphs
            splits = split_by_rules(content, entry_id, topic, url, aliases, chunk_type, parent_topic)
        
        print(f"   Created {len(splits)} smaller chunks")
        for s in splits:
            s_tokens = estimate_tokens(s.get("content", ""))
            print(f"      - {s['entry_id']}: {s_tokens} tokens")
        
        new_chunks.extend(splits)
    
    print(f"\n📊 Results:")
    print(f"   Fixed schema: {fixed_count} chunks")
    print(f"   Split oversized: {len(removed_ids)} chunks")
    print(f"   Total chunks: {len(new_chunks)}")
    
    # Verify no oversized chunks remain
    print("\n🔍 Final verification...")
    still_oversized = []
    missing_url = []
    for chunk in new_chunks:
        tokens = estimate_tokens(chunk.get("content", ""))
        if tokens > 2000:
            still_oversized.append((chunk.get("entry_id"), tokens))
        if not chunk.get("url"):
            missing_url.append(chunk.get("entry_id"))
    
    if still_oversized:
        print(f"⚠️  {len(still_oversized)} chunks still over 2000 tokens:")
        for eid, tokens in still_oversized:
            print(f"   - {eid}: {tokens} tokens")
    else:
        print("✅ All chunks are within acceptable limits!")
    
    if missing_url:
        print(f"⚠️  {len(missing_url)} chunks missing URL field:")
        for eid in missing_url[:5]:
            print(f"   - {eid}")
    else:
        print("✅ All chunks have URL field!")
    
    save_corpus(new_chunks)
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
