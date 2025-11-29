-- Topic Graph Setup for Veterans Benefits AI
-- Implements a simple graph structure: Questions ↔ Topics
-- For smart cache lookups with max 1 join

-- ============================================================
-- TOPICS TABLE (Nodes)
-- ============================================================
-- Predefined topic categories with keyword triggers
CREATE TABLE IF NOT EXISTS topics (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) UNIQUE NOT NULL,      -- e.g., 'disability_ratings'
    name VARCHAR(100) NOT NULL,             -- e.g., 'Disability Ratings'
    keywords TEXT[] NOT NULL DEFAULT '{}',  -- keyword triggers for matching
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for keyword array searches
CREATE INDEX IF NOT EXISTS idx_topics_slug ON topics(slug);

-- ============================================================
-- QUESTION_TOPICS TABLE (Edges)
-- ============================================================
-- Links cached questions to topic nodes (many-to-many)
CREATE TABLE IF NOT EXISTS question_topics (
    question_id INTEGER NOT NULL,           -- References cached_responses.id
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    confidence FLOAT DEFAULT 1.0,           -- How confident the topic match is
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (question_id, topic_id)
);

-- Index for fast topic-based lookups (the main query path)
CREATE INDEX IF NOT EXISTS idx_question_topics_topic ON question_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_question_topics_question ON question_topics(question_id);

-- ============================================================
-- SEED TOPICS FOR VETERANS BENEFITS
-- ============================================================
INSERT INTO topics (slug, name, keywords) VALUES
    ('disability_ratings', 'Disability Ratings', 
     ARRAY['disability', 'rating', 'percentage', 'combined rating', 'va rating', 'service connection', 'connected', 'rated', 'schedule', 'cfr']),
    
    ('healthcare', 'VA Healthcare', 
     ARRAY['healthcare', 'medical', 'hospital', 'doctor', 'enrollment', 'copay', 'health care', 'clinic', 'prescription', 'mental health', 'ptsd']),
    
    ('education', 'Education Benefits', 
     ARRAY['gi bill', 'education', 'school', 'college', 'tuition', 'voc rehab', 'vocational', 'training', 'chapter 33', 'post 9/11', 'montgomery']),
    
    ('compensation', 'Compensation & Pension', 
     ARRAY['compensation', 'pension', 'payment', 'back pay', 'retro', 'retroactive', 'monthly', 'special monthly', 'smc', 'tdiu', 'individual unemployability']),
    
    ('claims', 'Claims Process', 
     ARRAY['claim', 'appeal', 'decision', 'evidence', 'c&p exam', 'nexus', 'dbq', 'supplemental', 'higher level', 'bva', 'board', 'denial', 'denied', 'file']),
    
    ('housing', 'Housing & Home Loans', 
     ARRAY['home loan', 'va loan', 'housing', 'mortgage', 'coe', 'certificate of eligibility', 'refinance', 'irrrl', 'adapted housing', 'sah', 'sha']),
    
    ('employment', 'Employment', 
     ARRAY['employment', 'job', 'vrap', 'vocational', 'career', 'work', 'unemployability', 'hire', 'veteran preference']),
    
    ('survivors', 'Survivor Benefits', 
     ARRAY['survivor', 'dic', 'death', 'burial', 'spouse', 'dependent', 'widow', 'dependency indemnity', 'champva', 'beneficiary'])
ON CONFLICT (slug) DO UPDATE SET
    keywords = EXCLUDED.keywords,
    name = EXCLUDED.name;

-- ============================================================
-- VERIFY SETUP
-- ============================================================
SELECT 'Topics loaded:' as info, count(*) as count FROM topics;
SELECT slug, name, array_length(keywords, 1) as keyword_count FROM topics ORDER BY slug;

-- Example query: Find cached answers for questions about disability ratings
-- This is the single-join query the graph enables:
/*
SELECT DISTINCT cr.id, cr.query_text, cr.response, cr.created_at
FROM cached_responses cr
JOIN question_topics qt ON cr.id = qt.question_id
WHERE qt.topic_id IN (SELECT id FROM topics WHERE slug = 'disability_ratings')
  AND cr.expires_at > NOW()
ORDER BY cr.hit_count DESC, cr.created_at DESC
LIMIT 5;
*/

