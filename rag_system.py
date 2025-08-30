"""
Advanced RAG System for VA Benefits Knowledge Base
Implements proper embedding matching, spell checking, query expansion, 
hybrid search, and intelligent reranking.
"""

import os
import re
import json
import time
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib

@dataclass
class SearchResult:
    chunk_id: str
    text: str
    heading: str
    score: float
    source_url: str
    diagnostic_code: Optional[str] = None
    relevance_score: float = 0.0
    cross_validation_score: float = 0.0
    retrieval_method: str = "semantic"
    confidence: float = 0.0

class AdvancedRAGSystem:
    def __init__(self, pinecone_index, openai_client):
        self.index = pinecone_index
        self.openai_client = openai_client
        self.namespace = "production"
        # In-memory query result cache (normalized_query → {ts, results, query_data})
        self._result_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl_seconds: int = 300
        self.max_cache_entries: int = 500
        
        # VA-specific diagnostic codes and synonyms
        self.va_conditions = {
            'ptsd': {
                'codes': ['9411'],
                'synonyms': ['post traumatic stress disorder', 'posttraumatic stress', 'combat ptsd', 'military ptsd'],
                'related_terms': ['anxiety', 'depression', 'mental health', 'trauma', 'nightmares', 'flashbacks']
            },
            'tbi': {
                'codes': ['8045'],
                'synonyms': ['traumatic brain injury', 'head injury', 'concussion', 'brain trauma'],
                'related_terms': ['cognitive', 'memory', 'headache', 'dizziness']
            },
            'ulnar neuropathy': {
                'codes': ['8515'],
                'synonyms': ['ulnar nerve', 'cubital tunnel', 'elbow nerve'],
                'related_terms': ['numbness', 'tingling', 'weakness', 'hand', 'forearm']
            },
            'carpal tunnel': {
                'codes': ['8515'],
                'synonyms': ['carpal tunnel syndrome', 'median nerve', 'wrist'],
                'related_terms': ['numbness', 'tingling', 'weakness', 'hand pain']
            },
            'tinnitus': {
                'codes': ['6260'],
                'synonyms': ['ringing ears', 'ear ringing', 'hearing'],
                'related_terms': ['noise', 'buzzing', 'whistling', 'hearing loss']
            },
            'hearing loss': {
                'codes': ['6100'],
                'synonyms': ['deafness', 'hearing impairment', 'auditory'],
                'related_terms': ['decibel', 'audiogram', 'speech discrimination']
            }
        }
        
        # Common VA rating terms
        self.rating_terms = [
            'rating', 'percent', 'percentage', '10%', '20%', '30%', '40%', '50%', '60%', '70%', '80%', '90%', '100%',
            'disability', 'compensation', 'schedule', 'criteria', 'diagnostic code', 'CFR'
        ]

    def classify_query_intent(self, query: str) -> str:
        """
        Classify the primary intent of the query: rating | eligibility | process | general
        """
        q = (query or "").lower()
        if any(t in q for t in ['rating', 'percent', '%', 'disability rating', 'criteria']):
            return 'rating'
        if any(t in q for t in ['eligible', 'qualify', 'service connection', 'presumptive']):
            return 'eligibility'
        if any(t in q for t in ['how to', 'apply', 'claim', 'appeal', 'process', 'steps']):
            return 'process'
        return 'general'

    # --------------------
    # Caching Utilities
    # --------------------
    def _normalize_query(self, q: str) -> str:
        return ' '.join((q or '').lower().split())

    def _prune_cache(self) -> None:
        if len(self._result_cache) <= self.max_cache_entries:
            return
        # Evict oldest entries
        items = sorted(self._result_cache.items(), key=lambda kv: kv[1].get('ts', 0.0))
        to_remove = len(self._result_cache) - self.max_cache_entries
        for k, _ in items[:to_remove]:
            self._result_cache.pop(k, None)

    def _get_cached_results(self, query: str) -> Optional[Tuple[List['SearchResult'], Dict[str, Any]]]:
        now = time.time()
        nq = self._normalize_query(query)
        entry = self._result_cache.get(nq)
        if entry and (now - entry['ts'] <= self.cache_ttl_seconds):
            return entry['results'], entry['query_data']
        # Fuzzy match fallback
        best_key = None
        best_sim = 0.0
        for k in list(self._result_cache.keys()):
            e = self._result_cache.get(k)
            if not e:
                continue
            if now - e['ts'] > self.cache_ttl_seconds:
                continue
            sim = SequenceMatcher(None, nq, k).ratio()
            if sim > best_sim:
                best_sim = sim
                best_key = k
        if best_key and best_sim >= 0.93:
            e = self._result_cache[best_key]
            return e['results'], e['query_data']
        return None

    def _set_cached_results(self, query: str, results: List['SearchResult'], query_data: Dict[str, Any]) -> None:
        self._result_cache[self._normalize_query(query)] = {
            'ts': time.time(),
            'results': results,
            'query_data': query_data,
        }
        self._prune_cache()

    def spell_check_and_expand(self, query: str) -> Dict[str, Any]:
        """
        Spell check query and expand with VA-specific terms
        """
        query_lower = query.lower()
        expanded_terms = set()
        diagnostic_codes = set()
        matched_conditions = []
        
        # Check for exact condition matches
        for condition, data in self.va_conditions.items():
            if condition in query_lower or any(syn in query_lower for syn in data['synonyms']):
                matched_conditions.append(condition)
                expanded_terms.update(data['synonyms'])
                expanded_terms.update(data['related_terms'])
                diagnostic_codes.update(data['codes'])
        
        # Spell checking for common typos
        typo_corrections = {
            'ptds': 'ptsd',
            'tinnitis': 'tinnitus',
            'carple': 'carpal',
            'neuropaty': 'neuropathy',
            'diagonstic': 'diagnostic',
            'veterens': 'veterans',
            'disabilty': 'disability'
        }
        
        corrected_query = query_lower
        for typo, correction in typo_corrections.items():
            if typo in corrected_query:
                corrected_query = corrected_query.replace(typo, correction)
                print(f"🔤 Spell correction: '{typo}' → '{correction}'")
        
        # Add rating-related terms if asking about ratings
        if any(term in query_lower for term in ['rating', 'percent', 'compensation']):
            expanded_terms.update(['rating schedule', 'disability rating', 'percentage', 'criteria'])
        
        return {
            'original_query': query,
            'corrected_query': corrected_query,
            'expanded_terms': list(expanded_terms),
            'diagnostic_codes': list(diagnostic_codes),
            'matched_conditions': matched_conditions
        }

    def generate_query_embedding(self, text: str) -> List[float]:
        """
        Generate real embeddings for query using OpenAI API (matching thriving-walnut reindexed data)
        """
        try:
            print(f"🔍 Generating real 1024D embedding for query: '{text[:50]}...'")
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=text,
                dimensions=1024  # Match the thriving-walnut index dimension
            )
            embedding = response.data[0].embedding
            print(f"✅ Generated real {len(embedding)}D embedding")
            return embedding
        except Exception as e:
            print(f"⚠️ Failed to generate real embedding: {e}")
            print(f"🔧 Falling back to semantic dummy vector (1024-dim)")
            return self.generate_semantic_fallback_vector(text, dimension=1024)

    def generate_semantic_fallback_vector(self, text: str, dimension: int = 1024) -> List[float]:
        """
        Generate semantic fallback vector that matches the ingestion pattern
        """
        import random
        import hashlib
        
        # Use same medical terms as ingestion
        medical_terms = ['ptsd', 'disability', 'veteran', 'rating', 'condition', 'service',
                        'compensation', 'benefit', 'medical', 'diagnosis', 'treatment',
                        'neuropathy', 'nerve', 'carpal', 'tunnel', 'ulnar', 'anxiety',
                        'depression', 'mental', 'health', 'stress', 'trauma']
        
        base_seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        term_influence = 0
        for term in medical_terms:
            if term in text.lower():
                term_influence += hash(term) % 1000
        
        combined_seed = (base_seed + term_influence) % (2**32)
        random.seed(combined_seed)
        
        vector = []
        for i in range(dimension):
            if i < dimension // 4:
                base_val = random.gauss(0.1 if any(term in text.lower() for term in medical_terms[:5]) else -0.1, 0.5)
            elif i < dimension // 2:
                base_val = random.gauss(0.2 if any(term in text.lower() for term in medical_terms[5:15]) else 0, 0.4)
            elif i < 3 * dimension // 4:
                base_val = random.gauss(0.15 if any(word in text.lower() for word in ['rating', 'percent', '%', 'compensation']) else 0, 0.3)
            else:
                base_val = random.gauss(0, 0.2)
            vector.append(base_val)
        
        # Normalize vector
        magnitude = sum(x*x for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x/magnitude for x in vector]
        
        return vector

    def _convert_matches_to_results(self, matches, retrieval_method: str, query_data: Dict[str, Any]) -> List[SearchResult]:
        results: List[SearchResult] = []
        for match in (matches or []):
            md = getattr(match, 'metadata', None)
            if not md:
                continue
            text_content = md.get('text', '')
            if not text_content:
                continue
            # Extract diagnostic code if present in text
            diagnostic_code = None
            for code in query_data.get('diagnostic_codes', []):
                if code and code in text_content:
                    diagnostic_code = code
                    break
            res = SearchResult(
                chunk_id=match.id,
                text=text_content,
                heading=md.get('heading', 'Unknown Section'),
                score=getattr(match, 'score', 0.0) or 0.0,
                source_url=md.get('source_url', 'https://veteransbenefitskb.com'),
                diagnostic_code=diagnostic_code,
                retrieval_method=retrieval_method,
            )
            results.append(res)
        return results

    def _build_query_variants(self, query_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Return list of (variant_name, query_text) for diversified querying."""
        base = query_data['corrected_query']
        variants: List[Tuple[str, str]] = [('semantic:base', base)]
        # Expanded
        if query_data.get('expanded_terms'):
            expanded = base + ' ' + ' '.join(query_data['expanded_terms'][:8])
            variants.append(('semantic:expanded', expanded))
        # Diagnostic focused
        if query_data.get('diagnostic_codes'):
            diag = ' '.join(query_data['diagnostic_codes'] + ['diagnostic code', 'rating criteria'])
            variants.append(('semantic:diagnostic_terms', diag))
        # Condition synonyms
        cond_terms: List[str] = []
        for cond in query_data.get('matched_conditions', []):
            data = self.va_conditions.get(cond)
            if data:
                cond_terms.extend(data.get('synonyms', [])[:3])
        if cond_terms:
            cond_query = ' '.join(cond_terms + ['rating', 'criteria'])
            variants.append(('semantic:condition_terms', cond_query))
        # Rating terms emphasis
        rating_q = base + ' ' + ' '.join(self.rating_terms[:6])
        variants.append(('semantic:rating_terms', rating_q))
        return variants

    def _semantic_search_pass(self, query_data: Dict[str, Any], top_k: int) -> List[SearchResult]:
        results: List[SearchResult] = []
        variants = self._build_query_variants(query_data)
        for name, q in variants:
            print(f"🔎 Pass: {name} → '{q[:100]}...'")
            vec = self.generate_query_embedding(q)
            try:
                res = self.index.query(vector=vec, top_k=top_k, include_metadata=True, namespace=self.namespace)
                converted = self._convert_matches_to_results(res.matches, name, query_data)
                results.extend(converted)
            except Exception as e:
                print(f"❌ Variant {name} failed: {e}")
                continue
        return results

    def _diagnostic_code_search_pass(self, query_data: Dict[str, Any], top_k: int) -> List[SearchResult]:
        codes = query_data.get('diagnostic_codes', [])
        if not codes:
            return []
        code_query = ' '.join(codes + ['diagnostic code', 'rating criteria'])
        print(f"🎯 Pass: diagnostic_focused → '{code_query[:100]}...'")
        vec = self.generate_query_embedding(code_query)
        try:
            res = self.index.query(vector=vec, top_k=top_k, include_metadata=True, namespace=self.namespace)
            return self._convert_matches_to_results(res.matches, 'diagnostic_focused', query_data)
        except Exception as e:
            print(f"❌ Diagnostic pass failed: {e}")
            return []

    def _condition_search_pass(self, query_data: Dict[str, Any], top_k: int) -> List[SearchResult]:
        cond_terms: List[str] = []
        for cond in query_data.get('matched_conditions', []):
            data = self.va_conditions.get(cond)
            if data:
                cond_terms.extend(data.get('synonyms', [])[:3])
        if not cond_terms:
            return []
        cond_query = ' '.join(cond_terms + ['rating', 'criteria'])
        print(f"🏥 Pass: condition_specific → '{cond_query[:100]}...'")
        vec = self.generate_query_embedding(cond_query)
        try:
            res = self.index.query(vector=vec, top_k=top_k, include_metadata=True, namespace=self.namespace)
            return self._convert_matches_to_results(res.matches, 'condition_specific', query_data)
        except Exception as e:
            print(f"❌ Condition pass failed: {e}")
            return []

    def multi_pass_retrieval(self, query_data: Dict[str, Any]) -> List[SearchResult]:
        """Run multiple retrieval strategies and aggregate results."""
        intent = (query_data.get('intent') or 'general')
        if intent == 'rating':
            tk_sem, tk_diag, tk_cond = 28, 24, 18
        elif intent == 'eligibility':
            tk_sem, tk_diag, tk_cond = 32, 20, 18
        elif intent == 'process':
            tk_sem, tk_diag, tk_cond = 20, 12, 12
        else:
            tk_sem, tk_diag, tk_cond = 28, 20, 16
        aggregated: List[SearchResult] = []
        aggregated.extend(self._semantic_search_pass(query_data, top_k=tk_sem))
        aggregated.extend(self._diagnostic_code_search_pass(query_data, top_k=tk_diag))
        aggregated.extend(self._condition_search_pass(query_data, top_k=tk_cond))
        print(f"📈 Multi-pass collected {len(aggregated)} candidates")
        return aggregated

    def calculate_relevance_score(self, result: SearchResult, query_data: Dict[str, Any]) -> float:
        """
        Calculate relevance score based on multiple factors
        """
        score = result.score
        text_lower = result.text.lower()
        heading_lower = result.heading.lower()
        
        # Boost for diagnostic codes
        for code in query_data['diagnostic_codes']:
            if code in text_lower or code in heading_lower:
                score += 0.3
        
        # Boost for matched conditions
        for condition in query_data['matched_conditions']:
            if condition in text_lower or condition in heading_lower:
                score += 0.2
        
        # Boost for rating-related content
        if any(term in query_data['original_query'].lower() for term in ['rating', 'percent']):
            if any(term in text_lower for term in self.rating_terms):
                score += 0.15
        
        # Boost for exact term matches
        query_terms = query_data['corrected_query'].split()
        for term in query_terms:
            if len(term) > 3 and term in text_lower:
                score += 0.1
        
        # Penalty for very short chunks (likely not informative)
        if len(result.text) < 100:
            score -= 0.1
        
        return score

    def _text_similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, (a or '').lower(), (b or '').lower()).ratio()

    def advanced_relevance_scoring(self, results: List[SearchResult], query_data: Dict[str, Any]) -> List[SearchResult]:
        """Compute enhanced relevance with cross-validation across methods and deduplicate."""
        print(f"🧮 Scoring {len(results)} results (advanced)")
        # First pass: base relevance
        for r in results:
            r.relevance_score = self.calculate_relevance_score(r, query_data)
        # Cross-validation: how many other methods retrieve similar text
        for i, r in enumerate(results):
            seen_methods = set()
            for j, o in enumerate(results):
                if i == j:
                    continue
                if r.retrieval_method == o.retrieval_method:
                    continue
                if self._text_similarity(r.text, o.text) > 0.7:
                    seen_methods.add(o.retrieval_method)
            r.cross_validation_score = min(len(seen_methods) * 0.3, 1.0)
            # Confidence mixes both
            r.confidence = max(0.0, min(r.relevance_score * 0.7 + r.cross_validation_score * 0.3, 1.0))
        # Deduplicate by chunk_id (keep best)
        best_by_chunk: Dict[str, SearchResult] = {}
        for r in results:
            existing = best_by_chunk.get(r.chunk_id)
            if not existing or (r.relevance_score * 0.6 + r.cross_validation_score * 0.4) > (existing.relevance_score * 0.6 + existing.cross_validation_score * 0.4):
                best_by_chunk[r.chunk_id] = r
        deduped = list(best_by_chunk.values())
        # Sort by combined
        ranked = sorted(deduped, key=lambda x: (x.relevance_score * 0.6 + x.cross_validation_score * 0.4), reverse=True)
        for idx, r in enumerate(ranked[:10]):
            print(f"🏆 {idx+1}: rel={r.relevance_score:.3f} cross={r.cross_validation_score:.3f} conf={r.confidence:.3f} method={r.retrieval_method}")
        return ranked

    def search_with_fallback(self, query: str, max_results: int = 12) -> Tuple[List[SearchResult], Dict[str, Any]]:
        """Enhanced search: multi-pass retrieval + advanced scoring, larger result set."""
        print(f"🔍 Processing query: '{query}'")
        # 1) Cache check
        cached = self._get_cached_results(query)
        if cached:
            results_cached, qd_cached = cached
            print(f"⚡ Cache hit → returning {len(results_cached[:max_results])} results")
            return results_cached[:max_results], qd_cached
        query_data = self.spell_check_and_expand(query)
        intent = self.classify_query_intent(query)
        query_data['intent'] = intent
        if query_data.get('diagnostic_codes'):
            print(f"🎯 Found diagnostic codes: {query_data['diagnostic_codes']}")
        # Multi-pass retrieval
        candidates = self.multi_pass_retrieval(query_data)
        if not candidates:
            print("❌ No results from multi-pass retrieval")
            return [], query_data
        # Advanced scoring
        ranked = self.advanced_relevance_scoring(candidates, query_data)
        # Threshold and top-N
        threshold = 0.25
        filtered = [r for r in ranked if r.relevance_score >= threshold]
        final_results = filtered[:max_results]
        print(f"✅ Returning {len(final_results)} high-quality results (intent={intent})")
        # 5) Cache set
        self._set_cached_results(query, final_results, query_data)
        return final_results, query_data

    def _generate_fallback_summary(self, query: str, results: List[SearchResult]) -> str:
        """Generate a structured fallback summary when OpenAI times out"""
        if not results:
            return "I found relevant information but couldn't generate a complete response due to a timeout. Please try rephrasing your question."
        
        summary_parts = [f"# VA Disability Information: {query.title()}\n"]
        
        for i, result in enumerate(results[:3], 1):
            summary_parts.append(f"## Section {i}: {result.heading}")
            if result.diagnostic_code:
                summary_parts.append(f"**Diagnostic Code:** {result.diagnostic_code}")
            
            # Extract key information from text
            text_snippet = result.text[:400] + "..." if len(result.text) > 400 else result.text
            summary_parts.append(f"{text_snippet}\n")
        
        summary_parts.append("*Note: This is a summary due to processing timeout. For more detailed information, please try your question again.*")
        
        return "\n\n".join(summary_parts)

    def generate_answer(self, query: str, results: List[SearchResult]) -> Dict[str, Any]:
        """
        Generate answer using GPT with high-quality, structured context
        """
        if not results:
            return {
                "success": False,
                "content": "I couldn't find relevant information for your question. Please try rephrasing or asking about a specific VA condition or diagnostic code.",
                "citations": [],
                "source": "advanced_rag_system",
                "metadata": {"error": "no_results_found"}
            }
        
        # Build richer, structured context from top results
        context_parts = []
        citations = []
        
        for i, result in enumerate(results):
            context_parts.append(f"Section: {result.heading}\nConfidence: {result.confidence:.2f}\n{result.text}")
            citations.append({
                'text': result.text[:400] + "..." if len(result.text) > 400 else result.text,
                'source_url': result.source_url,
                'heading': result.heading,
                'score': result.relevance_score,
                'rank': i + 1,
                'diagnostic_code': result.diagnostic_code,
                'method': result.retrieval_method
            })
        
        context_text = '\n\n'.join(context_parts)
        
        # Generate answer with GPT (with timeout handling)
        try:
            prompt = f"""Based on the following VA disability information, provide a clear and structured answer to the veteran's question.

Context from VA Rating Guidelines:
{context_text}

User Question: {query}

Please provide a well-organized answer that:
1. Uses clear headings and bullet points for organization
2. Directly addresses the veteran's specific question
3. Includes specific rating percentages and criteria when available
4. Mentions relevant diagnostic codes if applicable
5. Provides practical examples when useful
6. Aims for 800-1200 tokens to be comprehensive yet concise

Answer:"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert VA disability benefits advisor. Provide clear, well-structured answers with headings and detailed information. Be comprehensive but concise to help veterans efficiently."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1200,
                temperature=0.1,
                timeout=25.0  # 25 second timeout to prevent worker timeout
            )
            
            answer = response.choices[0].message.content.strip()
            
            return {
                "success": True,
                "content": answer,
                "citations": citations,
                "source": "advanced_rag_system",
                "metadata": {
                    "model": "gpt-4",
                    "chunks_used": len(results),
                    "highest_score": results[0].relevance_score if results else 0,
                    "diagnostic_codes": [r.diagnostic_code for r in results if r.diagnostic_code]
                }
            }
            
        except Exception as e:
            print(f"❌ Error generating answer: {e}")
            
            # Timeout fallback: provide structured summary from top results
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                print("🔄 Timeout detected, providing fallback summary...")
                fallback_content = self._generate_fallback_summary(query, results[:3])
                return {
                    "success": True,
                    "content": fallback_content,
                    "citations": citations[:3],
                    "source": "advanced_rag_system_fallback",
                    "metadata": {"fallback_reason": "timeout", "original_error": str(e)}
                }
            
            return {
                "success": False,
                "content": f"I found relevant information but encountered an error generating the response: {str(e)}",
                "citations": citations[:3],
                "source": "advanced_rag_system",
                "metadata": {"error": str(e)}
            }
