import json
import os
import re
import pytest
from math import ceil
from datetime import datetime
from fastapi.testclient import TestClient
from src.api import app

SANDBOX_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")
ALLOWED_CAPABILITIES = {
    "persistence",
    "snapshots",
    "celestofs",
    "browser",
    "published_ports",
    "network_policy",
    "safety_hooks",
    "host_mounts",
    "coding_agent_preset",
    "agentor_durable",
}
ALLOWED_ATTACKS = {
    "prompt_injection_exfil",
    "destructive_command",
    "suspicious_package",
}
ALLOWED_POLICIES = {"resume", "rollback", "fresh"}


def test_core_req_1_docker_compose_and_dockerfile():
    """Verify docker-compose.yml and Dockerfile specifications."""
    assert os.path.isfile("docker-compose.yml"), "docker-compose.yml missing"
    assert os.path.isfile("Dockerfile"), "Dockerfile missing"

    with open("docker-compose.yml", "r", encoding="utf-8") as f:
        content = f.read()

    # Verify services exist
    assert "api:" in content, "Service 'api' missing in docker-compose.yml"
    assert "ledger:" in content, "Service 'ledger' missing in docker-compose.yml"
    assert "8080" in content, "Port 8080 missing in docker-compose.yml"
    assert "seeds" in content, "seeds mount missing in ledger service"
    assert "pg_isready" in content, "pg_isready healthcheck missing in ledger"
    assert "/health" in content, "healthcheck probe missing in api"

    # Check healthcheck attributes
    for kw in ["interval:", "timeout:", "retries:", "start_period:"]:
        assert kw in content, f"Healthcheck attribute '{kw}' missing in docker-compose.yml"


def test_core_req_2_env_example():
    """Verify .env.example exists, .env does not, and required keys are present with placeholders."""
    assert os.path.isfile(".env.example"), ".env.example missing at repository root"
    assert not os.path.isfile(".env"), ".env file MUST NOT be present at repository root"

    required_keys = [
        "CELESTO_PROVIDER",
        "CELESTO_API_KEY",
        "LLM_API_KEY",
        "LLM_MODEL",
        "DATABASE_URL",
        "API_PORT",
    ]
    with open(".env.example", "r", encoding="utf-8") as f:
        env_content = f.read()

    for key in required_keys:
        assert re.search(rf"^{key}=", env_content, re.MULTILINE), f"Missing key {key} in .env.example"
        # Confirm placeholder
        val_match = re.search(rf"^{key}=(.*)$", env_content, re.MULTILINE)
        assert val_match, f"Could not extract value for {key}"
        val = val_match.group(1).strip()
        assert not val.startswith("sk-"), f"Live secret detected for {key} in .env.example"


def test_core_req_3_problem_statement():
    """Verify reports/problem.json schema and string length requirements."""
    path = "reports/problem.json"
    assert os.path.isfile(path), f"{path} missing"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for field in ["who", "agent_work", "proof_output", "idea_source"]:
        assert field in data, f"Field '{field}' missing from {path}"

    assert data["idea_source"] in ["idea_bank", "original"], "idea_source must be idea_bank or original"
    assert len(data["who"]) >= 40, f"'who' must be >= 40 chars, got {len(data['who'])}"
    assert len(data["agent_work"]) >= 40, f"'agent_work' must be >= 40 chars, got {len(data['agent_work'])}"
    assert len(data["proof_output"]) >= 20, f"'proof_output' must be >= 20 chars, got {len(data['proof_output'])}"


def test_core_req_4_command_audit_log():
    """Verify logs/commands.jsonl format and execution target."""
    path = "logs/commands.jsonl"
    assert os.path.isfile(path), f"{path} missing"

    line_count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line_count += 1
            entry = json.loads(line)
            assert "ts" in entry and entry["ts"], "ts missing or empty"
            assert SANDBOX_REGEX.match(entry["sandbox_name"]), f"Invalid sandbox_name: {entry.get('sandbox_name')}"
            assert isinstance(entry["command"], str) and len(entry["command"]) > 0, "command must be non-empty"
            assert entry["decision"] in ["allow", "block"], f"decision must be allow or block, got {entry.get('decision')}"
            assert entry["execution_target"] == "celesto_sandbox", f"execution_target must be exactly celesto_sandbox, got {entry.get('execution_target')}"

    assert line_count >= 1, "logs/commands.jsonl must have at least one line"


def test_core_req_5_capabilities():
    """Verify reports/capabilities.json requirements."""
    path = "reports/capabilities.json"
    assert os.path.isfile(path), f"{path} missing"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "capabilities" in data and isinstance(data["capabilities"], list), "capabilities array missing"
    caps = data["capabilities"]
    assert len(caps) >= 2, f"Expected at least 2 capabilities, got {len(caps)}"

    seen_ids = set()
    for cap in caps:
        cap_id = cap.get("id")
        assert cap_id in ALLOWED_CAPABILITIES, f"Invalid capability id '{cap_id}'"
        assert cap_id not in seen_ids, f"Duplicate capability id '{cap_id}'"
        seen_ids.add(cap_id)

        why = cap.get("why", "")
        assert len(why) >= 80, f"Capability {cap_id} 'why' must be >= 80 chars, got {len(why)}"

        evidence_path = cap.get("evidence_path", "")
        assert os.path.exists(evidence_path), f"Evidence path '{evidence_path}' does not exist"


def test_core_req_6_lifecycle():
    """Verify reports/lifecycle.json requirements."""
    path = "reports/lifecycle.json"
    assert os.path.isfile(path), f"{path} missing"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("cleanup_on_success") is True, "cleanup_on_success must be true"
    assert data.get("cleanup_on_failure") is True, "cleanup_on_failure must be true"
    assert data.get("cleanup_on_interrupt") is True, "cleanup_on_interrupt must be true"

    sandbox_names = data.get("sandbox_names", [])
    assert isinstance(sandbox_names, list) and len(sandbox_names) > 0, "sandbox_names must be non-empty list"
    assert len(sandbox_names) == len(set(sandbox_names)), "sandbox_names must be unique"

    # Gather names from commands.jsonl and reliability.json
    known_names = set()
    if os.path.isfile("logs/commands.jsonl"):
        with open("logs/commands.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    known_names.add(json.loads(line)["sandbox_name"])
    if os.path.isfile("reports/reliability.json"):
        with open("reports/reliability.json", "r", encoding="utf-8") as f:
            rel = json.load(f)
            for r in rel.get("runs", []):
                known_names.add(r["sandbox_name"])

    for name in sandbox_names:
        assert SANDBOX_REGEX.match(name), f"Invalid sandbox name format: {name}"
        assert name in known_names, f"Sandbox {name} not found in commands.jsonl or reliability.json"


def test_core_req_7_reliability():
    """Verify reports/reliability.json math and reports/postmortem.md."""
    path = "reports/reliability.json"
    assert os.path.isfile(path), f"{path} missing"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    run_count = data.get("run_count")
    assert run_count >= 20, f"run_count must be >= 20, got {run_count}"
    assert run_count == len(runs), f"run_count {run_count} != len(runs) {len(runs)}"

    seen_names = set()
    for r in runs:
        sname = r.get("sandbox_name")
        assert SANDBOX_REGEX.match(sname), f"Invalid sandbox name: {sname}"
        assert sname not in seen_names, f"Duplicate sandbox name in runs: {sname}"
        seen_names.add(sname)

        assert r.get("fresh") is True, f"fresh must be true for {sname}"
        assert isinstance(r.get("success"), bool), f"success must be boolean for {sname}"
        assert r.get("wall_clock_s") >= 0, f"wall_clock_s must be >= 0 for {sname}"
        assert r.get("boot_to_ready_s") >= 0, f"boot_to_ready_s must be >= 0 for {sname}"
        assert r.get("cost_usd") >= 0, f"cost_usd must be >= 0 for {sname}"

    # Recompute statistics
    expected_success_rate = sum(1 for r in runs if r["success"]) / run_count
    assert abs(data["success_rate"] - expected_success_rate) <= 0.001, (
        f"success_rate mismatch: got {data['success_rate']}, expected {expected_success_rate}"
    )

    # Median wall clock
    sorted_wall = sorted(r["wall_clock_s"] for r in runs)
    n = len(sorted_wall)
    if n % 2 == 0:
        expected_median_wall = (sorted_wall[(n // 2) - 1] + sorted_wall[n // 2]) / 2.0
    else:
        expected_median_wall = sorted_wall[n // 2]
    assert abs(data["median_wall_clock_s"] - expected_median_wall) <= 0.001, (
        f"median_wall_clock_s mismatch: got {data['median_wall_clock_s']}, expected {expected_median_wall}"
    )

    # P90 wall clock: rank ceil(0.90 * n), 1-based index
    p90_idx = ceil(0.90 * n) - 1
    expected_p90_wall = sorted_wall[p90_idx]
    assert abs(data["p90_wall_clock_s"] - expected_p90_wall) <= 0.001, (
        f"p90_wall_clock_s mismatch: got {data['p90_wall_clock_s']}, expected {expected_p90_wall}"
    )

    # Median boot to ready
    sorted_boot = sorted(r["boot_to_ready_s"] for r in runs)
    if n % 2 == 0:
        expected_median_boot = (sorted_boot[(n // 2) - 1] + sorted_boot[n // 2]) / 2.0
    else:
        expected_median_boot = sorted_boot[n // 2]
    assert abs(data["median_boot_to_ready_s"] - expected_median_boot) <= 0.001, (
        f"median_boot_to_ready_s mismatch: got {data['median_boot_to_ready_s']}, expected {expected_median_boot}"
    )

    # Total cost
    expected_total_cost = sum(r["cost_usd"] for r in runs)
    assert abs(data["total_cost_usd"] - expected_total_cost) <= 0.01, (
        f"total_cost_usd mismatch: got {data['total_cost_usd']}, expected {expected_total_cost}"
    )

    # Postmortem path
    pm_path = data.get("postmortem_path")
    assert pm_path == "reports/postmortem.md", f"postmortem_path must be reports/postmortem.md, got {pm_path}"
    assert os.path.isfile(pm_path), f"File {pm_path} missing"
    with open(pm_path, "r", encoding="utf-8") as f:
        pm_content = f.read()
    assert len(pm_content) >= 200, f"Postmortem must be >= 200 chars, got {len(pm_content)}"


def test_core_req_8_containment():
    """Verify reports/containment.json requirements."""
    path = "reports/containment.json"
    assert os.path.isfile(path), f"{path} missing"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("attack") in ALLOWED_ATTACKS, f"Invalid attack '{data.get('attack')}'"
    assert data.get("blocked") is True, "blocked must be true"
    assert data.get("host_untouched") is True, "host_untouched must be true"

    evidence_paths = data.get("evidence_paths", [])
    assert isinstance(evidence_paths, list) and len(evidence_paths) >= 1, "evidence_paths must have >= 1 path"
    for ep in evidence_paths:
        assert os.path.isfile(ep), f"Evidence path '{ep}' does not exist"


def test_core_req_9_failure_policy():
    """Verify reports/failure_policy.json and reports/failure_trace.jsonl."""
    path = "reports/failure_policy.json"
    assert os.path.isfile(path), f"{path} missing"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("failed_step") == 7, "failed_step must be 7"
    assert data.get("total_steps") == 10, "total_steps must be 10"
    policy = data.get("policy")
    assert policy in ALLOWED_POLICIES, f"policy must be one of {ALLOWED_POLICIES}, got {policy}"
    assert len(data.get("rationale", "")) >= 200, "rationale must be >= 200 chars"

    trace_path = data.get("trace_path")
    assert trace_path == "reports/failure_trace.jsonl", f"trace_path must be reports/failure_trace.jsonl, got {trace_path}"
    assert os.path.isfile(trace_path), f"{trace_path} missing"

    found_policy_applied = False
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("event") == "policy_applied" and entry.get("policy") == policy:
                found_policy_applied = True
                break

    assert found_policy_applied, f"No event 'policy_applied' with policy '{policy}' found in {trace_path}"


def test_core_req_10_concurrency():
    """Verify reports/concurrency.json requirements."""
    path = "reports/concurrency.json"
    assert os.path.isfile(path), f"{path} missing"

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    jobs = data.get("jobs", [])
    assert isinstance(jobs, list) and len(jobs) >= 5, f"jobs must have >= 5 items, got {len(jobs)}"

    seen_names = set()
    for job in jobs:
        sname = job.get("sandbox_name")
        assert SANDBOX_REGEX.match(sname), f"Invalid sandbox_name: {sname}"
        assert sname not in seen_names, f"Duplicate sandbox_name in jobs: {sname}"
        seen_names.add(sname)
        assert isinstance(job.get("started_at"), str) and len(job.get("started_at")) > 0, "started_at must be non-empty"

    assert len(data.get("breakage_notes", "")) >= 40, "breakage_notes must be >= 40 chars"


def test_core_req_11_ledger_api_endpoints():
    """Verify GET /health, GET /api/runs, and POST /api/runs responses."""
    client = TestClient(app)

    # 1. GET /health
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "ok"}

    # 2. GET /api/runs includes sbx-seeddemo1
    res_runs = client.get("/api/runs")
    assert res_runs.status_code == 200
    runs = res_runs.json()
    assert isinstance(runs, list)
    sandbox_names = [r["sandbox_name"] for r in runs]
    assert "sbx-seeddemo1" in sandbox_names, "sbx-seeddemo1 missing from GET /api/runs"

    # 3. POST /api/runs with valid payload -> 201
    valid_payload = {
        "run_id": "run-test-valid-01",
        "sandbox_name": "sbx-testalpha01",
        "problem_id": "prob-detonator",
        "state": "created",
        "execution_target": "celesto_sandbox"
    }
    res_post = client.post("/api/runs", json=valid_payload)
    assert res_post.status_code == 201
    created = res_post.json()
    assert created["sandbox_name"] == "sbx-testalpha01"
    assert created["execution_target"] == "celesto_sandbox"

    # 4. POST /api/runs with execution_target == 'host' -> 400
    bad_target_payload = {
        "run_id": "run-test-bad-target",
        "sandbox_name": "sbx-testalpha02",
        "problem_id": "prob-detonator",
        "state": "created",
        "execution_target": "host"
    }
    res_bad_target = client.post("/api/runs", json=bad_target_payload)
    assert res_bad_target.status_code == 400, f"Expected 400 for bad target, got {res_bad_target.status_code}"

    # 5. POST /api/runs with invalid state -> 400
    bad_state_payload = {
        "run_id": "run-test-bad-state",
        "sandbox_name": "sbx-testalpha03",
        "problem_id": "prob-detonator",
        "state": "unknown_state",
        "execution_target": "celesto_sandbox"
    }
    res_bad_state = client.post("/api/runs", json=bad_state_payload)
    assert res_bad_state.status_code == 400, f"Expected 400 for bad state, got {res_bad_state.status_code}"

    # 6. POST /api/runs with invalid sandbox name format -> 400
    bad_name_payload = {
        "run_id": "run-test-bad-name",
        "sandbox_name": "invalid-sandbox-name",
        "problem_id": "prob-detonator",
        "state": "created",
        "execution_target": "celesto_sandbox"
    }
    res_bad_name = client.post("/api/runs", json=bad_name_payload)
    assert res_bad_name.status_code == 400, f"Expected 400 for bad name, got {res_bad_name.status_code}"


def test_core_req_12_readme_required_phrases():
    """Verify README.md contains required phrases as headings or bold labels."""
    assert os.path.isfile("README.md"), "README.md missing at root"
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    required_phrases = [
        "Problem statement",
        "How I used Celesto",
        "Eval report",
        "Containment test",
        "State and failure design",
        "Setup",
    ]
    for phrase in required_phrases:
        assert phrase in content, f"Required phrase '{phrase}' not found in README.md"
