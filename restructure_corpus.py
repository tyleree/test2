#!/usr/bin/env python3
"""
Corpus Restructuring Script

Transforms the Veterans Benefits Knowledge Base document into a clean,
normalized, RAG-ready JSON format with proper chunking and metadata.
"""

import re
import json
from pathlib import Path
from typing import Optional
from datetime import datetime


def extract_url_from_heading(heading: str) -> Optional[str]:
    """Extract URL if present in heading."""
    url_match = re.search(r'\((https?://[^\)]+)\)', heading)
    return url_match.group(1) if url_match else None


def clean_content(content: str) -> str:
    """Clean up content by removing artifacts and normalizing formatting."""
    # Remove document header
    content = re.sub(r'^# Veterans Benefits Knowledge Base - Contextual Guide\s*', '', content)
    content = re.sub(r'\*This document has been processed.*?\*\s*', '', content, flags=re.DOTALL)
    content = re.sub(r'\*Total chunks:.*?\*\s*', '', content)
    
    # Fix encoding issues
    content = content.replace('Â§', '§')
    content = content.replace('â€™', "'")
    content = content.replace('â€"', "–")
    content = content.replace('â€œ', '"')
    content = content.replace('â€', '"')
    content = content.replace('Â©', '©')
    content = content.replace('Â', '')
    
    # Remove HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # Remove "Return to top" links
    content = re.sub(r'\[Return to top\]\([^\)]+\)\s*', '', content)
    
    # Remove navigation sections (Skip to Content, Open Menu, etc.)
    content = re.sub(r'\[Skip to Content\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'Open Menu\s*', '', content)
    
    # Remove cart links
    content = re.sub(r'\[\d+\]\(https://www\.veteransbenefitskb\.com/cart\)\s*', '', content)
    
    # Remove horizontal rules (excessive ones)
    content = re.sub(r'(\* \* \*\s*){2,}', '---\n\n', content)
    content = re.sub(r'\* \* \*', '---', content)
    
    # Remove repeated navigation headers
    nav_pattern = r'\[Veterans Benefits Knowledge Base\]\([^\)]+\)\s*\[Home\]\([^\)]+\)\s*\[Mission Statement\]\([^\)]+\)\s*\[About Us\]\([^\)]+\)\s*'
    content = re.sub(nav_pattern, '', content)
    
    # Remove "Featured Articles" sidebar content
    content = re.sub(r'\[Featured Articles\]\([^\)]+\)\s*Featured\s*', '', content)
    content = re.sub(r'\[\\> Master Condition List\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\[\\> Federal Benefits.*?\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\[\\> Insider Insight.*?\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\[\\> Rating Schedule Index\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\[\\> Filing a VA Disability Claim\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\[\\> Filing an Appeal\]\([^\)]+\)\s*', '', content)
    
    # Remove Categories sidebar
    content = re.sub(r'\[Categories\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[Death/Survivor Benefits\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[Education.*?\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[Health care\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[Housing\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[Miscellaneous\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[VA Disability Compensation\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[VA\s*\]\([^\)]+\)\s*\[Pension\]\([^\)]+\)\s*', '', content)
    content = re.sub(r'\\?> \[VA Pension\]\([^\)]+\)\s*', '', content)
    
    # Remove copyright and footer
    content = re.sub(r'Â© \d{4}-\d{4}.*?all rights reserved\.?\s*', '', content)
    
    # Remove empty brackets and parentheses
    content = re.sub(r'\[\s*\]\s*', '', content)
    content = re.sub(r'\(\s*\)\s*', '', content)
    
    # Normalize multiple blank lines
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    
    # Clean up leading/trailing whitespace per line
    lines = content.split('\n')
    lines = [line.rstrip() for line in lines]
    content = '\n'.join(lines)
    
    # Remove leading/trailing horizontal rules (--- or * * *)
    content = re.sub(r'^[\s\n]*---+[\s\n]*', '', content)
    content = re.sub(r'[\s\n]*---+[\s\n]*$', '', content)
    content = re.sub(r'^[\s\n]*\* \* \*[\s\n]*', '', content)
    content = re.sub(r'[\s\n]*\* \* \*[\s\n]*$', '', content)
    
    # Remove duplicate heading markers at start (###, ##)
    content = re.sub(r'^(#{1,3}\s*\*?\*?)\s*\n', '', content)
    
    # Convert internal horizontal rules to proper format
    content = re.sub(r'\n\s*---+\s*\n', '\n\n---\n\n', content)
    
    # Strip overall content
    content = content.strip()
    
    return content


def determine_chunk_type(content: str, heading: str) -> str:
    """Determine the type of content chunk."""
    content_lower = content.lower()
    heading_lower = heading.lower()
    
    # Rating table detection
    if '| Rating |' in content or '| rating |' in content_lower:
        if 'rating' in heading_lower and 'schedule' in heading_lower:
            return 'policy'
        return 'rating_table'
    
    # Risk factors table
    if '| Risk Factors |' in content:
        return 'risk_factors_table'
    
    # References section
    if heading_lower.startswith('reference') or '38 CFR' in content or 'M21-1' in content:
        return 'references'
    
    # DBQ section
    if 'disability benefits questionnaire' in heading_lower or 'dbq' in heading_lower:
        return 'dbq_info'
    
    # Common secondaries/residuals
    if 'common secondary' in heading_lower or 'common residual' in heading_lower:
        return 'related_conditions'
    
    # Quasi secondaries
    if 'quasi secondary' in heading_lower:
        return 'related_conditions'
    
    # See Also sections
    if heading_lower.startswith('see also'):
        return 'related_links'
    
    # Navigation/index sections
    if 'rating schedule index navigation' in heading_lower:
        return 'navigation'
    
    # Affiliated partners, something broken, etc.
    if 'affiliated partner' in heading_lower or 'something broken' in heading_lower:
        return 'meta'
    
    # Having trouble finding
    if 'having trouble finding' in heading_lower:
        return 'navigation'
    
    # For Example sections
    if heading_lower.startswith('for example'):
        return 'example'
    
    # Notes sections
    if 'important note' in content_lower or 'pyramiding note' in content_lower:
        if '| Rating |' not in content:
            return 'notes'
    
    # Definition/main condition entry
    if re.match(r'^\d{4}', heading) or re.match(r'^\d{4}[a-z]?', heading):
        return 'condition_definition'
    
    # Introductory content
    if 'rating schedule for' in heading_lower or heading_lower.startswith('conditions that'):
        return 'section_intro'
    
    # Intestines, liver, etc. (anatomical sections)
    if heading_lower.startswith('the ') and len(heading_lower) < 50:
        return 'anatomical_section'
    
    return 'policy'


def extract_diagnostic_code(heading: str) -> Optional[str]:
    """Extract diagnostic code from heading (e.g., 7101, 9900)."""
    # Handle compound codes like "5003, 5010" - take first one
    match = re.match(r'^(\d{4})[,\s]+\d{4}', heading)
    if match:
        return match.group(1)
    # Handle patterns like "5002/5004-5009" - take first one
    match = re.match(r'^(\d{4})/\d{4}', heading)
    if match:
        return match.group(1)
    # Handle patterns like "9901/9902"
    match = re.match(r'^(\d{4}/\d{4})', heading)
    if match:
        return match.group(1).split('/')[0]  # Return first code
    # Handle range patterns like "5013-5024"
    match = re.match(r'^(\d{4})-\d{4}', heading)
    if match:
        return match.group(1)
    # Simple code like 7101 or 7101a
    match = re.match(r'^(\d{4}[a-z]?)', heading)
    if match:
        return match.group(1)
    return None


def extract_condition_name(heading: str) -> str:
    """Extract the main condition name from heading."""
    # Remove all diagnostic code prefixes
    # Handles: "5003, 5010", "5002/5004-5009", "9901/9902", "5013-5024", simple "7101"
    name = heading
    
    # Remove leading patterns like "5003, 5010 " or "5002/5004-5009 "
    # This regex removes all digit codes at the start, including comma-separated or slash-separated
    name = re.sub(r'^[\d,/\-\s]+(?=\D)', '', name)
    
    # If the above didn't work (heading is just codes), try simpler patterns
    if name == heading:
        name = re.sub(r'^\d{4}[a-z]?\s*', '', heading)
    
    # Fix encoding issues
    name = name.replace('â€™', "'")
    name = name.replace('â€"', "–")
    
    # Remove leading punctuation/slashes/spaces
    name = re.sub(r'^[,/\-\s]+', '', name)
    
    # Clean up parenthetical aliases - keep just the main name
    if '(' in name:
        main_part = name.split('(')[0].strip()
        if main_part:
            return main_part
    
    return name.strip()


def extract_subtopic(heading: str, parent_heading: str) -> Optional[str]:
    """Determine subtopic based on heading context."""
    heading_lower = heading.lower()
    
    if 'common secondary' in heading_lower:
        return 'Common Secondary Conditions'
    elif 'common residual' in heading_lower:
        return 'Common Residuals'
    elif 'quasi secondary' in heading_lower:
        return 'Quasi Secondary Presumptives'
    elif 'other common' in heading_lower:
        return 'Other Common Secondaries'
    elif 'reference' in heading_lower:
        return 'References'
    elif 'dbq' in heading_lower or 'disability benefits questionnaire' in heading_lower:
        return 'DBQs'
    elif 'see also' in heading_lower:
        return 'See Also'
    elif 'for example' in heading_lower:
        return 'Example'
    
    return None


def parse_chunk_comment(comment: str) -> dict:
    """Parse the HTML chunk comment to extract metadata."""
    # Pattern: <!-- Chunk 1/1206 | Heading: 7101 High Blood Pressure... | Words: 255 -->
    pattern = r'Chunk\s+(\d+)/(\d+)\s*\|\s*Heading:\s*(.+?)\s*\|\s*Words:\s*(\d+)'
    match = re.search(pattern, comment)
    
    if match:
        return {
            'chunk_num': int(match.group(1)),
            'total_chunks': int(match.group(2)),
            'heading': match.group(3).strip(),
            'word_count': int(match.group(4))
        }
    return {}


def infer_base_url(heading: str) -> str:
    """Infer the base URL for the content based on heading/topic."""
    heading_lower = heading.lower()
    
    url_mapping = {
        'blood pressure': 'https://veteransbenefitskb.com/bloodtubes',
        'hypertension': 'https://veteransbenefitskb.com/bloodtubes',
        'aneurysm': 'https://veteransbenefitskb.com/bloodtubes',
        'peripheral': 'https://veteransbenefitskb.com/bloodtubes',
        'buerger': 'https://veteransbenefitskb.com/bloodtubes',
        'raynaud': 'https://veteransbenefitskb.com/bloodtubes',
        'erythromelalgia': 'https://veteransbenefitskb.com/bloodtubes',
        'varicose': 'https://veteransbenefitskb.com/bloodtubes',
        'circulatory': 'https://veteransbenefitskb.com/bloodtubes',
        'allergic swelling': 'https://veteransbenefitskb.com/bloodtubes',
        'frostbite': 'https://veteransbenefitskb.com/bloodtubes',
        'cold injury': 'https://veteransbenefitskb.com/bloodtubes',
        'arteriovenous': 'https://veteransbenefitskb.com/bloodtubes',
        'sarcoma': 'https://veteransbenefitskb.com/bloodtubes',
        'dental': 'https://veteransbenefitskb.com/mouthsystem',
        'oral': 'https://veteransbenefitskb.com/mouthsystem',
        'jaw': 'https://veteransbenefitskb.com/mouthsystem',
        'mandible': 'https://veteransbenefitskb.com/mouthsystem',
        'maxilla': 'https://veteransbenefitskb.com/mouthsystem',
        'teeth': 'https://veteransbenefitskb.com/mouthsystem',
        'digestive': 'https://veteransbenefitskb.com/digsystem',
        'liver': 'https://veteransbenefitskb.com/digsystem',
        'hepatitis': 'https://veteransbenefitskb.com/digsystem',
        'intestin': 'https://veteransbenefitskb.com/digsystem',
        'bowel': 'https://veteransbenefitskb.com/digsystem',
        'colon': 'https://veteransbenefitskb.com/digsystem',
        'crohn': 'https://veteransbenefitskb.com/digsystem',
        'stomach': 'https://veteransbenefitskb.com/digsystem',
        'gastric': 'https://veteransbenefitskb.com/digsystem',
        'esophag': 'https://veteransbenefitskb.com/digsystem',
        'hernia': 'https://veteransbenefitskb.com/digsystem',
        'hemorrhoid': 'https://veteransbenefitskb.com/digsystem',
        'infectious': 'https://veteransbenefitskb.com/infect',
        'cholera': 'https://veteransbenefitskb.com/infect',
        'malaria': 'https://veteransbenefitskb.com/infect',
        'leprosy': 'https://veteransbenefitskb.com/infect',
        'typhus': 'https://veteransbenefitskb.com/infect',
        'fever': 'https://veteransbenefitskb.com/infect',
        'plague': 'https://veteransbenefitskb.com/infect',
        'syphilis': 'https://veteransbenefitskb.com/infect',
        'tuberculosis': 'https://veteransbenefitskb.com/infect',
        'hiv': 'https://veteransbenefitskb.com/infect',
        'immune': 'https://veteransbenefitskb.com/infect',
        'mental': 'https://veteransbenefitskb.com/mental',
        'ptsd': 'https://veteransbenefitskb.com/mental',
        'anxiety': 'https://veteransbenefitskb.com/mental',
        'depression': 'https://veteransbenefitskb.com/mental',
        'respiratory': 'https://veteransbenefitskb.com/airsystem',
        'lung': 'https://veteransbenefitskb.com/airsystem',
        'asthma': 'https://veteransbenefitskb.com/airsystem',
        'copd': 'https://veteransbenefitskb.com/airsystem',
        'heart': 'https://veteransbenefitskb.com/heart',
        'cardiac': 'https://veteransbenefitskb.com/heart',
        'cardiovascular': 'https://veteransbenefitskb.com/heart',
        'skin': 'https://veteransbenefitskb.com/skin',
        'dermat': 'https://veteransbenefitskb.com/skin',
        'scar': 'https://veteransbenefitskb.com/skin',
        'eye': 'https://veteransbenefitskb.com/eyes',
        'vision': 'https://veteransbenefitskb.com/eyes',
        'visual': 'https://veteransbenefitskb.com/eyes',
        'ear': 'https://veteransbenefitskb.com/ears',
        'hearing': 'https://veteransbenefitskb.com/ears',
        'tinnitus': 'https://veteransbenefitskb.com/ears',
        'kidney': 'https://veteransbenefitskb.com/gensystem',
        'bladder': 'https://veteransbenefitskb.com/gensystem',
        'urinary': 'https://veteransbenefitskb.com/gensystem',
        'genito': 'https://veteransbenefitskb.com/gensystem',
        'prostate': 'https://veteransbenefitskb.com/gensystem',
        'erectile': 'https://veteransbenefitskb.com/gensystem',
        'nerve': 'https://veteransbenefitskb.com/nervesystem',
        'neuro': 'https://veteransbenefitskb.com/nervesystem',
        'brain': 'https://veteransbenefitskb.com/cns',
        'tbi': 'https://veteransbenefitskb.com/TBI',
        'endocrine': 'https://veteransbenefitskb.com/endsystem',
        'thyroid': 'https://veteransbenefitskb.com/endsystem',
        'diabetes': 'https://veteransbenefitskb.com/endsystem',
        'musculoskeletal': 'https://veteransbenefitskb.com/msindex',
        'spine': 'https://veteransbenefitskb.com/spine',
        'back': 'https://veteransbenefitskb.com/spine',
        'shoulder': 'https://veteransbenefitskb.com/shoulder',
        'knee': 'https://veteransbenefitskb.com/knee',
        'ankle': 'https://veteransbenefitskb.com/ankle',
        'hip': 'https://veteransbenefitskb.com/hip',
        'blood': 'https://veteransbenefitskb.com/blood',
        'anemia': 'https://veteransbenefitskb.com/blood',
        'female': 'https://veteransbenefitskb.com/femalesystem',
        'gynec': 'https://veteransbenefitskb.com/femalesystem',
        'will not rate': 'https://veteransbenefitskb.com/norate',
        'misconduct': 'https://veteransbenefitskb.com/norate',
        'personality disorder': 'https://veteransbenefitskb.com/norate',
        'congenital': 'https://veteransbenefitskb.com/norate',
        'substance abuse': 'https://veteransbenefitskb.com/norate',
        'lab finding': 'https://veteransbenefitskb.com/norate',
    }
    
    for keyword, url in url_mapping.items():
        if keyword in heading_lower:
            return url
    
    return 'https://veteransbenefitskb.com'


def restructure_corpus(input_path: str, output_path: str):
    """Main function to restructure the corpus document."""
    
    print(f"Reading input file: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by chunk markers
    chunk_pattern = r'(<!-- Chunk \d+/\d+ \| Heading:.*?\| Words: \d+ -->)'
    parts = re.split(chunk_pattern, content)
    
    chunks = []
    current_main_topic = None
    current_section = None
    source_id = f"veteransbenefitskb_{datetime.now().strftime('%Y_%m_%d')}"
    
    print(f"Found {len(parts)} parts to process...")
    
    i = 0
    chunk_count = 0
    
    while i < len(parts):
        part = parts[i]
        
        # Check if this is a chunk marker
        if re.match(r'<!-- Chunk \d+/\d+', part):
            chunk_meta = parse_chunk_comment(part)
            
            if chunk_meta:
                # Get the content before this chunk marker
                # The content is in the previous part
                if i > 0:
                    raw_content = parts[i-1]
                else:
                    raw_content = ""
                
                # Clean the content
                cleaned_content = clean_content(raw_content)
                
                # Skip empty or navigation-only chunks
                if not cleaned_content or len(cleaned_content) < 20:
                    i += 1
                    continue
                
                # Skip pure navigation/meta chunks
                heading = chunk_meta.get('heading', '')
                chunk_type = determine_chunk_type(cleaned_content, heading)
                
                if chunk_type in ['navigation', 'meta']:
                    i += 1
                    continue
                
                # Extract metadata
                diagnostic_code = extract_diagnostic_code(heading)
                topic = extract_condition_name(heading) if diagnostic_code else heading
                
                # Track main topics for hierarchical structure
                if diagnostic_code or heading.startswith('Rating Schedule') or 'Conditions that' in heading:
                    current_main_topic = heading
                    current_section = topic
                
                # Format entry_id
                if diagnostic_code:
                    entry_id = f"{diagnostic_code}-{chunk_count:03d}"
                else:
                    entry_id = f"GEN-{chunk_count:04d}"
                
                # Build chunk object
                chunk_obj = {
                    "source_id": source_id,
                    "entry_id": entry_id,
                    "topic": topic,
                    "type": chunk_type,
                    "original_heading": heading,
                    "url": infer_base_url(heading),
                    "last_updated": datetime.now().strftime('%Y-%m-%d'),
                }
                
                # Add diagnostic code if present
                if diagnostic_code:
                    chunk_obj["diagnostic_code"] = diagnostic_code
                
                # Add subtopic if applicable
                subtopic = extract_subtopic(heading, current_main_topic or '')
                if subtopic:
                    chunk_obj["subtopic"] = subtopic
                
                # Add parent topic for hierarchical chunks
                if current_main_topic and current_main_topic != heading:
                    chunk_obj["parent_topic"] = current_main_topic
                
                # Add content last
                chunk_obj["content"] = cleaned_content
                
                chunks.append(chunk_obj)
                chunk_count += 1
        
        i += 1
    
    # Post-process to add anchor URLs where possible
    for chunk in chunks:
        dc = chunk.get('diagnostic_code')
        if dc:
            base_url = chunk.get('url', '')
            if '#' not in base_url:
                chunk['url'] = f"{base_url}#{dc}"
    
    print(f"Generated {len(chunks)} clean chunks")
    
    # Write output
    print(f"Writing output to: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    
    print("Done!")
    return chunks


def main():
    input_file = Path(__file__).parent / "veteran-ai-spark" / "corpus" / "vbkb_CG.md"
    output_file = Path(__file__).parent / "veteran-ai-spark" / "corpus" / "vbkb_restructured.json"
    
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        return
    
    chunks = restructure_corpus(str(input_file), str(output_file))
    
    # Print summary statistics
    print("\n=== Summary ===")
    print(f"Total chunks: {len(chunks)}")
    
    # Count by type
    types = {}
    for chunk in chunks:
        t = chunk.get('type', 'unknown')
        types[t] = types.get(t, 0) + 1
    
    print("\nChunk types:")
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    
    # Show sample chunks
    print("\n=== Sample Chunks ===")
    for chunk in chunks[:3]:
        print(json.dumps(chunk, indent=2)[:500] + "...")
        print("-" * 50)


if __name__ == "__main__":
    main()

