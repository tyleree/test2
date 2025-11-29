"""
Topic Graph for Smart Cache Lookups

Implements a lightweight topic classification system for questions,
enabling topic-based cache lookups with a single PostgreSQL join.

Architecture:
- Questions are classified into predefined topics using keyword matching
- Topics are stored in PostgreSQL with many-to-many relationships
- Cache lookups can find related questions via topic membership

Usage:
    graph = TopicGraph()
    topic_ids = graph.classify_question("What is my VA disability rating?")
    # -> [1]  (disability_ratings topic)
    
    cached = graph.find_similar_by_topic(topic_ids)
    # -> Returns cached Q&A pairs sharing the same topic(s)
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Topic:
    """A topic node in the graph."""
    id: int
    slug: str
    name: str
    keywords: List[str]


class TopicGraph:
    """
    Topic-based graph for question classification and lookup.
    
    Designed for minimal database overhead:
    - Topics are loaded once at initialization
    - Classification is done in-memory (no DB query)
    - Lookups use a single JOIN query
    """
    
    def __init__(self):
        self._topics: List[Topic] = []
        self._initialized = False
        self._db_available = False
    
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
                
                # Check if topics table exists
                exists = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'topics'
                    )
                """)).scalar()
                
                if not exists:
                    print("[TOPIC_GRAPH] Topics table not found - run scripts/topic_graph_setup.sql")
                    return False
                
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


def classify_and_link(question_id: int, question_text: str) -> List[int]:
    """
    Convenience function to classify a question and link it to topics.
    
    Args:
        question_id: The cached_responses.id
        question_text: The question text to classify
        
    Returns:
        List of topic IDs the question was linked to
    """
    graph = get_topic_graph()
    topic_ids = graph.classify_question(question_text)
    
    if topic_ids:
        graph.link_question_to_topics(question_id, topic_ids)
    
    return topic_ids


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

