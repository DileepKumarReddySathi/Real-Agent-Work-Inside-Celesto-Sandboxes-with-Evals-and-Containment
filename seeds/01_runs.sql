-- Schema for the Run Ledger
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR(255) PRIMARY KEY,
    sandbox_name VARCHAR(255) NOT NULL,
    problem_id VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL,
    execution_target VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Seed row required by the specification:
-- Sandbox name: sbx-seeddemo1, state: deleted, execution target: celesto_sandbox
-- Idempotent insert: re-running does not duplicate
INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
VALUES ('run-seeddemo001', 'sbx-seeddemo1', 'detonator-baseline', 'deleted', 'celesto_sandbox')
ON CONFLICT (run_id) DO NOTHING;
