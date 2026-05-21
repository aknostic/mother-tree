-- Mother Tree database schema
-- Applied via CNPG postInitTemplateSQL or manually via psql

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- === ORGANIZATION PROFILE ===
-- Automatically extracted identity of the organization using Mother Tree.
-- Acts as a lens for foundation and narrative extraction.

CREATE TABLE organization (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    element_type TEXT NOT NULL CHECK (element_type IN ('identity', 'change', 'audience', 'competitor_category')),
    content TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    source_count INTEGER DEFAULT 1,
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_organization_type ON organization(element_type);
CREATE TRIGGER organization_updated_at BEFORE UPDATE ON organization FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- === FOUNDATION LAYER (Seth: the change + worldview) ===

-- The Change — what we offer, the transformation
CREATE TABLE change (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    statement TEXT NOT NULL,
    context TEXT,
    source TEXT,
    confidence REAL DEFAULT 0.5,
    flagged BOOLEAN DEFAULT false,
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- The Worldview — what the audience believes, per persona
CREATE TABLE worldview (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id UUID,  -- references personas(id), added after personas table
    belief TEXT NOT NULL,
    pain TEXT,
    readiness_signal TEXT,
    source TEXT,
    confidence REAL DEFAULT 0.5,
    flagged BOOLEAN DEFAULT false,
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- === AUDIENCE LAYER ===

-- Companies
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    industry TEXT,
    market TEXT,
    regulatory_exposure TEXT[],
    employee_count INTEGER,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Contacts
CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    role TEXT,
    company_id UUID REFERENCES companies(id),
    linkedin TEXT,
    email TEXT,
    temperature TEXT DEFAULT 'cold' CHECK (temperature IN ('cold', 'warm', 'hot')),
    last_contact TIMESTAMPTZ,
    channels TEXT[],
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Add foreign key for worldview → personas (now that personas exists)
ALTER TABLE worldview ADD CONSTRAINT worldview_persona_fk FOREIGN KEY (persona_id) REFERENCES personas(id);
CREATE INDEX idx_worldview_persona ON worldview(persona_id);

-- === CONVERSATION LAYER (Mycorrhizal Method: live loop) ===

-- Signals
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    type TEXT,
    content TEXT NOT NULL,
    contact_id UUID REFERENCES contacts(id),
    company_id UUID REFERENCES companies(id),
    relevance REAL DEFAULT 0.0,
    status TEXT DEFAULT 'new' CHECK (status IN ('new', 'reviewed', 'acted_on', 'archived')),
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Interactions
CREATE TABLE interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES contacts(id) NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('call', 'email', 'meeting', 'event', 'linkedin', 'slack', 'other')),
    date TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary TEXT,
    source_role TEXT CHECK (source_role IN ('hunter', 'gatherer', 'farmer')),
    next_action TEXT,
    next_action_date DATE,
    anonymized BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- === NARRATIVE LAYER (Seth: the stories) ===

-- Insights (extracted from narrative sources — reframes for conversations)
CREATE TABLE insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category TEXT NOT NULL,
    reframe TEXT NOT NULL,
    evidence TEXT,
    stakeholder_lens JSONB DEFAULT '[]',
    trigger TEXT,
    next_step TEXT,
    freshness REAL DEFAULT 1.0,
    source TEXT,
    confidence REAL DEFAULT 0.5,
    flagged BOOLEAN DEFAULT false,
    embedding vector(3584),  -- bge-multilingual-gemma2 output dimension
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Personas (loaded from content sources)
CREATE TABLE personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    profile TEXT,
    fears TEXT,
    motivation TEXT,
    trigger TEXT,
    communication TEXT,
    decision_criteria JSONB DEFAULT '[]',
    objections JSONB DEFAULT '[]',
    how_to_reach TEXT,
    source TEXT,
    confidence REAL DEFAULT 0.5,
    flagged BOOLEAN DEFAULT false,
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Case studies (loaded from content sources)
CREATE TABLE case_studies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    industry TEXT,
    challenge TEXT,
    approach TEXT,
    outcome TEXT,
    relevant_personas TEXT[],
    relevant_insights TEXT[],
    source TEXT,
    confidence REAL DEFAULT 0.5,
    flagged BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Competitors (loaded from content sources)
CREATE TABLE competitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL,
    positioning TEXT,
    when_mentioned TEXT,
    response TEXT,
    source TEXT,
    confidence REAL DEFAULT 0.5,
    flagged BOOLEAN DEFAULT false,
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Proof points (specific outcomes from client work — extracted from narrative sources)
CREATE TABLE proof_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client TEXT,
    outcome TEXT NOT NULL,
    duration TEXT,
    relevance TEXT,
    source TEXT,
    confidence REAL DEFAULT 0.5,
    embedding vector(3584),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_proof_points_confidence ON proof_points(confidence);
GRANT ALL ON TABLE proof_points TO mothertree;

-- === LIFECYCLE LAYER (Opportunity → Engagement) ===

-- Engagements: the full delivery lifecycle (assess, build, operate)
CREATE TABLE engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    type TEXT NOT NULL CHECK (type IN ('assess', 'build', 'operate')),
    status TEXT DEFAULT 'active' CHECK (status IN ('planned', 'active', 'completed', 'paused')),
    title TEXT,
    start_date DATE,
    end_date DATE,
    parent_id UUID REFERENCES engagements(id),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Opportunities: the sales funnel (soil through proposal)
CREATE TABLE opportunities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    contact_id UUID REFERENCES contacts(id),
    stage TEXT DEFAULT 'signal' CHECK (stage IN ('soil', 'signal', 'reframe', 'diagnosis', 'proposal', 'converted')),
    engagement_id UUID REFERENCES engagements(id),
    title TEXT,
    notes TEXT,
    next_action TEXT,
    next_action_date DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Events: where relationships happen
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    type TEXT CHECK (type IN ('conference', 'meetup', 'webinar', 'office_hours', 'talk', 'other')),
    date DATE,
    location TEXT,
    url TEXT,
    notes TEXT,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Event participants
CREATE TABLE event_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID REFERENCES events(id) NOT NULL,
    contact_id UUID REFERENCES contacts(id) NOT NULL,
    role TEXT CHECK (role IN ('attending', 'speaking', 'organizing', 'prospect')),
    notes TEXT
);

-- === OPERATIONAL LAYER ===

-- Patterns (accumulated over time)
CREATE TABLE patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    frequency INTEGER DEFAULT 1,
    source_count INTEGER DEFAULT 1,
    last_seen TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- === USER IDENTITY ===
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL CHECK (email = lower(email)),
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('hunter', 'gatherer', 'farmer', 'citizen')),
    current_stage INTEGER DEFAULT 0,
    current_chapter INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_activity TIMESTAMPTZ,
    calendar_url TEXT,
    phone TEXT,
    working_days TEXT[],
    enrolled_at TIMESTAMPTZ DEFAULT now(),
    active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL CHECK (email = lower(email)),
    granted_by TEXT NOT NULL,
    granted_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS channel_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL DEFAULT 'slack',
    channel_user_id TEXT NOT NULL,
    linked_at TIMESTAMPTZ DEFAULT now(),
    -- A user has at most one link per channel type, and any given external
    -- channel_user_id maps to at most one user. Without the first constraint
    -- a stale row could shadow the correct link and DM the wrong person.
    CONSTRAINT channel_links_user_channeltype_unique UNIQUE (user_id, channel_type),
    UNIQUE (channel_type, channel_user_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_links_lookup ON channel_links(channel_type, channel_user_id);

-- Training progress (per user)
CREATE TABLE training_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    area TEXT NOT NULL,
    last_refresher TIMESTAMPTZ,
    score REAL DEFAULT 0.0,
    streak INTEGER DEFAULT 0,
    weak_spots TEXT[],
    exercises_completed INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, area)
);

-- Training exercises
CREATE TABLE exercises (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    stage INTEGER NOT NULL,
    chapter INTEGER,
    exercise_type TEXT NOT NULL CHECK (exercise_type IN
        ('instruction', 'multiple_choice', 'practice', 'open', 'scenario', 'prep')),
    content JSONB NOT NULL,
    source_tables TEXT[],
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Training responses (one row per question)
CREATE TABLE responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exercise_id UUID REFERENCES exercises(id),
    user_id UUID REFERENCES users(id),
    response TEXT NOT NULL,
    question_index INTEGER NOT NULL,
    correct BOOLEAN,
    scores JSONB,
    confidence REAL,
    feedback TEXT,
    responded_at TIMESTAMPTZ DEFAULT now()
);

-- Training conversation state (tracks DM flow)
-- stage = -1 is reserved for freeform DM conversations (user_id may be NULL for unenrolled users)
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    exercise_id UUID REFERENCES exercises(id),
    stage INTEGER NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active', 'waiting_response', 'complete')),
    current_question INTEGER DEFAULT -1,
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_contacts_company ON contacts(company_id);
CREATE INDEX idx_contacts_temperature ON contacts(temperature);
CREATE INDEX idx_signals_status ON signals(status);
CREATE INDEX idx_signals_created ON signals(created_at);
CREATE INDEX idx_interactions_contact ON interactions(contact_id);
CREATE INDEX idx_interactions_date ON interactions(date);
CREATE INDEX idx_interactions_next_action ON interactions(next_action_date) WHERE next_action_date IS NOT NULL;
CREATE INDEX idx_insights_category ON insights(category);
CREATE INDEX idx_engagements_company ON engagements(company_id);
CREATE INDEX idx_engagements_status ON engagements(status);
CREATE INDEX idx_opportunities_company ON opportunities(company_id);
CREATE INDEX idx_opportunities_stage ON opportunities(stage);
CREATE INDEX idx_signals_opportunity ON signals(opportunity_id);
CREATE INDEX idx_interactions_opportunity ON interactions(opportunity_id);
CREATE INDEX idx_event_participants_event ON event_participants(event_id);
CREATE INDEX idx_event_participants_contact ON event_participants(contact_id);
CREATE INDEX idx_training_progress_user ON training_progress(user_id);

-- Training indexes
CREATE INDEX idx_exercises_user_id ON exercises(user_id);
CREATE INDEX idx_responses_exercise_id ON responses(exercise_id);
CREATE INDEX idx_responses_user_id ON responses(user_id);
CREATE INDEX idx_conversations_user_state ON conversations(user_id, state);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER change_updated_at BEFORE UPDATE ON change FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER contacts_updated_at BEFORE UPDATE ON contacts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER companies_updated_at BEFORE UPDATE ON companies FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER signals_updated_at BEFORE UPDATE ON signals FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER insights_updated_at BEFORE UPDATE ON insights FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER engagements_updated_at BEFORE UPDATE ON engagements FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER opportunities_updated_at BEFORE UPDATE ON opportunities FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER training_progress_updated_at BEFORE UPDATE ON training_progress FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER set_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Channel conversation memory (top-level messages, capped at ~200)
CREATE TABLE channel_memory (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL UNIQUE,
    channel_name TEXT,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Thread conversation memory (per-thread, capped at ~100 with summarization)
CREATE TABLE thread_memory (
    id SERIAL PRIMARY KEY,
    thread_ts TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    remind_after TIMESTAMPTZ,
    remind_context TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER channel_memory_updated_at BEFORE UPDATE ON channel_memory FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER thread_memory_updated_at BEFORE UPDATE ON thread_memory FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- === PULSE: Ownership tracking ===
ALTER TABLE thread_memory ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE interactions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);

-- === PULSE: Nudge state ===
ALTER TABLE thread_memory ADD COLUMN IF NOT EXISTS pulse_nudged_at TIMESTAMPTZ;
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS pulse_nudged_at TIMESTAMPTZ;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS pulse_nudged_at TIMESTAMPTZ;

-- === PULSE: Indexes ===
CREATE INDEX IF NOT EXISTS idx_thread_memory_remind_after
    ON thread_memory(remind_after) WHERE remind_after IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_thread_memory_pulse_nudged
    ON thread_memory(pulse_nudged_at);
CREATE INDEX IF NOT EXISTS idx_thread_memory_owner ON thread_memory(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_owner
    ON opportunities(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_pulse_nudged
    ON opportunities(pulse_nudged_at);
CREATE INDEX IF NOT EXISTS idx_contacts_owner
    ON contacts(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_contacts_pulse_nudged
    ON contacts(pulse_nudged_at);

-- === CLIENT ACCOUNT MANAGEMENT ===
ALTER TABLE companies ADD COLUMN IF NOT EXISTS client_since DATE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS contract_value TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS services TEXT[];
ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS pulse_nudged_at TIMESTAMPTZ;

ALTER TABLE engagements ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(id);
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS next_service_meeting DATE;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS last_service_meeting TIMESTAMPTZ;
ALTER TABLE engagements ADD COLUMN IF NOT EXISTS service_meeting_notes TEXT;

-- === ENROLLMENT APPROVAL ===
CREATE TABLE IF NOT EXISTS enrollment_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    requested_role TEXT NOT NULL CHECK (requested_role IN ('hunter', 'gatherer', 'farmer')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    approved_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_enrollment_requests_status
    ON enrollment_requests(status) WHERE status = 'pending';

-- === ACCOUNT PLANS ===
CREATE TABLE IF NOT EXISTS account_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) UNIQUE,
    white_space TEXT,
    expansion_triggers TEXT[],
    strategy TEXT,
    qbr_notes TEXT,
    qbr_at TIMESTAMPTZ,
    next_qbr DATE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_account_plans_company ON account_plans(company_id);
CREATE INDEX IF NOT EXISTS idx_account_plans_next_qbr ON account_plans(next_qbr) WHERE next_qbr IS NOT NULL;
CREATE TRIGGER account_plans_updated_at BEFORE UPDATE ON account_plans FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- === REMINDERS ===
CREATE TABLE IF NOT EXISTS reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_user_id UUID NOT NULL REFERENCES users(id),
    target_user_id UUID NOT NULL REFERENCES users(id),
    remind_at TIMESTAMPTZ NOT NULL,
    context TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'cancelled')),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reminders_due
    ON reminders(remind_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_reminders_target
    ON reminders(target_user_id) WHERE status = 'pending';

-- === HANDBOOK DELIVERY TRACKING ===
CREATE TABLE IF NOT EXISTS help_delivered (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    help_key TEXT NOT NULL,
    delivered_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, help_key)
);

-- === DEBRIEF PENDING STATE ===
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_debrief JSONB;

-- === USER SNOOZE ===
ALTER TABLE users ADD COLUMN IF NOT EXISTS snoozed_until TIMESTAMPTZ;

-- === INGESTION LOG ===
-- Tracks content hashes to skip unchanged documents on re-ingestion.
-- Primary key is source (URL or path), not UUID.

CREATE TABLE IF NOT EXISTS ingestion_log (
    source TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT now(),
    record_counts JSON
);

-- === SIGNAL THREADS ===
-- Tracks signal-related Slack threads for follow-up and enrichment.

CREATE TABLE IF NOT EXISTS signal_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID REFERENCES signals(id),
    slack_thread_ts TEXT NOT NULL UNIQUE,
    slack_channel TEXT NOT NULL,
    messages JSON,
    enrichment JSON,
    status TEXT DEFAULT 'active',
    remind_after TIMESTAMPTZ,
    remind_context TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signal_threads_slack_ts ON signal_threads(slack_thread_ts);
CREATE INDEX IF NOT EXISTS idx_signal_threads_remind ON signal_threads(remind_after) WHERE remind_after IS NOT NULL;
CREATE TRIGGER signal_threads_updated_at BEFORE UPDATE ON signal_threads FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- === STORED PROCEDURES ===

CREATE OR REPLACE FUNCTION append_conversation_message(p_conversation_id UUID, p_message JSONB)
RETURNS conversations AS $$
UPDATE conversations
SET messages = messages || p_message,
    updated_at = now()
WHERE id = p_conversation_id
RETURNING *;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION upsert_training_progress_fn(p_user_id UUID, p_area TEXT, p_score REAL, p_last_refresher TIMESTAMPTZ DEFAULT NULL)
RETURNS training_progress AS $$
INSERT INTO training_progress (user_id, area, score, last_refresher)
VALUES (p_user_id, p_area, p_score, p_last_refresher)
ON CONFLICT (user_id, area) DO UPDATE
SET score = EXCLUDED.score,
    last_refresher = COALESCE(EXCLUDED.last_refresher, training_progress.last_refresher),
    exercises_completed = training_progress.exercises_completed + 1,
    updated_at = now()
RETURNING *;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION upsert_ingestion_log(p_source TEXT, p_hash TEXT, p_counts JSON)
RETURNS ingestion_log AS $$
INSERT INTO ingestion_log (source, content_hash, record_counts, ingested_at)
VALUES (p_source, p_hash, p_counts, now())
ON CONFLICT (source) DO UPDATE
SET content_hash = EXCLUDED.content_hash,
    record_counts = EXCLUDED.record_counts,
    ingested_at = now()
RETURNING *;
$$ LANGUAGE sql;

