# QA Test Summary - CRITICAL ISSUES IDENTIFIED

**Date:** 2025-12-06  
**Tests Run:** 230  
**API Success Rate:** 100% (all returned responses)  
**ACTUAL Accuracy Rate:** ~40% (severe content issues)

---

## 🚨 EXECUTIVE SUMMARY - CRITICAL FAILURES

The RAG system has **severe caching and retrieval issues** that are causing completely wrong answers to be returned. Despite having the correct content in the corpus, cached responses from semantically similar queries are being returned for unrelated topics.

---

## 🔴 CRITICAL ISSUE #1: GI Bill Returns VR&E Content (100% Failure)

**Every single GI Bill question returns Chapter 31 VR&E content instead of GI Bill content.**

| Question | Expected Topic | Actual Answer |
|----------|---------------|---------------|
| "What is the GI Bill?" | GI Bill education benefits | VR&E/Chapter 31 employment |
| "How do I apply for the Post-9/11 GI Bill?" | Post-9/11 GI Bill application | VR&E program description |
| "What is Chapter 33?" | Post-9/11 GI Bill | VR&E program description |
| "What is the Montgomery GI Bill?" | MGIB Chapter 30 | VR&E program description |
| "Can dependents use GI Bill benefits?" | DEA/Transfer of Benefits | VR&E program description |
| "What is Chapter 30?" | MGIB Active Duty | VR&E program description |
| "How much does the GI Bill pay?" | Payment rates | VR&E program description |
| "What is the housing allowance for GI Bill?" | BAH rates | VR&E program description |
| "Can I transfer my GI Bill benefits?" | TEB requirements | VR&E program description |
| "What is Chapter 35?" | DEA survivor benefits | VR&E program description |
| "How long do GI Bill benefits last?" | Duration/eligibility | VR&E program description |

**Root Cause:** Likely L2/L3 cache returning cached "chapter/education" semantic match from VR&E queries. GI Bill content exists in corpus but is never retrieved.

**Impact:** Veterans asking about education benefits get completely wrong employment rehab info.

---

## 🔴 CRITICAL ISSUE #2: CHAMPVA Returns Agent Orange/DEA Content (80% Failure)

**Most CHAMPVA questions return Agent Orange survivor benefits or DEA info instead.**

| Question | Expected Topic | Actual Answer |
|----------|---------------|---------------|
| "What is the CHAMPVA deductible?" | CHAMPVA cost-sharing | Agent Orange children benefits |
| "Does CHAMPVA cover prescriptions?" | CHAMPVA pharmacy | **DC 9411 PTSD code** (completely unrelated!) |
| "Can children use CHAMPVA?" | CHAMPVA eligibility | Agent Orange children benefits |
| "Is CHAMPVA the same as TRICARE?" | CHAMPVA vs TRICARE | Agent Orange children benefits |
| "What is the CHAMPVA income limit?" | CHAMPVA eligibility | Agent Orange children benefits |
| "Does CHAMPVA cover mental health?" | CHAMPVA mental health | **DC 9411 PTSD code** |
| "How do I file a CHAMPVA claim?" | CHAMPVA claims process | Agent Orange children benefits |
| "What happens to CHAMPVA if spouse remarries?" | CHAMPVA eligibility | Agent Orange children benefits |

**Root Cause:** "CHAMPVA" and "children/dependents" semantic similarity is matching Agent Orange survivor benefits queries. The word "dependents" may be linking to DEA (Dependents Educational Assistance).

**Impact:** Spouses/dependents of disabled veterans get completely wrong information about their healthcare coverage.

---

## 🔴 CRITICAL ISSUE #3: VR&E Questions Return Only Application Info (70% Failure)

**Many VR&E questions return "how to apply" instead of answering the actual question.**

| Question | Expected Answer | Actual Answer |
|----------|----------------|---------------|
| "Can I use VR&E and GI Bill together?" | Concurrent use policy | How to apply for VR&E |
| "What is the VR&E subsistence allowance?" | Payment rates | How to apply for VR&E |
| "How long can I use VR&E benefits?" | Duration/entitlement | How to apply for VR&E |
| "What disability rating do I need for VR&E?" | 10%/20% requirements | How to apply for VR&E |
| "Can VR&E pay for graduate school?" | Education track info | How to apply for VR&E |
| "Can VR&E help with self-employment?" | Self-employment track | Agent Orange children benefits (!!) |

**Root Cause:** Cached "VR&E" query response is being returned regardless of what VR&E question is asked.

---

## 🔴 CRITICAL ISSUE #4: DC Code Direct Lookups Fail (75% Failure)

**"What is DC XXXX?" queries mostly fail even though the codes are in the corpus.**

| Query | Expected | Actual |
|-------|----------|--------|
| "What is DC 7101?" | Hypertension | "I don't have enough information" |
| "What is DC 7007?" | Hypertensive Heart Disease | "I don't have enough information" |
| "What is DC 6847?" | Sleep Apnea | "I don't have enough information" |
| "What is DC 6600?" | Chronic Bronchitis | Returns DC 6604 (COPD) info |
| "What is DC 8100?" | Migraine Headaches | "I don't have enough information" |
| "What is DC 7305?" | Duodenal Ulcer | "I don't have enough information" |
| "What is DC 6100?" | Hearing Loss | "I don't have enough information" |
| "What is DC 7806?" | Dermatitis/Eczema | "I don't have enough information" |
| "What is DC 5242?" | Degenerative Arthritis Spine | "I don't have enough information" |

**Contrast:** Natural language works fine:
- "What is the diagnostic code for GERD?" → Correctly returns DC 7206 ✓
- "What is the diagnostic code for hearing loss?" → Correctly returns DC 6100 ✓
- "What is the diagnostic code for erectile dysfunction?" → Correctly returns DC 7522 ✓

**Root Cause:** Query preprocessing for "DC XXXX" pattern exists but may not be working, OR semantic search can't match the preprocessed text.

---

## 🔴 CRITICAL ISSUE #5: "Secondary to" Questions Return Wrong Content

**Questions about secondary conditions return diagnostic codes instead of answering.**

| Question | Expected | Actual |
|----------|----------|--------|
| "Can I get service connected for hypertension as secondary to PTSD?" | Secondary service connection info | "DC 9411 is the code for PTSD" |
| "Can sleep apnea be secondary to PTSD?" | Secondary connection info | "DC 9411 is the code for PTSD" |

**Root Cause:** "PTSD" keyword triggers cached DC code response instead of understanding the question context.

---

## 🔴 CRITICAL ISSUE #6: Sleep Apnea Questions Return Hallucinated Content

| Question | Expected | Actual |
|----------|----------|--------|
| "What is the 50% rating for sleep apnea?" | CPAP prescribed = 50% | "I don't have specific information about whether heart disease can be secondary to sleep apnea" |
| "Do I need a sleep study for sleep apnea?" | Sleep study requirements | Same hallucinated response |

**Root Cause:** Cached response from a different sleep apnea question is being returned.

---

## 🟡 MODERATE ISSUE #7: Protection Rules Still Show /ears URL

The 5/10/20 year protection rule queries still show `veteransbenefitskb.com/ears` in some source citations alongside the correct `/ratingsindex#protection` URL. The `/ears` URL is incorrect - this page is about hearing/ear conditions.

---

## 🟢 WHAT'S WORKING WELL

| Category | Success Rate | Examples |
|----------|-------------|----------|
| 1151 Claims | 90% | "What is a 1151 claim?" ✓ |
| Federal Tort Claims | 90% | "What is a federal tort claim?" ✓ |
| Agent Orange Overview | 85% | "What is Agent Orange?" ✓ |
| Protection Rules | 80% | "What is the 5/10/20 year rule?" ✓ |
| Natural Language DC Lookups | 80% | "What is the diagnostic code for [X]?" ✓ |
| Some VR&E Tracks | 70% | "What is reemployment track?" ✓ |
| Some Conditions | 70% | "How is COPD rated?" ✓ |

---

## ROOT CAUSE ANALYSIS

### Primary Issue: Aggressive Semantic Caching

The L2 (semantic) and L3 (topic-based) caching system appears to be:

1. **Over-matching on keywords**: "chapter", "education", "dependents", "benefits" trigger wrong cached responses
2. **Not invalidating properly**: Cache was supposed to clear on corpus change but old responses persist
3. **Ignoring query intent**: Same cached response returned regardless of what's actually being asked

### Evidence:
- Same VR&E response returned for ALL GI Bill queries
- Same Agent Orange children response returned for ALL CHAMPVA queries  
- Same "how to apply" response returned for most VR&E sub-questions
- Same PTSD DC code returned for any query mentioning "PTSD"

### Suspected Location:
- `src/response_cache.py` - Semantic matching threshold may be too low
- `src/topic_graph.py` - Topic associations may be too broad
- Database `cached_responses` table may have stale entries despite corpus hash change

---

## RECOMMENDED FIXES (Priority Order)

### 🔴 P0: Emergency Cache Clear
```sql
-- Clear all cached responses immediately
DELETE FROM cached_responses;
DELETE FROM question_topics;
DELETE FROM question_entities;
DELETE FROM question_sources;
```

### 🔴 P1: Increase Semantic Similarity Threshold
Current threshold appears too low (~0.7?). Increase to 0.85+ to prevent false matches between "GI Bill" and "VR&E".

### 🔴 P2: Add Topic Disambiguation
When multiple topics are detected (e.g., "GI Bill" vs "VR&E" vs "CHAMPVA"), require exact topic match before returning cached response.

### 🔴 P3: Fix DC Code Pattern Matching
The "DC XXXX" pattern preprocessing may not be working. Verify and test:
```python
# Expected transformation:
"What is DC 7101?" → "What is Diagnostic Code 7101 hypertension?"
```

### 🟡 P4: Add Query Type Classification
Classify queries by type (definition, eligibility, rating, application) and require type match for cache hits.

### 🟡 P5: Separate Program Caches
Create separate cache namespaces for:
- GI Bill (Chapter 30, 33, 35, DEA)
- VR&E (Chapter 31)
- CHAMPVA
- Disability Ratings

---

## METRICS SUMMARY

| Metric | Value |
|--------|-------|
| Total Questions | 230 |
| API Success Rate | 100% |
| Correct Content Rate | ~40% |
| GI Bill Accuracy | 0% |
| CHAMPVA Accuracy | 15% |
| VR&E Accuracy | 40% |
| DC Code Lookups | 25% |
| Agent Orange Accuracy | 75% |
| 1151 Claims Accuracy | 90% |
| Protection Rules Accuracy | 80% |

---

## FILES FOR REVIEW

- `/Users/tyler/AI_project/test2/qa_test_results.md` - Full 230 Q&A pairs
- `/Users/tyler/AI_project/test2/qa_test_results.json` - Raw API responses
- `/Users/tyler/AI_project/test2/src/response_cache.py` - Caching logic
- `/Users/tyler/AI_project/test2/src/topic_graph.py` - Topic association logic
- `/Users/tyler/AI_project/test2/src/rag_pipeline.py` - Query preprocessing

---

## CONCLUSION

The RAG system has a **critical caching bug** that is returning cached responses for semantically similar but topically different queries. This results in:

1. **100% failure rate** for GI Bill questions
2. **80% failure rate** for CHAMPVA questions
3. **70% failure rate** for VR&E detail questions
4. **75% failure rate** for direct DC code lookups

**Immediate action required**: Clear all caches and increase semantic similarity threshold to prevent false positive cache hits.
