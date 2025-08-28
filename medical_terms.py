"""
Medical terminology mappings for VA disability rating queries.
Maps common medical terms to VA rating schedule terminology.
"""

# Comprehensive medical term expansions for VA disability ratings
MEDICAL_TERM_EXPANSIONS = {
    # Nerve conditions
    'neuropathy': 'neuropathy neuritis nerve paralysis',
    'ulnar neuropathy': 'ulnar neuropathy ulnar neuritis ulnar nerve paralysis ulnar nerve',
    'median neuropathy': 'median neuropathy median neuritis median nerve paralysis median nerve',
    'radial neuropathy': 'radial neuropathy radial neuritis radial nerve paralysis radial nerve',
    'sciatic neuropathy': 'sciatic neuropathy sciatic neuritis sciatic nerve paralysis sciatic nerve',
    'peroneal neuropathy': 'peroneal neuropathy peroneal neuritis peroneal nerve paralysis peroneal nerve',
    'carpal tunnel': 'carpal tunnel median nerve neuropathy median neuritis',
    'sciatica': 'sciatica sciatic nerve neuropathy sciatic neuritis',
    'radiculopathy': 'radiculopathy nerve root neuropathy neuritis',
    'peripheral neuropathy': 'peripheral neuropathy neuritis nerve paralysis',
    'diabetic neuropathy': 'diabetic neuropathy diabetic neuritis peripheral neuropathy',
    
    # Mental health conditions
    'ptsd': 'ptsd post traumatic stress disorder mental health anxiety depression',
    'depression': 'depression mental health mood disorder ptsd anxiety',
    'anxiety': 'anxiety mental health panic disorder ptsd depression',
    'bipolar': 'bipolar mental health mood disorder manic depression',
    'schizophrenia': 'schizophrenia mental health psychotic disorder',
    
    # Brain and neurological
    'tbi': 'tbi traumatic brain injury head injury concussion',
    'concussion': 'concussion traumatic brain injury tbi head injury',
    'headaches': 'headaches migraine head pain cephalgia',
    'migraines': 'migraines headaches head pain cephalgia',
    'seizures': 'seizures epilepsy convulsions',
    'epilepsy': 'epilepsy seizures convulsions',
    
    # Hearing and vision
    'hearing loss': 'hearing loss tinnitus auditory impairment deafness',
    'tinnitus': 'tinnitus hearing loss auditory impairment',
    'vision loss': 'vision loss blindness visual impairment eye',
    'blindness': 'blindness vision loss visual impairment eye',
    
    # Musculoskeletal - Spine
    'back pain': 'back pain spine lumbar cervical thoracic disc vertebrae',
    'lower back pain': 'lower back pain lumbar spine disc vertebrae',
    'neck pain': 'neck pain cervical spine vertebrae',
    'disc herniation': 'disc herniation herniated disc spine vertebrae',
    'spinal stenosis': 'spinal stenosis spine vertebrae narrowing',
    'scoliosis': 'scoliosis spine curvature vertebrae',
    
    # Joints and extremities
    'knee pain': 'knee pain patella meniscus ligament joint arthritis',
    'shoulder pain': 'shoulder pain rotator cuff joint impingement arthritis',
    'hip pain': 'hip pain joint arthritis',
    'ankle pain': 'ankle pain joint arthritis',
    'wrist pain': 'wrist pain joint arthritis carpal',
    'elbow pain': 'elbow pain joint arthritis',
    'arthritis': 'arthritis joint pain degenerative',
    'osteoarthritis': 'osteoarthritis arthritis joint degenerative',
    'rheumatoid arthritis': 'rheumatoid arthritis arthritis joint inflammatory',
    
    # Respiratory
    'asthma': 'asthma respiratory breathing lung',
    'copd': 'copd chronic obstructive pulmonary disease lung respiratory',
    'sleep apnea': 'sleep apnea obstructive sleep apnea central sleep apnea respiratory',
    'lung disease': 'lung disease respiratory pulmonary',
    
    # Cardiovascular
    'heart disease': 'heart disease cardiac cardiovascular coronary',
    'hypertension': 'hypertension high blood pressure cardiovascular',
    'high blood pressure': 'high blood pressure hypertension cardiovascular',
    'heart attack': 'heart attack myocardial infarction cardiac',
    'stroke': 'stroke cerebrovascular accident brain',
    
    # Gastrointestinal
    'ibs': 'ibs irritable bowel syndrome gastrointestinal digestive',
    'crohns': 'crohns disease inflammatory bowel disease gastrointestinal',
    'ulcerative colitis': 'ulcerative colitis inflammatory bowel disease gastrointestinal',
    'gerd': 'gerd gastroesophageal reflux disease acid reflux digestive',
    
    # Skin conditions
    'eczema': 'eczema dermatitis skin',
    'psoriasis': 'psoriasis skin dermatitis',
    'rash': 'rash skin dermatitis',
    'acne': 'acne skin dermatitis',
    
    # Endocrine
    'diabetes': 'diabetes mellitus endocrine blood sugar',
    'thyroid': 'thyroid endocrine hyperthyroid hypothyroid',
    
    # Genitourinary
    'kidney disease': 'kidney disease renal genitourinary',
    'prostate': 'prostate genitourinary urinary',
    
    # Pain and symptoms
    'chronic pain': 'chronic pain fibromyalgia',
    'fibromyalgia': 'fibromyalgia chronic pain widespread pain',
    'fatigue': 'fatigue chronic fatigue syndrome',
    
    # Service-connected terms
    'agent orange': 'agent orange herbicide exposure presumptive',
    'burn pit': 'burn pit exposure presumptive',
    'gulf war': 'gulf war syndrome presumptive',
    'radiation': 'radiation exposure presumptive',
    
    # Common abbreviations
    'va': 'veterans affairs department veterans benefits',
    'dav': 'disabled american veterans',
    'vfw': 'veterans foreign wars',
    'vso': 'veterans service organization',
}

def expand_medical_query(query: str) -> str:
    """
    Expand a query with medical terminology for better VA rating schedule matching.
    
    Args:
        query: Original query string
        
    Returns:
        Expanded query string with medical synonyms and VA terminology
    """
    query_lower = query.lower()
    
    # Check for exact matches first (longer terms first to avoid partial replacements)
    sorted_terms = sorted(MEDICAL_TERM_EXPANSIONS.items(), key=lambda x: len(x[0]), reverse=True)
    
    for term, expansion in sorted_terms:
        if term in query_lower:
            # Replace the term with expanded version
            expanded_query = query_lower.replace(term, expansion)
            return expanded_query
    
    return query

def get_related_terms(medical_term: str) -> list:
    """
    Get related terms for a specific medical condition.
    
    Args:
        medical_term: Medical term to find related terms for
        
    Returns:
        List of related terms
    """
    medical_term_lower = medical_term.lower()
    
    if medical_term_lower in MEDICAL_TERM_EXPANSIONS:
        return MEDICAL_TERM_EXPANSIONS[medical_term_lower].split()
    
    # Check if term appears in any expansion
    related = []
    for term, expansion in MEDICAL_TERM_EXPANSIONS.items():
        if medical_term_lower in expansion.lower():
            related.extend(expansion.split())
    
    return list(set(related))  # Remove duplicates
