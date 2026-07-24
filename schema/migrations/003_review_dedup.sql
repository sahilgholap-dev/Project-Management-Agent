-- 003: review_queue.dedup_key — the stable identity of a RECURRING condition
-- (e.g. "off_track:schedule_variance"), so a persistent, still-unresolved
-- issue does not spawn a fresh Tier 1 item every monitoring cycle. Queue-level
-- mirror of the risk-register duplicate check. NULL = item never dedups
-- (one-shot items: clarifications tied to a specific report, slip_impact, ...).
ALTER TABLE review_queue ADD COLUMN dedup_key TEXT;

CREATE INDEX idx_review_queue_dedup
    ON review_queue (project_id, item_type, dedup_key);
