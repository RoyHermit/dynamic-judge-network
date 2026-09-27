#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATTERN_FILE="${SCRIPT_DIR}/block-patterns.txt"

block() {
    printf '{"decision": "block", "reason": "%s"}\n' "$1" >&2
    exit 2
}

command -v jq >/dev/null 2>&1 || block "jq未検出のため安全側に倒して遮断しました。"

INPUT_JSON=$(cat -)
echo "${INPUT_JSON}" | jq -e . >/dev/null 2>&1 || block "入力JSONの解析に失敗したため遮断しました。"

PROMPT_TYPE=$(echo "${INPUT_JSON}" | jq -r '(.prompt // "") | type') \
    || block "promptフィールドの型判定に失敗したため安全側に倒して遮断しました。"
if [ "${PROMPT_TYPE}" != "string" ]; then
    block "promptフィールドが想定した型(string)ではないため安全側に倒して遮断しました。"
fi

PROMPT=$(echo "${INPUT_JSON}" | jq -r '.prompt // empty') \
    || block "promptフィールドの解析に失敗したため安全側に倒して遮断しました。"

[ -f "${PATTERN_FILE}" ] || block "block-patterns.txtが見つからないため遮断しました。"

# パターンファイルを親シェルの変数へ捕捉し、捕捉自体の失敗(読み込み失敗等)を検知する。
# rc=0: 有効な行あり, rc=1: 全行がコメント/空行(正常。パターンなし=許可), rc>=2: 読み込み失敗等
FILTERED=$(grep -Ev '^[[:space:]]*(#|$)' "${PATTERN_FILE}")
FILTER_RC=$?
[ "${FILTER_RC}" -le 1 ] || block "パターン検査自体に失敗したため安全側に倒して遮断しました。"

if [ "${FILTER_RC}" -eq 0 ]; then
    grep -Eiq -f <(printf '%s\n' "${FILTERED}") <<< "${PROMPT}"
    rc=$?
    if [ "${rc}" -eq 0 ]; then
        block "メッセージに機密情報（APIキー/秘密鍵等）が含まれる可能性があるため送信を中断しました。"
    elif [ "${rc}" -ge 2 ]; then
        block "パターン検査自体に失敗したため安全側に倒して遮断しました。"
    fi
fi

exit 0
