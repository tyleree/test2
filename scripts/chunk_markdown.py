#!/usr/bin/env python3
"""
Chunk markdown files and add them to the restructured corpus JSON.

This script processes markdown files from the corpus directory and creates
properly formatted JSON chunks that match the existing vbkb_restructured.json format.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# File configurations with metadata
FILE_CONFIGS = {
    "gi_bill.md": {
        "base_url": "https://www.veteransbenefitskb.com/gibills",
        "primary_topic": "GI Bills",
        "aliases": ["chapter 33", "post 9/11", "post-9/11", "post 9/11 gi bill", "montgomery gi bill", "chapter 30", "chapter 32", "VEAP", "MGIB"],
        "entry_prefix": "GIBILL",
    },
    "champva.md": {
        "base_url": "https://www.veteransbenefitskb.com/champva",
        "primary_topic": "CHAMPVA",
        "aliases": ["civilian health and medical program", "champva insurance", "va family health"],
        "entry_prefix": "CHAMPVA",
    },
    "1151.md": {
        "base_url": "https://www.veteransbenefitskb.com/1151",
        "primary_topic": "1151 Claim",
        "aliases": ["federal tort claim", "tort claim", "va malpractice", "1151", "medical malpractice va"],
        "entry_prefix": "1151",
    },
    "Agentorange.md": {
        "base_url": "https://www.veteransbenefitskb.com/agentorange",
        "primary_topic": "Agent Orange",
        "aliases": ["AO", "herbicide exposure", "vietnam veteran presumptive", "nehmer"],
        "entry_prefix": "AO",
    },
    "chapter31.md": {
        "base_url": "https://www.veteransbenefitskb.com/vre",
        "primary_topic": "Veterans Readiness and Employment (VR&E)",
        "aliases": ["voc rehab", "vocational rehab", "vocational rehabilitation", "chapter 31", "VR&E", "VRE"],
        "entry_prefix": "VRE",
    },
}

def clean_markdown_content(content: str) -> str:
    """Clean up markdown content for better readability."""
    # Remove navigation/header boilerplate (lines 1-70 typically)
    lines = content.split('\n')
    
    # Find the main content start (after the navigation)
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('# **') or (line.startswith('# ') and not line.startswith('# [') and 'Skip to' not in line):
            start_idx = i
            break
    
    # Find the end (before footer)
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if '#### **Veterans Benefits Knowledge Base**' in line or '![](https://images.squarespace-cdn.com' in line and i > start_idx + 50:
            end_idx = i
            break
    
    # Keep only main content
    main_content = '\n'.join(lines[start_idx:end_idx])
    
    # Clean up excessive whitespace
    main_content = re.sub(r'\n{3,}', '\n\n', main_content)
    
    return main_content.strip()

def extract_sections(content: str) -> List[Dict[str, str]]:
    """Extract sections from markdown content based on headers."""
    sections = []
    
    # Split by ## headers (main sections)
    parts = re.split(r'\n(?=## \*\*)', content)
    
    for part in parts:
        if not part.strip():
            continue
            
        # Extract header
        header_match = re.match(r'^(#+)\s*\*?\*?([^*\n]+)\*?\*?', part)
        if header_match:
            level = len(header_match.group(1))
            header = header_match.group(2).strip()
        else:
            header = "General"
            level = 2
        
        sections.append({
            "header": header,
            "level": level,
            "content": part.strip()
        })
    
    return sections

def chunk_section(section: Dict[str, str], max_chunk_size: int = 2000) -> List[str]:
    """Split a section into smaller chunks if needed."""
    content = section["content"]
    
    if len(content) <= max_chunk_size:
        return [content]
    
    chunks = []
    
    # Try to split by ### subsections first
    subsections = re.split(r'\n(?=### )', content)
    
    current_chunk = ""
    for sub in subsections:
        if len(current_chunk) + len(sub) <= max_chunk_size:
            current_chunk += sub + "\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sub + "\n"
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # If still too big, split by paragraphs
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_chunk_size:
            final_chunks.append(chunk)
        else:
            # Split by double newlines (paragraphs)
            paragraphs = chunk.split('\n\n')
            current = ""
            for para in paragraphs:
                if len(current) + len(para) <= max_chunk_size:
                    current += para + "\n\n"
                else:
                    if current:
                        final_chunks.append(current.strip())
                    current = para + "\n\n"
            if current:
                final_chunks.append(current.strip())
    
    return final_chunks

def determine_chunk_type(content: str, header: str) -> str:
    """Determine the type of chunk based on content."""
    header_lower = header.lower()
    content_lower = content.lower()
    
    if "eligibility" in header_lower:
        return "eligibility"
    elif "benefits" in header_lower:
        return "benefits"
    elif "frequently asked" in header_lower or "faq" in header_lower:
        return "faq"
    elif "reference" in header_lower:
        return "references"
    elif "applying" in header_lower or "how to" in header_lower:
        return "process"
    elif "| " in content and "---" in content:
        return "rating_table"
    elif "presumptive" in header_lower:
        return "presumptive"
    else:
        return "policy"

def extract_anchor_from_header(header: str) -> str:
    """Create URL anchor from header text."""
    # Remove special chars, lowercase, replace spaces with nothing
    anchor = re.sub(r'[^a-zA-Z0-9\s]', '', header)
    anchor = anchor.lower().replace(' ', '')
    return anchor[:20] if anchor else ""

def process_markdown_file(filepath: Path, config: Dict[str, Any], start_id: int) -> List[Dict[str, Any]]:
    """Process a markdown file and return JSON chunks."""
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_content = f.read()
    
    content = clean_markdown_content(raw_content)
    sections = extract_sections(content)
    
    chunks = []
    chunk_id = start_id
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Add an overview chunk with aliases for better search
    alias_text = ""
    if config.get("aliases"):
        alias_text = f"\n\nAlso known as: {', '.join(config['aliases'])}"
    
    # First chunk is the main overview
    first_section = sections[0] if sections else {"header": config["primary_topic"], "content": content[:1500]}
    overview_content = first_section["content"] + alias_text
    
    chunks.append({
        "source_id": f"veteransbenefitskb_{today.replace('-', '_')}",
        "entry_id": f"{config['entry_prefix']}-{chunk_id:04d}",
        "topic": config["primary_topic"],
        "type": "overview",
        "original_heading": config["primary_topic"],
        "url": config["base_url"],
        "last_updated": today,
        "content": overview_content
    })
    chunk_id += 1
    
    # Process remaining sections
    for section in sections[1:]:
        header = section["header"]
        section_chunks = chunk_section(section)
        
        for i, chunk_content in enumerate(section_chunks):
            if not chunk_content.strip() or len(chunk_content) < 50:
                continue
            
            # Determine topic name
            if len(section_chunks) > 1:
                topic = f"{header} (Part {i+1})"
            else:
                topic = header
            
            # Build URL with anchor
            anchor = extract_anchor_from_header(header)
            url = f"{config['base_url']}#{anchor}" if anchor else config["base_url"]
            
            chunk_type = determine_chunk_type(chunk_content, header)
            
            chunks.append({
                "source_id": f"veteransbenefitskb_{today.replace('-', '_')}",
                "entry_id": f"{config['entry_prefix']}-{chunk_id:04d}",
                "topic": topic,
                "type": chunk_type,
                "original_heading": header,
                "url": url,
                "last_updated": today,
                "parent_topic": config["primary_topic"],
                "content": chunk_content
            })
            chunk_id += 1
    
    return chunks

def main():
    corpus_dir = Path("veteran-ai-spark/corpus")
    output_file = corpus_dir / "vbkb_restructured.json"
    
    # Load existing corpus
    print(f"Loading existing corpus from {output_file}...")
    with open(output_file, 'r', encoding='utf-8') as f:
        existing_corpus = json.load(f)
    
    print(f"Existing corpus has {len(existing_corpus)} chunks")
    
    # Find the highest existing ID to continue numbering
    max_id = 0
    for chunk in existing_corpus:
        entry_id = chunk.get("entry_id", "")
        # Extract numeric part if present
        match = re.search(r'-(\d+)$', entry_id)
        if match:
            max_id = max(max_id, int(match.group(1)))
    
    start_id = max_id + 1
    print(f"Starting new chunks at ID {start_id}")
    
    # Process each markdown file
    new_chunks = []
    for filename, config in FILE_CONFIGS.items():
        filepath = corpus_dir / filename
        if not filepath.exists():
            print(f"  Skipping {filename} - file not found")
            continue
        
        print(f"\nProcessing {filename}...")
        file_chunks = process_markdown_file(filepath, config, start_id)
        print(f"  Created {len(file_chunks)} chunks for {config['primary_topic']}")
        
        new_chunks.extend(file_chunks)
        start_id += len(file_chunks)
    
    # Combine and save
    combined_corpus = existing_corpus + new_chunks
    print(f"\nTotal chunks: {len(combined_corpus)} ({len(new_chunks)} new)")
    
    # Save backup first
    backup_file = corpus_dir / "vbkb_restructured_backup.json"
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(existing_corpus, f, indent=2, ensure_ascii=False)
    print(f"Backup saved to {backup_file}")
    
    # Save updated corpus
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(combined_corpus, f, indent=2, ensure_ascii=False)
    print(f"Updated corpus saved to {output_file}")
    
    # Print summary
    print("\n=== Summary ===")
    for filename, config in FILE_CONFIGS.items():
        count = len([c for c in new_chunks if c.get("entry_id", "").startswith(config["entry_prefix"])])
        print(f"  {config['primary_topic']}: {count} chunks")

if __name__ == "__main__":
    main()

