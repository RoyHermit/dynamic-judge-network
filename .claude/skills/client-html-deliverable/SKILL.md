---
name: client-html-deliverable
description: Use when converting a Markdown requirements, basic-design, hearing-response, or explanatory document into a client-facing, offline-viewable HTML deliverable for a customer or stakeholder audience.
---

# Client HTML Deliverable

## Rule

要件定義書・基本設計書・ヒアリング回答などの客先向け成果物は、MD原稿をそのまま渡さず `template.html` のコンポーネント一式でHTML化する。生成物はソース資料とは別レイヤーとして扱う: 各種の権威あるソース資料（要件一覧・アーキテクチャ資料・議事録など、プロジェクト各所に散在するMarkdown/CSV）を直接客先提出物として渡さない。生成物は毎回このSkillの手順で作り直す前提とする。

この「ソース資料」と、下記の手順3で組み立てる「この成果物1件のために用意した最終MD原稿」は別物である。前者は複数のソース資料から情報を集約する側で、変更せず元の場所に残す。後者はHTML化の直接の元になった単一の原稿で、後から見て「何を基にこのHTMLを作ったか」を追えるよう、生成したHTMLと同じ場所に置く（手順11参照）。

以下の手順では`docs/project/`・`docs/architecture/`・`docs/decisions/`・`docs/knowledge/`をソース、`docs/deliverables/`を生成物置き場とする構成を例として使うが、プロジェクトの実際のディレクトリ構成に合わせて読み替えてよい。

## いつ使うか

- 「要件定義書を作って」「基本設計書をHTML化して」「ヒアリング回答資料を作って」のような依頼
- 客先に見せる予定のMD文書（要件定義・基本設計・ヒアリング回答・説明資料）をHTML化する場面
- 社内レビューのみで完結する使い捨てメモには不要（過剰）

## 手順（MUST、この順で実行する）

1. **文書タイプを1つ選ぶ**：下表の`references/doc-types/`から該当ファイルを読む。MD原稿の内容だけで自動推定せず、必ず人間と会話で確認する。
2. **使う機能コンポーネントを選ぶ**：下表の`references/components/`のうち本文に必要なものだけ読む（複数ファイル分割が要るか／インタラクティブ要素を入れるか／UML図を入れるか）。これも自動判定せず人間と確認する。使わないものは読まない。
3. `template.html` をコピーし、1で選んだ文書タイプの章立て・本文パターンに合わせて中身を差し替える。
4. ヘッダーの`meta-box`・`doc-manifest`（入力マニフェスト・選択レシピ・改訂履歴）を埋める。**選んだ文書タイプ・適用したコンポーネント・使わなかった主要コンポーネントとその理由・出力形態（単一/複数ファイル）・生成時コミットID・未コミット変更の有無**を必ず記載する（次に開いたAI・人間が同じ構成で再生成できるようにするため）。再生成の場合は既存の`doc-manifest`の内容を初期値として提示し、変更点を人間に確認してから上書きする。
5. TOCは実際のアンカーIDに更新する。
6. 本文の性質に応じてcalloutクラスを使い分ける（下表）。同じ色に揃えない。
7. **段落は1つの論点につき1つの`<p>`にする**（目安2〜4文）。複数論点を1つの長い`<p>`に詰め込まない。列挙できる内容は`<p>`でなく`<ul>/<ol>`にする。
8. 画面イメージ・UIモックアップは**ASCIIアート（`┌─┐│└┘`）のpre/monospaceにしない**。テンプレのmock-panel／mock-tabbar+table／mock-chatのいずれかで実UI形状に組む。
9. 処理フロー図は横並びflexbox（flow-row的な実装）にしない。長文ステップが混じると箱が潰れて歪む。テンプレの縦積み`flow-steps`を使う。
10. 図が必要でもMermaid CDNは使わない（オフラインで開けなくなる）。インラインSVGか`flow-steps`/UIコンポーネント、またはUML図なら`references/components/plantuml-embed.md`の事前レンダリング手順で表現する。
11. **出力先**：`docs/deliverables/<成果物名>.html`（単一ファイル）または`docs/deliverables/<成果物名>/`配下（複数ファイル分割時、`multifile-packaging.md`参照）。手順3で組み立てたこの成果物専用の最終MD原稿も同じ場所に置く（散在するソース資料自体は移動しない）。外部公開（Artifact等）が必要かは都度ユーザーに確認する。
12. **最後に外部依存の監査を行う**：元MDや自分が書いた内容に紛れ込んだ外部リソース参照が無いか確認する。`<script src=`／`<link rel="stylesheet" href=`（Google Fontsなど外部CDN含む）／CSS `@import`・`url(http`／`<img src="http`／`<iframe>`／Mermaid等のCDNスクリプトをgrep等でチェックし、見つかれば埋め込み（data URI）または削除する。通常の`<a href>`テキストリンク（クリックしないと発火しない参照）は対象外。

## 文書タイプ一覧

| ファイル | 用途 |
|---|---|
| `references/doc-types/hearing-explanation.md` | ヒアリング回答・説明資料（Q&A形式） |
| `references/doc-types/requirements-doc.md` | 要件定義書（客先提出） |
| `references/doc-types/basic-design-doc.md` | 基本設計書（客先提出、arc42公式12章+国内SI標準の名称付きサブセクション） |
| `references/doc-types/detailed-design-doc.md` | 詳細設計書（客先提出、基本設計書と1:1の全章対応表+IPO記述） |

## 機能コンポーネント一覧

| ファイル | 用途 | 適用条件 |
|---|---|---|
| `references/components/multifile-packaging.md` | 複数ファイル分割＋相互リンク | 分量が大きく1ファイルでは閲覧性が落ちる場合のみ |
| `references/components/interactive-js.md` | アコーディオン／タブ切替／TOCスクロール連動 | インタラクティブ要素を入れる場合のみ |
| `references/components/plantuml-embed.md` | UML図（シーケンス図・クラス図等）の事前レンダリング埋め込み | UML図を入れる場合のみ |

## calloutタキソノミー

| クラス | 用途 | 見出し |
|---|---|---|
| `blockquote.client-answer` | 客先の実回答を引用 | 客先回答 |
| `callout ask` | こちらから確認したいこと | 🔎 確認したいこと |
| `callout warn` | 既知のリスク・注意点 | ⚠ 既知のリスク |
| `callout note` | 前回資料からの訂正 | 訂正 |
| `conclusion` | 結論・まとめ | （ラベル可変） |

## UIモックアップの4パターン

| コンポーネント | 用途 |
|---|---|
| `.mock-panel` | サイドパネル（スライドイン）の画面イメージ |
| `.mock-modal-backdrop` > `.mock-panel` | ダイアログ／モーダル（中央オーバーレイ）の画面イメージ。`.mock-panel`を暗い背景でラップし中央寄せするだけでサイドパネルと区別できる |
| `.mock-tabbar` + `.mock-table-wrap table` | タブ切替のある一覧・辞書画面 |
| `.mock-chat` | 対話型モーダル・チャットUI |

サイドパネルとモーダルは見た目が似ていても意味が違う（スライドインで一覧と併存 vs 画面中央に割り込むダイアログ）。どちらの案かで表記を混同しない。

## よくある間違い

- ASCIIアートでUIモックアップを表現する → 実HTML/CSSコンポーネント（mock-panel等）を使う
- Mermaid CDNスクリプトを読み込む → オフライン閲覧できなくなる、インラインSVG/CSSまたはPlantUML事前レンダリングで代替
- 手順フローを横並びflexboxで組む → 長文ステップが混じると箱が歪む、縦積み(flow-steps)にする
- calloutを全部同じ見た目にする → 客先回答/確認事項/リスク/訂正で色分けし視覚的に区別する
- 1つの`<p>`に複数論点を詰め込む → 読みにくくなる。論点ごとに`<p>`を分け、列挙は`<ul>/<ol>`にする
- 文書タイプ・機能コンポーネントをMD原稿の内容から自動で決めようとする → 判定ロジックは作らない。必ず人間と会話で確認する
- 入力マニフェスト・選択レシピを埋めずに出力する → 次回の再生成時に何を基に作ったか分からなくなる（ドリフト検知不能）。必ず埋める
