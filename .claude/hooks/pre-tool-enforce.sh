#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_FILE="${SCRIPT_DIR}/block-patterns.txt"
DANGER_FILE="${SCRIPT_DIR}/dangerous-commands.txt"

deny() {
    printf '{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "%s"}\n' "$1" >&2
    exit 2
}

command -v jq >/dev/null 2>&1 || deny "jqが見つからないため安全側に倒して遮断しました。"

INPUT_JSON=$(cat -)
echo "${INPUT_JSON}" | jq -e . >/dev/null 2>&1 || deny "入力JSONの解析に失敗したため安全側に倒して遮断しました。"

TOOL_NAME=$(echo "${INPUT_JSON}" | jq -r '.tool_name // empty')

# tool_inputの型を検証する。object以外(文字列・数値・配列等)はfail-closed。
TOOL_INPUT_TYPE=$(echo "${INPUT_JSON}" | jq -r '.tool_input | type') \
    || deny "tool_inputの型判定に失敗したため安全側に倒して遮断しました。"
if [ "${TOOL_INPUT_TYPE}" != "object" ] && [ "${TOOL_INPUT_TYPE}" != "null" ]; then
    deny "tool_inputが想定した型(object)ではないため安全側に倒して遮断しました。"
fi

# tool_input配下の全文字列値をraw(クォート無し)で抽出。jq自体の失敗もfail-closedにする。
INPUT_TEXT=$(echo "${INPUT_JSON}" | jq -r '[.tool_input // {} | .. | strings] | join("\n")') \
    || deny "tool_inputの解析に失敗したため安全側に倒して遮断しました。"

# パターンファイルを親シェルの変数へ捕捉し、捕捉自体のエラー(読み込み失敗等)をここで検知する。
# rc=0: 有効な行あり, rc=1: 全行がコメント/空行(正常。パターンなし=許可), rc>=2: 読み込み失敗等
grep_pattern_file() {
    local file="$1" text="$2" filtered filter_rc rc
    [ -f "${file}" ] || return 2
    filtered=$(grep -Ev '^[[:space:]]*(#|$)' "${file}")
    filter_rc=$?
    [ "${filter_rc}" -le 1 ] || return 2
    [ "${filter_rc}" -eq 1 ] && return 1
    grep -Eiq -f <(printf '%s\n' "${filtered}") <<< "${text}"
    rc=$?
    [ "${rc}" -le 1 ] || return 2
    return "${rc}"
}

check_and_deny() {
    local file="$1" text="$2" message="$3" rc
    grep_pattern_file "${file}" "${text}"
    rc=$?
    case "${rc}" in
        0) deny "${message}" ;;
        1) return 0 ;;
        *) deny "パターン検査自体に失敗したため安全側に倒して遮断しました（${file}）。" ;;
    esac
}

# BashツールとPowerShellツールは同じtool_input.command構造を持つ(Windows未導入時/PowerShellツール
# 有効時はBashツールでなくPowerShellツールが使われるため、Bash限定にすると危険コマンド検知が
# 素通りする。Claude Code公式ドキュメントもBash|PowerShell両方へのマッチを明記している)。
if [ "${TOOL_NAME}" = "Bash" ] || [ "${TOOL_NAME}" = "PowerShell" ]; then
    CMD_TYPE=$(echo "${INPUT_JSON}" | jq -r '(.tool_input.command // "") | type') \
        || deny "commandフィールドの型判定に失敗したため安全側に倒して遮断しました。"
    if [ "${CMD_TYPE}" != "string" ]; then
        deny "commandフィールドが想定した型(string)ではないため安全側に倒して遮断しました。"
    fi
    CMD=$(echo "${INPUT_JSON}" | jq -r '.tool_input.command // empty') \
        || deny "commandフィールドの解析に失敗したため安全側に倒して遮断しました。"
    check_and_deny "${DANGER_FILE}" "${CMD}" \
        "危険な操作を検知しました（補助チェック）。本番反映・破壊的操作は人間が実行してください。"
fi

check_and_deny "${PATTERN_FILE}" "${INPUT_TEXT}" \
    "機密情報（APIキー/秘密鍵/.env等）を検知したため遮断しました。"

exit 0
