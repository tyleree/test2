"""
Topic Graph for Smart Cache Lookups with Enhanced Graph Architecture

Implements a multi-node knowledge graph for questions, enabling:
- Topic-based cache lookups (1 join)
- Entity-based cache lookups with diagnostic codes, forms, benefits (2 joins)
- Source-linked responses for hallucination prevention
- Verification flags for quality assurance

Graph Architecture (max 2 joins):
                    ┌─────────────┐
                    │   TOPICS    │ (broad categories)
                    └──────┬──────┘
                           │
      ┌────────────────────┼────────────────────┐
      │                    │                    │
┌─────▼─────┐       ┌──────▼──────┐      ┌──────▼──────┐
│ QUESTIONS │◄──────┤   SOURCES   │──────►│  ENTITIES   │
└───────────┘       │  (chunks)   │       │ (DC codes,  │
                    └─────────────┘       │  forms)     │
                                          └─────────────┘

Usage:
    graph = TopicGraph()
    topic_ids = graph.classify_question("What is my VA disability rating?")
    # -> [1]  (disability_ratings topic)
    
    entities = graph.extract_entities("What is DC 7101 rating for hypertension?")
    # -> [Entity(type='dc_code', value='7101', name='Hypertension')]
    
    cached = graph.find_similar_by_topic_and_entity(topic_ids, entities)
    # -> Returns cached Q&A pairs with matching topics AND entities
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class Topic:
    """A topic node in the graph."""
    id: int
    slug: str
    name: str
    keywords: List[str]


@dataclass
class Entity:
    """An extracted entity from a question or document.
    
    Types:
    - dc_code: VA Diagnostic Code (e.g., 7101, 5201)
    - va_form: VA Form number (e.g., 21-526EZ, 21-4138)
    - benefit: Specific benefit program (e.g., TDIU, Chapter 35)
    - condition: Medical condition (e.g., PTSD, hypertension)
    """
    type: str  # dc_code, va_form, benefit, condition
    value: str  # The extracted value (e.g., "7101", "21-526EZ")
    name: Optional[str] = None  # Human-readable name
    confidence: float = 1.0


@dataclass
class CacheEntry:
    """A cached question-answer pair with metadata."""
    id: int
    question: str
    answer: str
    topics: List[int] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)  # chunk IDs
    model_used: Optional[str] = None
    verified: bool = False
    created_at: Optional[str] = None


# Entity extraction patterns
ENTITY_PATTERNS = {
    # Diagnostic Codes: 4-digit numbers (e.g., 7101, 5201, 8520)
    'dc_code': [
        (r'\b(?:DC|diagnostic code)\s*[#]?\s*(\d{4})\b', 'DC {}'),
        (r'\b(\d{4})\s+(?:rating|disability)\b', 'DC {}'),
        (r'\bcode\s+(\d{4})\b', 'DC {}'),
    ],
    # VA Forms: Various formats (e.g., 21-526EZ, VA Form 21-0845)
    'va_form': [
        (r'\b(?:VA\s+)?(?:Form\s+)?(\d{2}-\d{3,4}[A-Z]*)\b', 'Form {}'),
        (r'\b(21-526EZ|21-4138|21-0845|21-0966|21-22|21-22a)\b', 'Form {}'),
    ],
    # Benefit Programs
    'benefit': [
        (r'\b(TDIU|IU|individual unemployability)\b', 'TDIU'),
        (r'\b(Chapter 35|DEA|Dependents Educational Assistance)\b', 'Chapter 35'),
        (r'\b(Chapter 31|VR&E|Vocational Rehab)\b', 'Chapter 31'),
        (r'\b(CHAMPVA)\b', 'CHAMPVA'),
        (r'\b(Aid and Attendance|A&A|housebound)\b', 'Aid & Attendance'),
        (r'\b(SMC|Special Monthly Compensation)\b', 'SMC'),
    ],
    # Common Conditions (for entity matching)
    'condition': [
        (r'\b(PTSD|post[- ]traumatic stress)\b', 'PTSD'),
        (r'\b(MST|military sexual trauma)\b', 'MST'),
        (r'\b(TBI|traumatic brain injury)\b', 'TBI'),
        (r'\b(sleep apnea)\b', 'Sleep Apnea'),
        (r'\b(tinnitus)\b', 'Tinnitus'),
        (r'\b(hypertension|high blood pressure)\b', 'Hypertension'),
    ],
}


class TopicGraph:
    """
    Enhanced topic-based graph for question classification and lookup.
    
    Features:
    - Topics: Broad categories (disability_ratings, healthcare, etc.)
    - Entities: Specific items (DC codes, forms, benefits)
    - Sources: Links to corpus chunks used in answers
    - Verification: Flags for quality assurance
    
    Designed for minimal database overhead:
    - Topics and entities loaded once at initialization
    - Classification done in-memory (no DB query)
    - Lookups use max 2 JOINs
    """
    
    def __init__(self):
        self._topics: List[Topic] = []
        self._entities: Dict[str, List[Entity]] = {}  # Cache extracted entities
        self._initialized = False
        self._db_available = False
    
    def _create_tables(self, session) -> None:
        """Create the topic graph tables and seed data."""
        from sqlalchemy import text
        
        # ============================================================
        # TOPICS TABLE (Nodes) - Broad categories
        # ============================================================
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS topics (
                id SERIAL PRIMARY KEY,
                slug VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                keywords TEXT[] NOT NULL DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_topics_slug ON topics(slug)"))
        
        # ============================================================
        # ENTITIES TABLE (Nodes) - Specific items (DC codes, forms)
        # ============================================================
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS entities (
                id SERIAL PRIMARY KEY,
                type VARCHAR(20) NOT NULL,  -- dc_code, va_form, benefit, condition
                value VARCHAR(50) NOT NULL,  -- The code/number (e.g., '7101')
                name VARCHAR(200),           -- Human-readable name
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(type, value)
            )
        """))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_entities_type_value ON entities(type, value)"))
        
        # ============================================================
        # QUESTION_TOPICS TABLE (Edges) - Question -> Topic
        # ============================================================
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS question_topics (
                question_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
                confidence FLOAT DEFAULT 1.0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                PRIMARY KEY (question_id, topic_id)
            )
        """))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_question_topics_topic ON question_topics(topic_id)"))
        
        # ============================================================
        # QUESTION_ENTITIES TABLE (Edges) - Question -> Entity
        # ============================================================
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS question_entities (
                question_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
                confidence FLOAT DEFAULT 1.0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                PRIMARY KEY (question_id, entity_id)
            )
        """))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_question_entities_entity ON question_entities(entity_id)"))
        
        # ============================================================
        # QUESTION_SOURCES TABLE (Edges) - Question -> Source chunks
        # ============================================================
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS question_sources (
                question_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
                source_id VARCHAR(100) NOT NULL,  -- chunk entry_id from corpus
                relevance_score FLOAT DEFAULT 1.0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                PRIMARY KEY (question_id, source_id)
            )
        """))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_question_sources_source ON question_sources(source_id)"))
        
        # ============================================================
        # VERIFICATION FLAGS - Add to events table if not exists
        # ============================================================
        # Check if verified column exists
        try:
            session.execute(text("""
                ALTER TABLE events ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT FALSE
            """))
            session.execute(text("""
                ALTER TABLE events ADD COLUMN IF NOT EXISTS flagged BOOLEAN DEFAULT FALSE
            """))
            session.execute(text("""
                ALTER TABLE events ADD COLUMN IF NOT EXISTS flag_reason VARCHAR(200)
            """))
        except Exception:
            pass  # Columns may already exist
        
        # ============================================================
        # SEED DATA - Topics for veterans benefits
        # ============================================================
        session.execute(text("""
            INSERT INTO topics (slug, name, keywords) VALUES
            ('disability_ratings', 'Disability Ratings', ARRAY['disability rating', 'va rating', 'service-connected', 'compensation', 'disability claim', 'rating decision', 'combined rating']),
            ('healthcare', 'Healthcare Benefits', ARRAY['healthcare', 'medical', 'va hospital', 'health care', 'doctor', 'treatment', 'prescription', 'mental health', 'ptsd']),
            ('education', 'Education Benefits', ARRAY['gi bill', 'education', 'college', 'tuition', 'school', 'vocational', 'training', 'vre', 'voc rehab']),
            ('home_loans', 'Home Loans', ARRAY['va loan', 'home loan', 'mortgage', 'housing', 'coe', 'certificate of eligibility', 'funding fee']),
            ('pension', 'Pension & Aid', ARRAY['pension', 'aid and attendance', 'housebound', 'survivors pension', 'death pension']),
            ('burial', 'Burial & Memorial', ARRAY['burial', 'cemetery', 'memorial', 'headstone', 'grave marker', 'funeral', 'interment']),
            ('dependents', 'Dependent Benefits', ARRAY['dependent', 'spouse', 'child', 'family', 'champva', 'dea', 'chapter 35']),
            ('appeals', 'Appeals & Claims', ARRAY['appeal', 'decision review', 'higher level', 'supplemental claim', 'board of veterans appeals', 'bva', 'denied claim'])
            ON CONFLICT (slug) DO NOTHING
        """))
        
        # Seed common entities (diagnostic codes)
        session.execute(text("""
            INSERT INTO entities (type, value, name) VALUES
            ('dc_code', '7101', 'Hypertension'),
            ('dc_code', '9411', 'PTSD'),
            ('dc_code', '6260', 'Tinnitus'),
            ('dc_code', '6847', 'Sleep Apnea'),
            ('dc_code', '5201', 'Arm Limitation of Motion'),
            ('dc_code', '8520', 'Sciatic Nerve Paralysis'),
            ('va_form', '21-526EZ', 'Application for Disability Compensation'),
            ('va_form', '21-4138', 'Statement in Support of Claim'),
            ('va_form', '21-0966', 'Intent to File'),
            ('benefit', 'TDIU', 'Total Disability Individual Unemployability'),
            ('benefit', 'SMC', 'Special Monthly Compensation'),
            ('benefit', 'Chapter 35', 'Dependents Educational Assistance')
            ON CONFLICT (type, value) DO NOTHING
        """))
        
        print("[TOPIC_GRAPH] Created tables with entities and sources, seeded data")
    
    def initialize(self) -> bool:
        """
        Initialize the topic graph from database.
        
        Returns True if successfully initialized, False otherwise.
        """
        if self._initialized:
            return self._db_available
        
        self._initialized = True
        
        # Check if database is available
        if not os.getenv("DATABASE_URL"):
            print("[TOPIC_GRAPH] No DATABASE_URL - topic graph disabled")
            return False
        
        try:
            from db import SessionLocal
            if not SessionLocal:
                print("[TOPIC_GRAPH] No SessionLocal - topic graph disabled")
                return False
            
            session = SessionLocal()
            try:
                from sqlalchemy import text
                
                # Check if topics table exists, create if not
                exists = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'topics'
                    )
                """)).scalar()
                
                if not exists:
                    print("[TOPIC_GRAPH] Topics table not found - creating...")
                    self._create_tables(session)
                    session.commit()
                
                # Load all topics into memory
                rows = session.execute(text("""
                    SELECT id, slug, name, keywords FROM topics ORDER BY id
                """)).mappings().all()
                
                for row in rows:
                    keywords = row['keywords'] or []
                    # PostgreSQL arrays come as lists already
                    if isinstance(keywords, str):
                        keywords = [k.strip() for k in keywords.strip('{}').split(',')]
                    
                    self._topics.append(Topic(
                        id=row['id'],
                        slug=row['slug'],
                        name=row['name'],
                        keywords=keywords
                    ))
                
                self._db_available = True
                print(f"[TOPIC_GRAPH] Loaded {len(self._topics)} topics")
                return True
                
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Initialization error: {e}")
            return False
    
    @property
    def topics(self) -> List[Topic]:
        """Get all loaded topics."""
        return self._topics
    
    def classify_question(self, question: str) -> List[int]:
        """
        Classify a question into topic(s) using keyword matching.
        
        This is fast (in-memory, O(topics * keywords)) and requires no DB query.
        
        Args:
            question: The user's question text
            
        Returns:
            List of topic IDs that match the question
        """
        if not self._topics:
            return []
        
        question_lower = question.lower()
        matched_ids = []
        
        for topic in self._topics:
            for keyword in topic.keywords:
                if keyword.lower() in question_lower:
                    matched_ids.append(topic.id)
                    break  # One keyword match is enough per topic
        
        return matched_ids
    
    def classify_question_with_scores(self, question: str) -> List[Tuple[int, float]]:
        """
        Classify a question with confidence scores.
        
        Returns list of (topic_id, score) tuples, sorted by score descending.
        Score is based on number of keyword matches.
        """
        if not self._topics:
            return []
        
        question_lower = question.lower()
        scores: Dict[int, float] = {}
        
        for topic in self._topics:
            match_count = 0
            for keyword in topic.keywords:
                if keyword.lower() in question_lower:
                    match_count += 1
            
            if match_count > 0:
                # Normalize score by number of keywords (0-1 range)
                scores[topic.id] = match_count / len(topic.keywords)
        
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    def extract_entities(self, text: str) -> List[Entity]:
        """
        Extract entities (DC codes, forms, benefits, conditions) from text.
        
        Uses regex patterns to identify:
        - Diagnostic Codes (e.g., 7101, 5201)
        - VA Forms (e.g., 21-526EZ)
        - Benefit programs (e.g., TDIU, Chapter 35)
        - Medical conditions (e.g., PTSD, TBI)
        
        Returns list of Entity objects.
        """
        entities: List[Entity] = []
        seen: Set[Tuple[str, str]] = set()  # Prevent duplicates
        
        for entity_type, patterns in ENTITY_PATTERNS.items():
            for pattern, name_template in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    value = match.group(1).upper() if match.groups() else match.group(0).upper()
                    
                    # Skip if we've already found this entity
                    key = (entity_type, value)
                    if key in seen:
                        continue
                    seen.add(key)
                    
                    # Generate human-readable name
                    if '{}' in name_template:
                        name = name_template.format(value)
                    else:
                        name = name_template
                    
                    entities.append(Entity(
                        type=entity_type,
                        value=value,
                        name=name,
                        confidence=1.0
                    ))
        
        return entities
    
    def get_or_create_entity(self, entity: Entity) -> Optional[int]:
        """
        Get entity ID from database, creating if not exists.
        
        Returns entity ID or None if DB unavailable.
        """
        if not self._db_available:
            return None
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                # Try to insert, get ID
                result = session.execute(text("""
                    INSERT INTO entities (type, value, name)
                    VALUES (:type, :value, :name)
                    ON CONFLICT (type, value) DO UPDATE SET name = COALESCE(EXCLUDED.name, entities.name)
                    RETURNING id
                """), {
                    "type": entity.type,
                    "value": entity.value,
                    "name": entity.name
                }).fetchone()
                
                session.commit()
                return result[0] if result else None
                
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Entity creation error: {e}")
            return None
    
    def link_question_to_entities(
        self,
        question_id: int,
        entities: List[Entity],
        confidence: float = 1.0
    ) -> bool:
        """
        Create edges from a question to its entities.
        
        Args:
            question_id: The events.id
            entities: List of Entity objects to link
            confidence: Confidence score for the links (0-1)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._db_available or not entities:
            return False
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                for entity in entities:
                    # Get or create entity
                    entity_id = self.get_or_create_entity(entity)
                    if not entity_id:
                        continue
                    
                    # Link question to entity
                    session.execute(text("""
                        INSERT INTO question_entities (question_id, entity_id, confidence)
                        VALUES (:q_id, :e_id, :conf)
                        ON CONFLICT (question_id, entity_id) DO UPDATE SET
                            confidence = EXCLUDED.confidence
                    """), {
                        "q_id": question_id,
                        "e_id": entity_id,
                        "conf": confidence
                    })
                
                session.commit()
                return True
                
            except Exception as e:
                print(f"[TOPIC_GRAPH] Entity link error: {e}")
                session.rollback()
                return False
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Entity link error: {e}")
            return False
    
    def link_question_to_sources(
        self,
        question_id: int,
        source_ids: List[str],
        relevance_scores: Optional[List[float]] = None
    ) -> bool:
        """
        Create edges from a question to its source chunks.
        
        Args:
            question_id: The events.id
            source_ids: List of corpus entry_ids used in the answer
            relevance_scores: Optional relevance scores for each source
            
        Returns:
            True if successful, False otherwise
        """
        if not self._db_available or not source_ids:
            return False
        
        if relevance_scores is None:
            relevance_scores = [1.0] * len(source_ids)
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                for source_id, score in zip(source_ids, relevance_scores):
                    session.execute(text("""
                        INSERT INTO question_sources (question_id, source_id, relevance_score)
                        VALUES (:q_id, :s_id, :score)
                        ON CONFLICT (question_id, source_id) DO UPDATE SET
                            relevance_score = EXCLUDED.relevance_score
                    """), {
                        "q_id": question_id,
                        "s_id": source_id,
                        "score": score
                    })
                
                session.commit()
                return True
                
            except Exception as e:
                print(f"[TOPIC_GRAPH] Source link error: {e}")
                session.rollback()
                return False
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Source link error: {e}")
            return False
    
    def find_similar_by_topic(
        self,
        topic_ids: List[int],
        limit: int = 5,
        exclude_question_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find cached questions sharing the same topic(s).
        
        This is THE single-join query that makes the graph useful:
        
        SELECT e.* FROM events e
        JOIN question_topics qt ON e.id = qt.question_id
        WHERE qt.topic_id = ANY(:topic_ids)
        
        Args:
            topic_ids: List of topic IDs to search for
            limit: Maximum results to return
            exclude_question_id: Optional question ID to exclude (the current question)
            
        Returns:
            List of cached response dicts with question, answer, etc.
        """
        if not self._db_available or not topic_ids:
            return []
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                # The magic single-join query using events table
                # Only get original answers (cache_hit = 'miss'), not cached ones
                query = """
                    SELECT DISTINCT 
                        e.id,
                        COALESCE(e.meta::json->>'question', '') as question,
                        COALESCE(e.meta::json->>'answer', '') as answer,
                        e.model_used,
                        e.ts as created_at
                    FROM events e
                    JOIN question_topics qt ON e.id = qt.question_id
                    WHERE qt.topic_id = ANY(:topic_ids)
                      AND e.type = 'chat_question'
                      AND e.meta::json->>'answer' IS NOT NULL
                      AND COALESCE(e.meta::json->>'cache_hit', 'miss') = 'miss'
                """
                
                params = {"topic_ids": topic_ids}
                
                if exclude_question_id:
                    query += " AND e.id != :exclude_id"
                    params["exclude_id"] = exclude_question_id
                
                query += """
                    ORDER BY e.ts DESC
                    LIMIT :limit
                """
                params["limit"] = limit
                
                rows = session.execute(text(query), params).mappings().all()
                
                results = []
                for row in rows:
                    if row['answer']:  # Only include if there's an answer
                        results.append({
                            "id": row['id'],
                            "query": row['question'],
                            "response": row['answer'],
                            "sources": [],  # Events table doesn't easily expose sources
                            "model_used": row['model_used'],
                            "hit_count": 0  # Not tracked in events
                        })
                
                return results
                
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Lookup error: {e}")
            return []
    
    def link_question_to_topics(
        self,
        question_id: int,
        topic_ids: List[int],
        confidence: float = 1.0
    ) -> bool:
        """
        Create edges from a cached question to its topics.
        
        Call this after caching a new response to build the graph.
        
        Args:
            question_id: The cached_responses.id
            topic_ids: List of topic IDs to link
            confidence: Confidence score for the links (0-1)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._db_available or not topic_ids:
            return False
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                # Insert edges (ignore conflicts for idempotency)
                for topic_id in topic_ids:
                    session.execute(text("""
                        INSERT INTO question_topics (question_id, topic_id, confidence)
                        VALUES (:q_id, :t_id, :conf)
                        ON CONFLICT (question_id, topic_id) DO UPDATE SET
                            confidence = EXCLUDED.confidence
                    """), {
                        "q_id": question_id,
                        "t_id": topic_id,
                        "conf": confidence
                    })
                
                session.commit()
                return True
                
            except Exception as e:
                print(f"[TOPIC_GRAPH] Link error: {e}")
                session.rollback()
                return False
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Link error: {e}")
            return False
    
    def find_by_entity(
        self,
        entities: List[Entity],
        limit: int = 5,
        exclude_question_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find cached questions that reference the same entities.
        
        2-JOIN query through entities table:
        Questions -> question_entities -> entities
        
        This finds related Q&A based on specific entities (DC codes, forms).
        More precise than topic-based lookup.
        """
        if not self._db_available or not entities:
            return []
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                # Build entity filter
                entity_filters = []
                for entity in entities:
                    entity_filters.append(f"(ent.type = '{entity.type}' AND ent.value = '{entity.value}')")
                
                if not entity_filters:
                    return []
                
                entity_where = " OR ".join(entity_filters)
                exclude_clause = f"AND e.id != {exclude_question_id}" if exclude_question_id else ""
                
                query = f"""
                    SELECT DISTINCT 
                        e.id,
                        COALESCE(e.meta::json->>'question', '') as question,
                        COALESCE(e.meta::json->>'answer', '') as answer,
                        e.model_used,
                        e.ts as created_at,
                        COALESCE(e.verified, false) as verified,
                        COUNT(DISTINCT qe.entity_id) as entity_matches
                    FROM events e
                    JOIN question_entities qe ON e.id = qe.question_id
                    JOIN entities ent ON qe.entity_id = ent.id
                    WHERE ({entity_where})
                      AND e.type = 'chat_question'
                      AND e.meta::json->>'answer' IS NOT NULL
                      AND COALESCE(e.meta::json->>'cache_hit', 'miss') = 'miss'
                      {exclude_clause}
                    GROUP BY e.id, e.meta, e.model_used, e.ts, e.verified
                    ORDER BY entity_matches DESC, e.ts DESC
                    LIMIT :limit
                """
                
                rows = session.execute(text(query), {"limit": limit}).mappings().all()
                
                results = []
                for row in rows:
                    if row['answer']:
                        results.append({
                            "id": row['id'],
                            "query": row['question'],
                            "response": row['answer'],
                            "sources": [],
                            "model_used": row['model_used'],
                            "verified": row['verified'],
                            "entity_matches": row['entity_matches'],
                            "match_type": "entity"
                        })
                
                return results
                
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Entity lookup error: {e}")
            return []
    
    def find_similar_enhanced(
        self,
        topic_ids: List[int],
        entities: List[Entity],
        limit: int = 5,
        exclude_question_id: Optional[int] = None,
        prefer_verified: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Enhanced lookup combining topics AND entities.
        
        Scoring:
        - Entity matches get 2x weight (more specific)
        - Verified responses get priority
        - Topic matches provide fallback
        
        This reduces hallucinations by finding answers that:
        1. Match specific entities (DC codes, forms)
        2. Are from verified/high-quality responses
        3. Fall back to topic matches if no entity matches
        """
        results = []
        seen_ids = set()
        
        # First: Try entity-based lookup (most specific)
        if entities:
            entity_results = self.find_by_entity(entities, limit, exclude_question_id)
            for r in entity_results:
                if r['id'] not in seen_ids:
                    seen_ids.add(r['id'])
                    results.append(r)
        
        # Second: Try topic-based lookup (fallback)
        if len(results) < limit and topic_ids:
            topic_results = self.find_similar_by_topic(
                topic_ids, 
                limit - len(results), 
                exclude_question_id
            )
            for r in topic_results:
                if r.get('id') not in seen_ids:
                    seen_ids.add(r.get('id'))
                    r['match_type'] = 'topic'
                    results.append(r)
        
        # Sort: Verified first, then by match type (entity > topic), then by recency
        if prefer_verified:
            results.sort(key=lambda x: (
                not x.get('verified', False),  # Verified first
                x.get('match_type', 'topic') != 'entity',  # Entity matches first
                0  # Keep original order otherwise
            ))
        
        return results[:limit]
    
    def verify_response(
        self,
        question_id: int,
        verified: bool = True,
        flagged: bool = False,
        flag_reason: Optional[str] = None
    ) -> bool:
        """
        Mark a response as verified or flagged.
        
        This builds the "trusted answers" set for higher-quality cache hits.
        """
        if not self._db_available:
            return False
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                session.execute(text("""
                    UPDATE events 
                    SET verified = :verified,
                        flagged = :flagged,
                        flag_reason = :flag_reason
                    WHERE id = :q_id
                """), {
                    "q_id": question_id,
                    "verified": verified,
                    "flagged": flagged,
                    "flag_reason": flag_reason
                })
                
                session.commit()
                return True
                
            except Exception as e:
                print(f"[TOPIC_GRAPH] Verify error: {e}")
                session.rollback()
                return False
            finally:
                session.close()
                
        except Exception as e:
            print(f"[TOPIC_GRAPH] Verify error: {e}")
            return False
    
    def get_topic_by_slug(self, slug: str) -> Optional[Topic]:
        """Get a topic by its slug."""
        for topic in self._topics:
            if topic.slug == slug:
                return topic
        return None
    
    def get_topic_stats(self) -> Dict[str, Any]:
        """Get statistics about the topic graph."""
        if not self._db_available:
            return {"error": "Database not available"}
        
        try:
            from db import SessionLocal
            session = SessionLocal()
            
            try:
                from sqlalchemy import text
                
                # Count questions per topic
                rows = session.execute(text("""
                    SELECT t.slug, t.name, COUNT(qt.question_id) as question_count
                    FROM topics t
                    LEFT JOIN question_topics qt ON t.id = qt.topic_id
                    GROUP BY t.id, t.slug, t.name
                    ORDER BY question_count DESC
                """)).mappings().all()
                
                topic_stats = [
                    {
                        "slug": row['slug'],
                        "name": row['name'],
                        "question_count": row['question_count']
                    }
                    for row in rows
                ]
                
                # Total edges
                total_edges = session.execute(text(
                    "SELECT COUNT(*) FROM question_topics"
                )).scalar() or 0
                
                return {
                    "topics": topic_stats,
                    "total_topics": len(self._topics),
                    "total_edges": total_edges
                }
                
            finally:
                session.close()
                
        except Exception as e:
            return {"error": str(e)}


# Global instance
_topic_graph: Optional[TopicGraph] = None


def get_topic_graph() -> TopicGraph:
    """Get or create the global topic graph instance."""
    global _topic_graph
    if _topic_graph is None:
        _topic_graph = TopicGraph()
        _topic_graph.initialize()
    return _topic_graph


def classify_and_link(question_id: int, question_text: str) -> Tuple[List[int], List[Entity]]:
    """
    Convenience function to classify a question and link it to topics AND entities.
    
    Args:
        question_id: The events.id
        question_text: The question text to classify
        
    Returns:
        Tuple of (topic_ids, entities) the question was linked to
    """
    graph = get_topic_graph()
    
    # Classify by topic
    topic_ids = graph.classify_question(question_text)
    if topic_ids:
        graph.link_question_to_topics(question_id, topic_ids)
    
    # Extract and link entities
    entities = graph.extract_entities(question_text)
    if entities:
        graph.link_question_to_entities(question_id, entities)
    
    return topic_ids, entities


def link_sources(question_id: int, source_ids: List[str], scores: Optional[List[float]] = None) -> bool:
    """
    Convenience function to link a question to its source chunks.
    
    Args:
        question_id: The events.id
        source_ids: List of corpus entry_ids used in the answer
        scores: Optional relevance scores
        
    Returns:
        True if successful
    """
    graph = get_topic_graph()
    return graph.link_question_to_sources(question_id, source_ids, scores)


def find_by_topic(question_text: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Convenience function to find cached answers by topic.
    
    Args:
        question_text: The question to find similar answers for
        limit: Maximum results
        
    Returns:
        List of cached response dicts
    """
    graph = get_topic_graph()
    topic_ids = graph.classify_question(question_text)
    
    if not topic_ids:
        return []
    
    return graph.find_similar_by_topic(topic_ids, limit=limit)


def find_enhanced(question_text: str, limit: int = 5, prefer_verified: bool = True) -> List[Dict[str, Any]]:
    """
    Convenience function for enhanced lookup using both topics AND entities.
    
    This is the recommended function for cache lookups as it:
    1. Finds entity matches first (most specific, reduces hallucinations)
    2. Falls back to topic matches
    3. Prefers verified responses
    
    Args:
        question_text: The question to find similar answers for
        limit: Maximum results
        prefer_verified: Whether to prioritize verified responses
        
    Returns:
        List of cached response dicts with match_type indicating source
    """
    graph = get_topic_graph()
    
    # Extract both topics and entities
    topic_ids = graph.classify_question(question_text)
    entities = graph.extract_entities(question_text)
    
    # Use enhanced lookup
    return graph.find_similar_enhanced(
        topic_ids=topic_ids,
        entities=entities,
        limit=limit,
        prefer_verified=prefer_verified
    )

