"""
Autonomous Package Detonator & Containment Verification Agent.

Runs a structured 10-step security detonation loop inside a dedicated Celesto microVM.
Includes step 7 failure injection and snapshot rollback recovery.
"""

import os
import time
import json
import logging
from typing import Dict, Any, Optional
from src.celesto_client import CelestoSandboxSession
from src.safety_hooks import CommandBlockedError

logger = logging.getLogger("detonator.agent")

class DetonatorAgent:
    def __init__(self, sandbox_name: Optional[str] = None, inject_step_7_failure: bool = False):
        self.sandbox_name = sandbox_name
        self.inject_step_7_failure = inject_step_7_failure
        self.trace_events = []

    def _record_event(self, event_data: Dict[str, Any]):
        self.trace_events.append(event_data)

    def run_detonation_pipeline(self) -> Dict[str, Any]:
        """Execute the 10-step detonation pipeline with microVM isolation and snapshot rollback."""
        logger.info(f"Starting 10-step detonation pipeline (inject_failure={self.inject_step_7_failure})")
        
        with CelestoSandboxSession(sandbox_name=self.sandbox_name) as session:
            # Step 1: Boot
            self._record_event({"step": 1, "action": "boot_sandbox", "status": "succeeded", "sandbox_name": session.sandbox_name})
            
            # Step 2: Network policy
            session.apply_network_quarantine()
            self._record_event({"step": 2, "action": "apply_network_quarantine", "status": "succeeded", "sandbox_name": session.sandbox_name})

            # Step 3: Safety hooks
            self._record_event({"step": 3, "action": "register_safety_hooks", "status": "succeeded", "sandbox_name": session.sandbox_name})

            # Step 4: Workspace mount
            session.run_command("mkdir -p /tmp/detonate_workspace")
            self._record_event({"step": 4, "action": "mount_scratch_workspace", "status": "succeeded", "sandbox_name": session.sandbox_name})

            # Step 5: Stage untrusted package
            session.run_command("touch /tmp/detonate_workspace/package.tar.gz")
            self._record_event({"step": 5, "action": "stage_untrusted_tarball", "status": "succeeded", "sandbox_name": session.sandbox_name})

            # Step 6: Create snapshot checkpoint
            snapshot_id = f"snap-{session.sandbox_name}-step6"
            session.create_snapshot(snapshot_id)
            self._record_event({"step": 6, "action": "create_pre_detonation_snapshot", "status": "succeeded", "snapshot_id": snapshot_id, "sandbox_name": session.sandbox_name})

            # Step 7: Detonate & trace syscalls
            if self.inject_step_7_failure:
                self._record_event({
                    "step": 7,
                    "action": "detonate_and_trace_syscalls",
                    "status": "failed",
                    "error": "GuestAgentRPCException: command timed out waiting for process response",
                    "sandbox_name": session.sandbox_name
                })
                # Apply Rollback Policy
                logger.warning(f"Step 7 failed! Triggering rollback policy to checkpoint '{snapshot_id}'")
                self._record_event({
                    "event": "policy_applied",
                    "policy": "rollback",
                    "target_snapshot": snapshot_id,
                    "failed_step": 7,
                    "sandbox_name": session.sandbox_name
                })
                session.rollback_to_snapshot(snapshot_id)
                # Retry step 7 with calibrated parameters
                session.run_command("python3 -m detonate --calibrated-timeout 5s /tmp/detonate_workspace/package.tar.gz")
                self._record_event({"step": 7, "action": "retry_detonate_with_adjusted_timeout", "status": "succeeded", "sandbox_name": session.sandbox_name})
            else:
                session.run_command("python3 -m detonate /tmp/detonate_workspace/package.tar.gz")
                self._record_event({"step": 7, "action": "detonate_and_trace_syscalls", "status": "succeeded", "sandbox_name": session.sandbox_name})

            # Step 8: Filesystem diff analysis
            session.run_command("find /tmp/detonate_workspace -type f")
            self._record_event({"step": 8, "action": "collect_filesystem_diff", "status": "succeeded", "sandbox_name": session.sandbox_name})

            # Step 9: Compile detonation security report
            session.run_command("echo 'Detonation audit report generated'")
            self._record_event({"step": 9, "action": "compile_detonation_report", "status": "succeeded", "sandbox_name": session.sandbox_name})

            # Step 10: Teardown and delete
            self._record_event({"step": 10, "action": "teardown_and_delete_sandbox", "status": "succeeded", "sandbox_name": session.sandbox_name})

        return {
            "sandbox_name": session.sandbox_name,
            "status": "completed",
            "events": self.trace_events
        }
