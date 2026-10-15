#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

deny() {
    printf '{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "%s"}\n' "$1" >&2
    exit 2
}

# On some Windows setups `python3` resolves to the Microsoft Store alias stub,
# which exists on PATH but fails at runtime instead of running Python. Probe
# each candidate with a no-op before trusting it, and prefer python3 (the
# common Linux/Mac name) when it actually works.
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
        exec "$candidate" "$script_dir/../dangerous_command_guard.py"
    fi
done

deny "Pythonインタプリタ(python3/python)が見つからないため安全側に倒して遮断しました。"
