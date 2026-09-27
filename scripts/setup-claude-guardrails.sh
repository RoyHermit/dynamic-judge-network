#!/usr/bin/env bash
set -euo pipefail

echo "==> Setting up Claude Code guardrails..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOOKS_DIR="${PROJECT_ROOT}/.claude/hooks"

if [ ! -d "${HOOKS_DIR}" ]; then
    echo "[ERROR] ${HOOKS_DIR} not found. Run this script from the project root after copying template/." >&2
    exit 1
fi

chmod +x "${HOOKS_DIR}"/*.sh
echo "==> Hook scripts are now executable."

echo "==> Validating dependencies..."
if ! command -v jq &> /dev/null; then
    echo "[WARN] 'jq' is not installed. The security hooks fail closed (block everything) without it."
    echo "       Install jq before using Claude Code on this project: https://jqlang.org/download/"
else
    echo "[OK] jq is installed ($(jq --version))."
fi

echo "==> Setup completed."
