"""
Safety Hooks Implementation for Celesto MicroVM Sandboxes.

Safety hooks provide imperative pre-execution and post-execution callbacks that
intercept commands before they reach the guest kernel. When an untrusted agent or
a prompt-injected payload requests an unsafe operation, the safety hook inspects
the syntax and arguments, appends the decision to the immutable command audit log,
and raises a CommandBlockedError to stop execution.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Tuple

COMMAND_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "logs/commands.jsonl")

# Patterns indicating malicious behavior, prompt injection exfiltration, or destructive host/guest abuse
BLOCKED_PATTERNS = [
    re.compile(r"curl.*(@/root/\.env|@.*\.env|attacker\.com|exfil)", re.IGNORECASE),
    re.compile(r"/etc/shadow", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", re.IGNORECASE),  # Fork bomb
    re.compile(r"rm\s+-rf\s+/(?:\s|$)", re.IGNORECASE),  # Destructive wipe of root
    re.compile(r"(wget|curl).*\|\s*(bash|sh)", re.IGNORECASE),  # Unauthenticated remote script piping
    re.compile(r"printenv.*(?:CELESTO|AWS|KEY|SECRET|TOKEN)", re.IGNORECASE),  # Credential scraping
]


class CommandBlockedError(Exception):
    """Raised when a pre-execution safety hook rejects a command."""
    pass


class SafetyHookManager:
    """Manages pre-command and post-command inspection hooks for Celesto sandboxes."""

    def __init__(self, log_path: str = COMMAND_LOG_PATH):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)

    def log_command(self, sandbox_name: str, command: str, decision: str) -> None:
        """Append an audited command record to logs/commands.jsonl.
        
        Every command requested by an agent or detonation workload MUST be logged
        with execution_target explicitly set to 'celesto_sandbox'.
        """
        record = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "sandbox_name": sandbox_name,
            "command": command.strip(),
            "decision": decision,
            "execution_target": "celesto_sandbox"
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def inspect_command(self, sandbox_name: str, command: str) -> Tuple[bool, str]:
        """Inspect a command prior to dispatching to the Celesto microVM.
        
        Returns:
            (allowed: bool, reason: str)
        """
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(command):
                reason = f"Security rule triggered by pattern: {pattern.pattern}"
                self.log_command(sandbox_name, command, decision="block")
                return False, reason

        self.log_command(sandbox_name, command, decision="allow")
        return True, "Allowed"

    def execute_with_hook(self, sandbox_name: str, command: str, executor_fn):
        """Execute a command through the safety hook pipeline."""
        allowed, reason = self.inspect_command(sandbox_name, command)
        if not allowed:
            raise CommandBlockedError(f"Safety hook blocked command on {sandbox_name}: {reason}")
        return executor_fn(command)
