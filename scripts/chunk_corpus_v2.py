#!/usr/bin/env python3
"""
Improved Corpus Chunking Script v2

This script processes markdown files in the corpus folder and chunks them
into semantically meaningful pieces for the RAG knowledge base.

Key improvements:
1. Strips navigation/header junk from scraped pages
2. Preserves FAQ sections as individual Q&A chunks
3. Preserves legal references with their topics
4. Creates smaller, more focused chunks
5. Adds keyword aliases for better retrieval
"""

import re
import json
from datetime import datetime
from pathlib import Path

# Configuration
CORPUS_DIR = Path(__file__).parent.parent / "veteran-ai-spark" / "corpus"
OUTPUT_FILE = CORPUS_DIR / "vbkb_restructured.json"
SOURCE_ID_PREFIX = "veteransbenefitskb_2025_12_07"

# Files to process with their metadata
FILES_TO_PROCESS = {
    "nexus_letter.md": {
        "topic": "Independent Medical Opinion (IMO) / Nexus Letter",
        "url": "https://www.veteransbenefitskb.com/imo",
        "aliases": ["nexus letter", "nexus", "IMO", "independent medical opinion", "medical nexus", "nexus opinion"],
        "type": "claims_evidence"
    },
    "aggravation.md": {
        "topic": "Service-Connection by Aggravation",
        "url": "https://www.veteransbenefitskb.com/agg",
        "aliases": ["aggravation", "aggravated condition", "pre-existing condition", "preexisting"],
        "type": "claims_evidence"
    },
    "bilateral.md": {
        "topic": "Bilateral Factor",
        "url": "https://www.veteransbenefitskb.com/vamath#bilateral",
        "aliases": ["bilateral factor", "bilateral", "VA math bilateral", "paired extremities"],
        "type": "rating_calculation"
    },
    "static.md": {
        "topic": "Static vs Dynamic Ratings",
        "url": "https://www.veteransbenefitskb.com/static-check",
        "aliases": ["static rating", "dynamic rating", "static condition", "permanent rating", "static_ind"],
        "type": "rating_info"
    },
    "appeal_nottice_of_disagreement": {
        "topic": "Filing an Appeal",
        "url": "https://www.veteransbenefitskb.com/appeals",
        "aliases": ["appeal", "NOD", "notice of disagreement", "HLR", "higher level review", "supplemental claim", "BVA", "board appeal"],
        "type": "appeals"
    },
    "appeals_remands": {
        "topic": "Board Remands",
        "url": "https://www.veteransbenefitskb.com/appeals",
        "aliases": ["remand", "BVA remand", "board remand", "stegall", "manlincon"],
        "type": "appeals"
    },
    "toxic_exposure": {
        "topic": "Toxic Exposure and Hazardous Materials",
        "url": "https://www.va.gov/disability/eligibility/hazardous-materials-exposure/",
        "aliases": ["toxic exposure", "hazardous materials", "burn pit", "radiation", "asbestos", "mustard gas", "project shad"],
        "type": "presumptive"
    },
    "gi_bill.md": {
        "topic": "GI Bill Education Benefits",
        "url": "https://www.veteransbenefitskb.com/gibill",
        "aliases": ["GI Bill", "chapter 33", "post-9/11", "post 9/11 gi bill", "montgomery gi bill", "chapter 30", "chapter 32", "VEAP", "MGIB", "education benefits"],
        "type": "education"
    },
    "champva.md": {
        "topic": "CHAMPVA Healthcare Program",
        "url": "https://www.veteransbenefitskb.com/champva",
        "aliases": ["CHAMPVA", "civilian health and medical program", "dependent healthcare", "spouse healthcare"],
        "type": "healthcare"
    },
    "1151.md": {
        "topic": "38 USC 1151 Claims (VA Negligence)",
        "url": "https://www.veteransbenefitskb.com/1151",
        "aliases": ["1151", "section 1151", "VA negligence", "tort", "federal tort claim", "malpractice"],
        "type": "claims_special"
    },
    "Agentorange.md": {
        "topic": "Agent Orange Exposure",
        "url": "https://www.veteransbenefitskb.com/agentorange",
        "aliases": ["agent orange", "herbicide", "Vietnam", "dioxin", "presumptive conditions"],
        "type": "presumptive"
    },
    "chapter31.md": {
        "topic": "Veterans Readiness and Employment (VR&E) Chapter 31",
        "url": "https://www.veteransbenefitskb.com/vre",
        "aliases": ["VR&E", "voc rehab", "vocational rehab", "chapter 31", "vocational rehabilitation", "employment services"],
        "type": "employment"
    },
    # New files added by user
    "lay_evidence.md": {
        "topic": "Lay Evidence and Testimony",
        "url": "https://www.knowva.ebenefits.va.gov/system/templates/selfservice/va_ssnew/help/customer/locale/en-US/portal/554400000001018/content/554400000014389/",
        "aliases": ["lay evidence", "lay statement", "buddy statement", "testimony", "witness statement", "personal statement"],
        "type": "claims_evidence"
    },
    "duty_to_assist.md": {
        "topic": "Duty to Assist (DTA)",
        "url": "https://www.veteransbenefitskb.com/dta",
        "aliases": ["duty to assist", "DTA", "VA duty", "duty to notify", "records request"],
        "type": "claims_process"
    },
    "pact_act.md": {
        "topic": "PACT Act",
        "url": "https://www.va.gov/resources/the-pact-act-and-your-va-benefits/",
        "aliases": ["PACT Act", "pact", "burn pit", "toxic exposure", "presumptive conditions", "heath robinson"],
        "type": "presumptive"
    },
    "camp_lejeune.md": {
        "topic": "Camp Lejeune Water Contamination",
        "url": "https://www.va.gov/disability/eligibility/hazardous-materials-exposure/camp-lejeune-water-contamination/",
        "aliases": ["camp lejeune", "lejeune", "water contamination", "MCAS new river", "contaminated water"],
        "type": "presumptive"
    },
    "yellow_ribbon.md": {
        "topic": "Yellow Ribbon Program",
        "url": "https://www.veteransbenefitskb.com/yellow",
        "aliases": ["yellow ribbon", "yellow ribbon program", "tuition assistance", "private school", "out of state tuition"],
        "type": "education"
    },
    "aid_attendance.md": {
        "topic": "Aid and Attendance (Pension)",
        "url": "https://www.veteransbenefitskb.com/pension-aa",
        "aliases": ["aid and attendance", "A&A", "pension aid", "nursing home", "daily activities assistance"],
        "type": "pension"
    },
    "Housebound_SMP.md": {
        "topic": "Housebound - Special Monthly Pension",
        "url": "https://www.veteransbenefitskb.com/pension-housebound",
        "aliases": ["housebound", "SMP", "special monthly pension", "housebound status", "homebound"],
        "type": "pension"
    },
    "buddy_letter.md": {
        "topic": "Buddy Letters and Statements",
        "url": "https://www.veteransbenefitskb.com/buddy",
        "aliases": ["buddy letter", "buddy statement", "lay statement", "witness statement", "21-10210", "supporting statement"],
        "type": "claims_evidence"
    },
    # New batch of files added Dec 7, 2025
    "Nehmer.md": {
        "topic": "Nehmer Class Members (38 CFR 3.816)",
        "url": "https://www.veteransbenefitskb.com/nehmer",
        "aliases": ["Nehmer", "Nehmer rule", "Nehmer class", "38 CFR 3.816", "agent orange effective date", "earlier effective date"],
        "type": "claims_special"
    },
    "P&T.md": {
        "topic": "Permanent and Total (P&T) Disability",
        "url": "https://www.veteransbenefitskb.com/pnt",
        "aliases": ["permanent and total", "P&T", "100% P&T", "TDIU P&T", "DEA eligibility", "static rating"],
        "type": "rating_info"
    },
    "blue_water.md": {
        "topic": "Blue Water Navy Vietnam Veterans Act",
        "url": "https://www.veteransbenefitskb.com/bluewater",
        "aliases": ["blue water navy", "blue water", "offshore Vietnam", "Public Law 116-23", "vietnam navy"],
        "type": "presumptive"
    },
    "burn_pits.md": {
        "topic": "Burn Pit Exposure",
        "url": "https://www.veteransbenefitskb.com/burnpits",
        "aliases": ["burn pit", "burn pits", "particulate matter", "PACT Act", "toxic exposure", "fine particulate matter"],
        "type": "presumptive"
    },
    "mental_rating.md": {
        "topic": "General Rating Formula for Mental Disorders",
        "url": "https://www.veteransbenefitskb.com/mental",
        "aliases": ["mental health rating", "PTSD rating", "depression rating", "anxiety rating", "mental disorder criteria", "occupational and social impairment"],
        "type": "rating_criteria"
    },
    "smc.md": {
        "topic": "Special Monthly Compensation (SMC)",
        "url": "https://www.veteransbenefitskb.com/smc",
        "aliases": ["SMC", "special monthly compensation", "SMC-K", "SMC-L", "SMC-S", "SMC-R", "aid and attendance", "loss of use"],
        "type": "compensation"
    },
    "statement_of_the_case.md": {
        "topic": "Statement of the Case (SOC)",
        "url": "https://www.veteransbenefitskb.com/appeals#soc",
        "aliases": ["SOC", "statement of the case", "VA Form 9", "VA Form 10182", "BVA appeal"],
        "type": "appeals"
    },
    "stressor_PTSD.md": {
        "topic": "PTSD Stressor Development and Verification",
        "url": "https://www.knowva.ebenefits.va.gov/system/templates/selfservice/va_ssnew/help/customer/locale/en-US/portal/554400000001018/content/554400000177468/",
        "aliases": ["PTSD stressor", "stressor verification", "combat stressor", "MST", "military sexual trauma", "personal assault", "in-service stressor"],
        "type": "claims_process"
    },
    "va_math.md": {
        "topic": "VA Math - Combined Ratings Calculation",
        "url": "https://www.veteransbenefitskb.com/vamath",
        "aliases": ["VA math", "combined ratings", "combined rating table", "total person concept", "bilateral factor", "disability math"],
        "type": "rating_calculation"
    },
    "money_backpay": {
        "topic": "VA Money Matters and Back Pay",
        "url": "https://www.veteransbenefitskb.com/money",
        "aliases": ["back pay", "backpay", "VA payment", "retro pay", "effective date pay", "VA disability pay"],
        "type": "compensation"
    },
    "outside_resorces.md": {
        "topic": "External VA Resources and Calculators",
        "url": "https://www.veteransbenefitskb.com/resources",
        "aliases": ["VA calculator", "disability calculator", "pay table", "SMC rates", "compensation rates"],
        "type": "resources"
    },
}

def strip_navigation_junk(content: str) -> str:
    """Remove navigation headers, menus, and other non-content elements."""
    lines = content.split('\n')
    
    # Find the start of actual content (usually starts with # **Title**)
    content_start = 0
    for i, line in enumerate(lines):
        # Look for the main title (# **Something**)
        if line.strip().startswith('# **') or line.strip().startswith('# '):
            # But skip if it's just a navigation link
            if 'Skip to Content' not in line and 'Open Menu' not in line:
                content_start = i
                break
        # Also look for ## headings as content start
        if line.strip().startswith('## ') and i > 30:  # After likely nav section
            content_start = i
            break
    
    # Filter out navigation-style lines
    filtered_lines = []
    skip_patterns = [
        r'^\[0\]',  # Cart links
        r'^\[Skip to Content\]',
        r'^Open MenuClose Menu',
        r'^\[Home\]',
        r'^\[Mission Statement\]',
        r'^\[About Us\]',
        r'^!\[.*\]\(https://images\.squarespace',  # Squarespace images
        r'^\[Featured Articles\]',
        r'^Featured$',
        r'^\[Categories\]',
        r'^\\> \[',  # Category links like "> [Death & Survivor Benefits]"
        r'^\[Return to top\]',
        r'^Article ID:',
        r'^You can view this article at:',
        r'^Article added to bookmarks',
        r'^Was this article useful\?',
        r'^\[Yes\].*\[No\]',
        r'^- ###### Attachments',
        r'^- ###### Related Articles',
        r'^\[View All\]',
        r'^Heading Level six',
    ]
    
    for i, line in enumerate(lines):
        if i < content_start:
            continue
            
        # Skip lines matching navigation patterns
        skip = False
        for pattern in skip_patterns:
            if re.match(pattern, line.strip()):
                skip = True
                break
        
        if not skip:
            filtered_lines.append(line)
    
    return '\n'.join(filtered_lines)


def extract_faq_chunks(content: str, base_topic: str, base_url: str) -> list:
    """Extract FAQ Q&A pairs as individual chunks."""
    chunks = []
    
    # Find FAQ section
    faq_match = re.search(r'## \*\*Frequently\*\* \*\*Asked Questions\*\*|## \*\*Frequently Asked Questions\*\*|## Frequently Asked Questions', content)
    if not faq_match:
        return chunks
    
    faq_start = faq_match.end()
    
    # Find end of FAQ (next ## section or end of content)
    next_section = re.search(r'\n## ', content[faq_start:])
    faq_end = faq_start + next_section.start() if next_section else len(content)
    
    faq_content = content[faq_start:faq_end]
    
    # Extract Q&A pairs (format: - #### Question\n\n\n\n\n- Answer)
    # Also handle: - #### Question\n\n- Answer
    qa_pattern = r'- #### (.+?)(?:\n)+(?:- )?(.+?)(?=\n- ####|\n## |\Z)'
    
    for match in re.finditer(qa_pattern, faq_content, re.DOTALL):
        question = match.group(1).strip()
        answer = match.group(2).strip()
        
        # Clean up the answer (remove leading dashes and extra whitespace)
        answer = re.sub(r'^- ', '', answer)
        answer = re.sub(r'\n\n+', '\n\n', answer)
        
        if question and answer and len(answer) > 20:
            chunks.append({
                "question": question,
                "answer": answer,
                "type": "faq"
            })
    
    return chunks


def extract_references(content: str) -> str:
    """Extract the References section."""
    ref_match = re.search(r'## \*\*References\*\*|## References', content)
    if not ref_match:
        return ""
    
    ref_start = ref_match.start()
    
    # Find end of references (next ## section or end)
    next_section = re.search(r'\n## ', content[ref_match.end():])
    ref_end = ref_match.end() + next_section.start() if next_section else len(content)
    
    return content[ref_start:ref_end].strip()


def chunk_by_headings(content: str, base_topic: str, base_url: str) -> list:
    """Chunk content by ## headings."""
    chunks = []
    
    # Remove FAQ and References sections for main chunking (we handle them separately)
    content_for_chunking = content
    
    # Remove FAQ section
    faq_match = re.search(r'## \*\*Frequently\*\* \*\*Asked Questions\*\*.*?(?=\n## |\Z)', content_for_chunking, re.DOTALL)
    if faq_match:
        content_for_chunking = content_for_chunking[:faq_match.start()] + content_for_chunking[faq_match.end():]
    
    # Remove References section
    ref_match = re.search(r'## \*\*References\*\*.*?(?=\n## |\Z)', content_for_chunking, re.DOTALL)
    if ref_match:
        content_for_chunking = content_for_chunking[:ref_match.start()] + content_for_chunking[ref_match.end():]
    
    # Remove See Also section
    see_also_match = re.search(r'## \*\*See Also\*\*.*?(?=\n## |\Z)', content_for_chunking, re.DOTALL)
    if see_also_match:
        content_for_chunking = content_for_chunking[:see_also_match.start()] + content_for_chunking[see_also_match.end():]
    
    # Split by ## headings
    sections = re.split(r'\n(?=## )', content_for_chunking)
    
    for section in sections:
        section = section.strip()
        if not section:
            continue
        
        # Extract heading
        heading_match = re.match(r'## \*\*(.+?)\*\*|## (.+)', section)
        if heading_match:
            heading = heading_match.group(1) or heading_match.group(2)
            heading = heading.strip()
        else:
            heading = base_topic
        
        # Skip very short sections
        if len(section) < 100:
            continue
        
        # Create URL anchor from heading
        anchor = re.sub(r'[^a-z0-9]+', '', heading.lower())
        
        chunks.append({
            "heading": heading,
            "content": section,
            "url_anchor": anchor,
            "type": "section"
        })
    
    return chunks


def process_file(filename: str, metadata: dict) -> list:
    """Process a single markdown file and return chunks."""
    filepath = CORPUS_DIR / filename
    
    if not filepath.exists():
        print(f"  Skipping {filename} - file not found")
        return []
    
    # Check if file is empty
    if filepath.stat().st_size == 0:
        print(f"  Skipping {filename} - file is empty")
        return []
    
    print(f"  Processing {filename}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip navigation junk
    clean_content = strip_navigation_junk(content)
    
    if len(clean_content) < 100:
        print(f"    Warning: Very little content after cleaning ({len(clean_content)} chars)")
        return []
    
    chunks = []
    base_topic = metadata["topic"]
    base_url = metadata["url"]
    aliases = metadata.get("aliases", [])
    doc_type = metadata.get("type", "general")
    
    # 1. Extract FAQ chunks
    faq_chunks = extract_faq_chunks(clean_content, base_topic, base_url)
    for i, faq in enumerate(faq_chunks):
        chunk_id = f"{base_topic.replace(' ', '').replace('/', '')}-FAQ-{i+1}"
        chunks.append({
            "source_id": SOURCE_ID_PREFIX,
            "entry_id": chunk_id,
            "topic": f"{base_topic} - FAQ",
            "original_heading": faq["question"],
            "type": "faq",
            "url": f"{base_url}#faq",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "content": f"**Question:** {faq['question']}\n\n**Answer:** {faq['answer']}",
            "parent_topic": base_topic,
            "aliases": aliases
        })
    
    print(f"    Found {len(faq_chunks)} FAQ entries")
    
    # 2. Extract References
    references = extract_references(clean_content)
    if references:
        chunk_id = f"{base_topic.replace(' ', '').replace('/', '')}-References"
        chunks.append({
            "source_id": SOURCE_ID_PREFIX,
            "entry_id": chunk_id,
            "topic": f"{base_topic} - Legal References",
            "original_heading": "References and Legal Citations",
            "type": "references",
            "url": f"{base_url}#references",
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "content": references,
            "parent_topic": base_topic,
            "aliases": aliases
        })
        print(f"    Found References section")
    
    # 3. Chunk main content by headings
    section_chunks = chunk_by_headings(clean_content, base_topic, base_url)
    for i, section in enumerate(section_chunks):
        chunk_id = f"{base_topic.replace(' ', '').replace('/', '')}-{i+1}"
        chunks.append({
            "source_id": SOURCE_ID_PREFIX,
            "entry_id": chunk_id,
            "topic": section["heading"] if section["heading"] != base_topic else base_topic,
            "original_heading": section["heading"],
            "type": doc_type,
            "url": f"{base_url}#{section['url_anchor']}" if section["url_anchor"] else base_url,
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "content": section["content"],
            "parent_topic": base_topic,
            "aliases": aliases if section["heading"] == base_topic else []
        })
    
    print(f"    Found {len(section_chunks)} content sections")
    print(f"    Total chunks: {len(chunks)}")
    
    return chunks


def main():
    """Main entry point."""
    print("=" * 60)
    print("Corpus Chunking Script v2")
    print("=" * 60)
    
    # Load existing corpus
    existing_chunks = []
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            existing_chunks = json.load(f)
        print(f"Loaded {len(existing_chunks)} existing chunks from corpus")
    
    # Track entry IDs to avoid duplicates
    existing_ids = {c.get("entry_id") for c in existing_chunks}
    
    # Process each file
    new_chunks = []
    for filename, metadata in FILES_TO_PROCESS.items():
        chunks = process_file(filename, metadata)
        
        # Add chunks that don't already exist
        for chunk in chunks:
            if chunk["entry_id"] not in existing_ids:
                new_chunks.append(chunk)
                existing_ids.add(chunk["entry_id"])
            else:
                # Update existing chunk
                for i, existing in enumerate(existing_chunks):
                    if existing.get("entry_id") == chunk["entry_id"]:
                        existing_chunks[i] = chunk
                        break
    
    # Merge and save
    all_chunks = existing_chunks + new_chunks
    
    # Update corpus version marker
    version_marker = {
        "entry_id": f"_corpus_version_{datetime.now().strftime('%Y-%m-%d')}-v8",
        "topic": "Corpus Version",
        "content": f"This is a cache invalidation marker. Version: {datetime.now().strftime('%Y-%m-%d')}-v8. Added new chunked content including Nehmer, P&T, Blue Water Navy, Burn Pits, Mental Rating, SMC, PTSD Stressor, VA Math, Money/Backpay, and External Resources.",
        "source_id": "system"
    }
    
    # Remove old version markers and add new one
    all_chunks = [c for c in all_chunks if not c.get("entry_id", "").startswith("_corpus_version")]
    all_chunks.insert(0, version_marker)
    
    # Save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  - Existing chunks: {len(existing_chunks)}")
    print(f"  - New chunks added: {len(new_chunks)}")
    print(f"  - Total chunks: {len(all_chunks)}")
    print(f"  - Output: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

