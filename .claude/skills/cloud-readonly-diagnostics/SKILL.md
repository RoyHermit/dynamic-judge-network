---
name: cloud-readonly-diagnostics
description: Use before checking logs/metrics or running smoke/connectivity checks (e.g. curl) against a production or customer-staging cloud environment — and before treating any "read" call there as automatically safe.
---

# Cloud Read-Only Diagnostics

## Rule

All three conditions must hold — "it's a read/GET call" alone is not enough:

1. **操作**: read-only限定。deploy/mutate/delete/writeは常に人間のみ実行する（Coreの原則、例外なし）。
2. **データ**: 応答に含まれうる実顧客データ・PII・シークレットは会話に出力しない。要約/マスキングするか、含まれる疑いがあれば作業を止めて人間に確認する。
3. **対象範囲**: 人間が事前に許可したアカウント/リージョン/リソースのallowlistの外へは出ない。

## How

- 実行前に対象がallowlistに入っているか確認する。不明なら止めて聞く。
- "read-only"に見えても秘密を返すAPI（Secrets Manager GetSecretValue、SSM GetParameter --with-decryption、KMS Decrypt等）は対象外として扱う。
- ログ取得は生ログ全文ではなく、エラー種別・件数・タイムスタンプなど要約してから会話に載せる。生ログの丸ごと貼り付けは避ける。
- curlでの疎通確認はGET/HEADなど副作用のないメソッド限定。POST/PUT/DELETE、または副作用のある既知GETエンドポイントは対象外。
- 機械的ガードを過信しない：このリポジトリのhook（`pre-tool-enforce.sh`）はBash/PowerShell経由のコマンドしか見ておらず、MCPサーバ経由のAPI呼び出し・SDK呼び出し・別profileには効かない。実効的な防御は対象環境側の専用read-onlyロール/IAM明示Denyであり、この規約はその代替ではない。

## Anti-patterns

- "GETだから安全"と機械的に判断する。
- CloudWatch Logsなどの生ログをそのまま会話に貼り付けて確認する。
- allowlist外のアカウント/リージョンに「ついでに」アクセスする。
- 「確認のため」を名目に`terraform apply`や`cdk deploy`など書き込み系操作を実行する。
