# QA Test Analysis Report - December 7, 2025

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Questions** | 348 |
| **Success Rate** | 347/348 (99.7%) |
| **Average Confidence** | 59.8% |
| **No Information Found** | 13 questions |
| **Low Confidence (<50%)** | 22 questions |
| **Partial Answers** | 15 questions |

## Performance By Category

### 🟢 Strong Categories (>60% confidence)
| Category | Avg Confidence | Questions |
|----------|---------------|-----------|
| CHAMPVA | 72.56% | 15 |
| GIBILL | 70.85% | 20 |
| LEJEUNE | 69.36% | 8 |
| YELLOW | 67.71% | 6 |
| BUDDY | 67.69% | 10 |
| VRE | 66.87% | 15 |
| MONEY | 65.29% | 6 |
| PACT | 65.02% | 10 |
| PT | 64.16% | 8 |
| DTA | 61.98% | 6 |
| PRESUMPTIVE | 61.53% | 15 |
| PENSION | 60.26% | 8 |
| PHYSICAL | 60.25% | 20 |
| APPEAL | 60.11% | 20 |

### 🟡 Moderate Categories (50-60% confidence)
| Category | Avg Confidence | Questions | Issues |
|----------|---------------|-----------|--------|
| STRESSOR | 58.96% | 6 | 1 low conf |
| DEPENDENTS | 58.79% | 10 | 1 no info |
| SMC | 57.90% | 8 | 2 low conf |
| EDGE | 57.55% | 20 | 2 low conf |
| RATING | 57.18% | 25 | 2 low conf, 1 no info |
| MENTAL | 57.13% | 26 | 1 low conf |
| CLAIMS | 57.04% | 25 | 2 low conf, 1 no info |
| SECONDARY | 56.85% | 15 | 2 low conf |
| BURN | 56.38% | 8 | 1 low conf |
| NEHMER | 56.13% | 6 | 2 low conf |

### 🔴 Weak Categories (<55% confidence)
| Category | Avg Confidence | Questions | Issues |
|----------|---------------|-----------|--------|
| AO | 50.21% | 10 | 1 low conf, 2 no info |
| MATH | 49.20% | 6 | 1 no info |
| 1151 | 47.99% | 10 | 1 low conf, 2 no info |
| **BWN** | **17.77%** | 6 | **4 no info** |

---

## Critical Issues: Questions With No Answers (13)

These questions returned "I couldn't find any relevant information":

### 🔴 Blue Water Navy (BWN) - 4 questions (CRITICAL)
1. What is Blue Water Navy?
2. What dates does Blue Water Navy cover?
3. How far offshore counts as Blue Water Navy?
4. What is Public Law 116-23?

**Root Cause:** The Blue Water Navy content chunks are not being retrieved properly. Need to verify:
- Chunk entry_ids and aliases
- Content was properly chunked from `blue_water.md`

### 🔴 Agent Orange (AO) - 2 questions
1. What is Blue Water Navy? (duplicate topic)
2. What is herbicide exposure?

### 🔴 1151 Claims - 2 questions
1. What is the difference between 1151 and tort?
2. What evidence do I need for 1151?

### 🔴 Other Categories - 5 questions
- **CLAIMS:** What is the difference between direct and secondary service connection?
- **RATING:** Can I get retro pay?
- **VRE:** What is the subsistence allowance?
- **DEPENDENTS:** What is a helpless child?
- **MATH:** What is the total person concept?

---

## Low Confidence Questions (<50%) - 22 Questions

### Appeals & Claims Process
- What is a fully developed claim? (49.82%)
- What if my medical records were lost? (46.07%)
- What is a Notice of Disagreement? (48.87%)
- What is a Board hearing? (48.90%)
- What is a Statement of the Case? (48.88%)

### Ratings & Protection
- What is a protected rating? (48.27%)
- What is the 5 year rule? (47.36%)

### Mental Health
- What is a stressor statement? (47.66%)

### Secondary Conditions
- Can depression be secondary to chronic pain? (45.09%)
- Is GERD secondary to PTSD medication? (47.16%)

### Other Topics
- What is the 1 year presumptive period? (47.33%)
- What is the statute of limitations for tort claims? (46.82%)
- What is the Nehmer rule? (48.57%)
- What is the difference between SMC and SMP? (45.16%)
- What if I can't remember my stressor? (47.97%)
- Can I file a claim without medical records? (49.90%)
- What is 38 CFR 3.816? (47.73%)
- Do I need to join the burn pit registry? (47.09%)
- What is SMC-K? (49.58%)
- Can I get multiple SMC-K awards? (49.73%)
- What is military sexual trauma (MST)? (49.80%)

---

## Recommended Actions

### Immediate (High Priority)

1. **Fix Blue Water Navy Content Retrieval**
   - Verify `blue_water.md` was properly chunked
   - Check chunk aliases include: "blue water navy", "BWN", "public law 116-23", "territorial waters"
   - Ensure entry_ids are correct in corpus

2. **Add Missing Content:**
   - Direct vs Secondary service connection (comparison article)
   - Retro pay / back pay explanation
   - VR&E subsistence allowance details
   - Helpless child dependency information
   - Total person concept (VA math)
   - 1151 evidence requirements
   - Difference between 1151 and federal tort claims

### Short-term (1-2 weeks)

3. **Improve Low-Confidence Categories:**
   - Review and enhance MATH content
   - Add more specific 1151 content
   - Improve AO/herbicide exposure content
   - Add more aliases to chunks in weak categories

4. **Content Enhancements:**
   - Add "fully developed claim" explanation
   - Add Statement of the Case details
   - Add Board hearing procedures
   - Add 5/10/20 year protection rules in one focused article

### Ongoing

5. **Monitor Progress:**
   - Run QA tests weekly
   - Target: 65%+ average confidence
   - Target: 0 "no information found" responses

---

## Corpus Statistics

- **Total Chunks:** 1,468
- **Chunk Size:** All chunks <2,000 tokens (fixed from 13k+ token issues)
- **Deployment:** Successfully deployed to Render
- **Last Test:** December 7, 2025 09:08 UTC

---

## Test Categories Breakdown

| Category | Description | Questions |
|----------|-------------|-----------|
| CLAIMS | Filing claims | 25 |
| MENTAL | Mental health ratings | 26 |
| RATING | Rating decisions | 25 |
| APPEAL | Appeals process | 20 |
| PHYSICAL | Physical conditions | 20 |
| GIBILL | Education benefits | 20 |
| EDGE | Edge cases | 20 |
| SECONDARY | Secondary conditions | 15 |
| PRESUMPTIVE | Presumptive conditions | 15 |
| CHAMPVA | CHAMPVA healthcare | 15 |
| VRE | Voc Rehab | 15 |
| 1151 | VA negligence claims | 10 |
| AO | Agent Orange | 10 |
| DEPENDENTS | Dependent benefits | 10 |
| BUDDY | Buddy statements | 10 |
| PACT | PACT Act | 10 |
| PENSION | Pension benefits | 8 |
| PT | P&T status | 8 |
| LEJEUNE | Camp Lejeune | 8 |
| SMC | Special Monthly Comp | 8 |
| BURN | Burn pit exposure | 8 |
| MATH | VA math | 6 |
| MONEY | Pay and backpay | 6 |
| BWN | Blue Water Navy | 6 |
| NEHMER | Nehmer rules | 6 |
| DTA | Duty to Assist | 6 |
| STRESSOR | PTSD stressors | 6 |
| YELLOW | Yellow Ribbon | 6 |

---

*Report generated: December 7, 2025*

