#!/usr/bin/env python3
"""
Add aliases to corpus entries for better semantic matching.

This script adds aliases to specific entries in vbkb_restructured.json
to improve retrieval for common alternative names and abbreviations.
"""

import json
from pathlib import Path

CORPUS_PATH = Path("veteran-ai-spark/corpus/vbkb_restructured.json")

# Aliases to add based on entry_id prefixes and topics
ALIAS_RULES = {
    # GI Bill entries
    "GIBILL": {
        "keywords": ["GI Bill", "GI Bills"],
        "aliases": ["GI Bill", "gi bill", "education benefits", "tuition assistance", "college benefits"]
    },
    # Chapter 33 / Post-9/11 specific
    "Chapter 33": {
        "keywords": ["Chapter 33", "Post-9/11"],
        "aliases": ["chapter 33", "chapter33", "post 9/11", "post-9/11", "post 911", "post-911 gi bill", "post 9/11 gi bill"]
    },
    # Montgomery GI Bill
    "Chapter 30": {
        "keywords": ["Chapter 30", "Montgomery GI Bill", "MGIB"],
        "aliases": ["chapter 30", "montgomery gi bill", "mgib", "mgib-ad"]
    },
    # Chapter 31 / VR&E
    "Chapter 31": {
        "keywords": ["Chapter 31", "VR&E", "Veterans Readiness"],
        "aliases": ["chapter 31", "voc rehab", "vocational rehab", "vocational rehabilitation", "vre", "vr&e"]
    },
    # CHAMPVA
    "CHAMPVA": {
        "keywords": ["CHAMPVA"],
        "aliases": ["champva", "civilian health", "dependent healthcare", "spouse healthcare"]
    },
    # 1151 Claims
    "1151": {
        "keywords": ["1151"],
        "aliases": ["1151 claim", "1151", "federal tort", "tort claim", "va malpractice", "medical malpractice"]
    },
    # Agent Orange
    "Agent Orange": {
        "keywords": ["Agent Orange", "Nehmer"],
        "aliases": ["agent orange", "ao", "herbicide exposure", "vietnam veteran", "dioxin"]
    },
}

def add_aliases_to_corpus():
    """Add aliases to corpus entries based on rules."""
    
    # Load corpus
    with open(CORPUS_PATH, 'r') as f:
        corpus = json.load(f)
    
    print(f"Loaded {len(corpus)} entries from corpus")
    
    modified_count = 0
    
    for entry in corpus:
        entry_id = entry.get("entry_id", "")
        topic = entry.get("topic", "")
        content = entry.get("content", "")
        
        # Check each alias rule
        for rule_name, rule_config in ALIAS_RULES.items():
            keywords = rule_config["keywords"]
            aliases = rule_config["aliases"]
            
            # Check if entry matches any keyword
            matched = False
            for keyword in keywords:
                if keyword.lower() in entry_id.lower() or keyword.lower() in topic.lower():
                    matched = True
                    break
            
            if matched:
                # Add or extend aliases
                existing_aliases = entry.get("aliases", [])
                new_aliases = list(set(existing_aliases + aliases))
                
                if new_aliases != existing_aliases:
                    entry["aliases"] = new_aliases
                    modified_count += 1
                    print(f"  Added aliases to {entry_id}: {new_aliases}")
    
    # Save updated corpus
    with open(CORPUS_PATH, 'w') as f:
        json.dump(corpus, f, indent=2)
    
    print(f"\nModified {modified_count} entries")
    print(f"Saved updated corpus to {CORPUS_PATH}")

if __name__ == "__main__":
    add_aliases_to_corpus()

