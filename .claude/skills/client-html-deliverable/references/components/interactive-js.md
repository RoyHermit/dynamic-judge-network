# コンポーネント: インタラクティブ要素（interactive-js）

## 適用条件

アコーディオン開閉・タブ切替・TOCスクロール連動など、クリック操作で見やすくなる要素を入れたい場合のみ使う。外部CDNは使わない（Skillのオフライン閲覧原則）ので、すべてインラインJSで完結させる。

## 大原則：progressive enhancement

**本文はJSが無効でも全て読める状態を既定にする。** JSは「操作性を上げる」ためだけに使い、JSが動かない環境（客先のセキュリティ設定でJS無効、印刷/PDF変換等）でも情報が欠落しないようにする。

- アコーディオンは`<details>/<summary>`をベースにする（ネイティブに開閉・キーボード操作・スクリーンリーダー対応済み）。独自divでの開閉実装はARIA属性を手動管理する必要があり避ける
- 既定で`open`にしておく（閉じた状態が既定だと、JS無効時に内容が見えなくなる）
- `prefers-reduced-motion`を尊重し、アニメーションは`@media (prefers-reduced-motion: no-preference)`の中でのみ適用する

## アコーディオン（`<details>`ベース、追加JS不要）

```html
<style>
  details.section-toggle { border: 1px solid var(--border); border-radius: 8px; margin: 12px 0; }
  details.section-toggle summary { cursor: pointer; padding: 12px 16px; font-weight: 600; list-style: none; }
  details.section-toggle summary::-webkit-details-marker { display: none; }
  details.section-toggle summary::before { content: "▶"; display: inline-block; margin-right: 8px; transition: transform 0.15s; }
  details.section-toggle[open] summary::before { transform: rotate(90deg); }
  details.section-toggle .body { padding: 0 16px 16px; }
  @media (prefers-reduced-motion: reduce) {
    details.section-toggle summary::before { transition: none; }
  }
  @media print {
    details.section-toggle { break-inside: avoid; }
  }
</style>

<details class="section-toggle" open>
  <summary>[見出し]</summary>
  <div class="body">[本文]</div>
</details>
```

## タブ切替（ARIA対応、JS必須・JS無効時は全タブ内容を縦積み表示）

```html
<style>
  .tabset .tab-list { display: flex; gap: 4px; border-bottom: 1px solid var(--border); }
  .tabset [role="tab"] { padding: 8px 16px; border: 1px solid transparent; border-bottom: none; cursor: pointer; background: none; font: inherit; color: var(--text-sub); }
  .tabset [role="tab"][aria-selected="true"] { color: var(--accent); font-weight: 700; border-color: var(--border); border-bottom: 2px solid #fff; margin-bottom: -1px; background: #fff; }
  .tabset [role="tabpanel"] { padding: 16px 4px; }
  /* JS無効時のフォールバック: タブボタンを隠し、hidden属性のUA既定非表示も打ち消して全パネルを縦積み表示する */
  .tabset:not(.js-ready) [role="tab"] { display: none; }
  .tabset:not(.js-ready) [role="tabpanel"][hidden] { display: block; }
  .tabset.js-ready [role="tabpanel"][hidden] { display: none; }
</style>

<div class="tabset" id="tabset1">
  <div class="tab-list" role="tablist" aria-label="[タブグループの説明]">
    <button role="tab" id="tab-a" aria-controls="panel-a" aria-selected="true">[タブA]</button>
    <button role="tab" id="tab-b" aria-controls="panel-b" aria-selected="false">[タブB]</button>
  </div>
  <div role="tabpanel" id="panel-a" aria-labelledby="tab-a">[タブA本文]</div>
  <div role="tabpanel" id="panel-b" aria-labelledby="tab-b" hidden>[タブB本文]</div>
</div>

<script>
(function () {
  document.querySelectorAll('.tabset').forEach(function (root) {
    root.classList.add('js-ready');
    var tabs = root.querySelectorAll('[role="tab"]');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () { activate(tab); });
      tab.addEventListener('keydown', function (e) {
        var i = Array.prototype.indexOf.call(tabs, tab);
        if (e.key === 'ArrowRight') activate(tabs[(i + 1) % tabs.length]);
        if (e.key === 'ArrowLeft') activate(tabs[(i - 1 + tabs.length) % tabs.length]);
      });
    });
    function activate(tab) {
      tabs.forEach(function (t) {
        var selected = t === tab;
        t.setAttribute('aria-selected', selected);
        document.getElementById(t.getAttribute('aria-controls')).hidden = !selected;
      });
      tab.focus();
    }
  });
})();
</script>
```

- JS無効時は`.js-ready`が付かず、`[role="tabpanel"][hidden]`のCSSも効かないため**全パネルがそのまま縦に並んで表示される**（情報は欠落しない、見た目がタブでなくなるだけ）

## TOCスクロール連動ハイライト（装飾のみ、JS無効でも既存のTOCリンクはそのまま機能）

```html
<script>
(function () {
  var toc = document.querySelector('nav.toc');
  if (!toc) return;
  var links = toc.querySelectorAll('a[href^="#"]');
  var targets = Array.prototype.map.call(links, function (a) {
    return document.getElementById(a.getAttribute('href').slice(1));
  }).filter(Boolean);
  if (!targets.length || !('IntersectionObserver' in window)) return;
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      var link = toc.querySelector('a[href="#' + entry.target.id + '"]');
      if (link) link.classList.toggle('active', entry.isIntersecting);
    });
  }, { rootMargin: '-20% 0px -70% 0px' });
  targets.forEach(function (t) { observer.observe(t); });
})();
</script>
<style>
  nav.toc a.active { font-weight: 700; text-decoration: underline; }
</style>
```

## 接続線アニメーション（データフロー表現、追加JS不要）

システム構成図・処理フロー図で「データがこの経路を流れている」ことを視覚的に示したい場合に使う。CSSのみ（`stroke-dasharray`＋`stroke-dashoffset`をアニメーション）で、SVGの線に沿って破線が流れる表現を作れる。外部ライブラリ不要、JS無効時は静止した破線としてそのまま表示される（情報は欠落しない、動きが止まるだけ）。

```html
<style>
  .flow-line {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2;
    stroke-dasharray: 6 10;
    animation: flow-dash 1.1s linear infinite;
  }
  @media (prefers-reduced-motion: reduce) {
    .flow-line { animation: none; }
  }
  @keyframes flow-dash {
    to { stroke-dashoffset: -16; }
  }
</style>

<svg viewBox="0 0 400 120">
  <line class="flow-line" x1="20" y1="60" x2="380" y2="60" marker-end="url(#arrow)"/>
  <!-- 矢印マーカーは既存のC4図例(references/doc-types/basic-design-doc.md)と同じdefs/marker定義を使い回せる -->
</svg>
```

- 矢印の向き＝破線が流れる方向（`stroke-dashoffset`を負方向に動かすと矢印の指す方向へ流れる）と揃える。逆方向に見えるとかえって分かりにくくなるので、実際に描画して目で確認する
- 使いどころは「本当に流れが重要な経路」だけに絞る。図中の全ての線を光らせると逆に何が要点か伝わらなくなる（強調を全体に均等にばら撒くと、結局どこも強調されていないのと同じになる。強調は1箇所〜数箇所に留める）
- グラデーションストロークを重ねて「光の粒」らしさを強めることもできるが、業務資料としては上記の破線移動で十分なことが多い。過剰演出にしない

## 印刷対応

`@media print`でアコーディオンは`break-inside: avoid`、タブは全パネルを表示する（`hidden`属性を印刷時は無効化する）：

```css
@media print {
  .tabset [role="tabpanel"][hidden] { display: block !important; }
  .tabset [role="tab"] { display: none; }
}
```
