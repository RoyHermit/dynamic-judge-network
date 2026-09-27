#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_FILE="${SCRIPT_DIR}/block-patterns.txt"
AUDIT_LOG="${CLAUDE_PROJECT_DIR:-.}/.claude/guardrail-audit.log"

# 監査層のため、依存不足時は静かに継続する（主防御は①〜③）
command -v jq >/dev/null 2>&1 || exit 0

INPUT_JSON=$(cat -)
echo "${INPUT_JSON}" | jq -e . >/dev/null 2>&1 || exit 0

OUTPUT_TEXT=$(echo "${INPUT_JSON}" | jq -r '[.tool_response // {} | .. | strings] | join("\n")' 2>/dev/null || echo "")

[ -f "${PATTERN_FILE}" ] || exit 0

if grep -Eiq -f <(grep -Ev '^[[:space:]]*(#|$)' "${PATTERN_FILE}") <<< "${OUTPUT_TEXT}"; then
    TOOL_NAME=$(echo "${INPUT_JSON}" | jq -r '.tool_name // empty')
    echo "$(date -Iseconds) tool=${TOOL_NAME} secret-pattern-in-output" >> "${AUDIT_LOG}" 2>/dev/null || true
    printf '{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "直前の実行結果に機密情報らしきパターンを検知しました。会話ログに機密情報が残っている可能性があるため、内容を確認し必要ならセッションを破棄してください。"}\n' >&2
    exit 2
fi

exit 0
