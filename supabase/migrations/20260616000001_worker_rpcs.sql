-- Atomic Job Claiming RPCs

-- claim_webhook_event: Atomically claim one pending webhook event
CREATE OR REPLACE FUNCTION claim_webhook_event()
RETURNS SETOF webhook_events
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    UPDATE webhook_events
    SET status = 'processing',
        processed_at = now()
    WHERE id = (
        SELECT id
        FROM webhook_events
        WHERE status = 'pending'
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;

-- claim_outbox_job: Atomically claim one pending outbox job
CREATE OR REPLACE FUNCTION claim_outbox_job()
RETURNS SETOF outbox_jobs
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    UPDATE outbox_jobs
    SET status = 'processing',
        attempts = attempts + 1,
        processed_at = now()
    WHERE id = (
        SELECT id
        FROM outbox_jobs
        WHERE status = 'pending'
        AND attempts < max_attempts
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$;
