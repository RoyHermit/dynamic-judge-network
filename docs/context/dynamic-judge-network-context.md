# Dynamic Judge Network — Research & Development Context

> Status: Foundation implemented; network mechanisms remain research plans
> Primary development agents: Claude Code / Codex  
> Initial benchmark: High & Low directional decision task  
> Core implementation candidate: Jev-based lightweight judges  
> Date: 2026-09-27

> **Research update (2026-09-29):** Read this document together with
> [DJN Research Direction Update](djn-research-direction-update.md). The update
> refines the novelty boundary, baseline labels, execution model, metrics,
> and ablation order for future work. Sections 12 and 15 below reflect the
> revised labels and progression; the update has the detailed rationale.
> The approved foundation spec and its implementation remain historical
> records of the scope completed at that time.
>
> **Additional research input (2026-10-02):** Read the
> [SpikingBrain-inspired DJN input](djn-research-input-spikingbrain.md)
> as a source of candidate later-stage hypotheses. It does not change the
> fixed-Judge first experiment, imply that DJN implements spiking neurons,
> or transfer the paper's measured results to DJN.

---

## 1. この文書の目的

この文書は、Claude Code / Codex が本プロジェクトの背景・研究仮説・設計思想を理解したうえで、実装・レビュー・実験設計を行えるようにするためのコンテキスト資料である。

本プロジェクトの目的は、単純な「Jevを複数並べるシステム」を作ることではない。

研究対象は、**多様な軽量Judgeを必要に応じて動的に発火させ、Judge間の相互作用、集約、早期停止、経験による経路最適化によって、高速かつ高精度な意思決定を実現できるか**という点にある。

暫定的に、このアーキテクチャを以下のように呼ぶ。

**Dynamic Judge Network (DJN)**

研究テーマとしては、

> **Bio-inspired Dynamic Sparse Multi-Judge Reasoning**

すなわち、

> **生物の意思決定機構に着想を得た、動的・疎結合なマルチJudge推論アーキテクチャ**

として扱う。

---

## 2. 背景

現在の高性能LLMは、非常に広範な問題を単一モデルで処理できる一方、単純な分類・判定問題に対しても比較的大きな計算資源を必要とする。

一方、実際の意思決定問題の多くは、

- 正常か異常か
- HIGHかLOWか
- 実行すべきかSKIPすべきか
- リスクが高いか低いか
- ある仮説を支持するか反証するか

といった、狭い判断の組み合わせとして表現できる。

そこで、巨大モデルに一度ですべてを判断させるのではなく、**狭い判断を得意とする多数の軽量Judgeに問題を分解し、それらの判断を統合する**方式を検討する。

Jevは現時点で、この「軽量Judge」の実装候補として有力である。

ただし、本研究はJev固有の研究ではない。

将来的にはJudgeとして以下を利用できる設計を想定する。

- Jev
- 小型LLM
- classifier
- rule engine
- static analyzer
- embedding model
- numerical model
- external tool
- domain-specific ML model

Jevは初期PoCにおける実装手段の一つである。

---

## 3. 中心仮説

本研究の中心仮説は以下である。

> **多数の軽量Judgeに異なる観点を持たせ、必要なJudgeだけを動的に実行し、その相互作用と結果を統合することで、単一の軽量モデルより高精度でありながら、大型LLMより低レイテンシ・低コストな意思決定システムを構築できるのではないか。**

さらに、

> **Judgeの実行経路自体を過去の成功・失敗から適応させることで、問題ごとに異なる「思考回路」を形成できるのではないか。**

という仮説を持つ。

目標は生物の脳そのものを再現することではない。

生物の意思決定から、

- sparse activation
- excitation
- inhibition
- attention
- feedback
- early stopping
- reinforcement / weakening
- adaptive routing

といった原理のみを抽出し、AI推論システムへ応用する。

---

## 4. 基本アーキテクチャ

最終的には以下のような構成を想定する。

```text
                     Input
                       |
                       v
              +----------------+
              | Semantic Router|
              |   Small LLM    |
              +-------+--------+
                      |
                      v
              Initial Judge Set
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
        Judge A     Judge B     Judge C
          | \          |          /
          |  \         v         /
          |   +----> Judge D <---+
          |            |
          |         inhibition
          |            |
          +--------> Judge E
                       |
                       v
                 Aggregator
                       |
              +--------+--------+
              |                 |
         confidence high   confidence low
              |                 |
              v                 v
           Decision       More Judges /
                          Frontier LLM
```

ただし、**初期PoCではSemantic Routerを研究対象から除外する。**

最初は単一タスクに固定し、

```text
Known Task
    |
    v
Dynamic Judge Network
    |
    v
Decision
```

のみを評価する。

Routerを最初から含めると、失敗原因が

- task classification
- Judge design
- Judge selection
- graph activation
- aggregation

のどこにあるのか分離しにくいためである。

---

## 5. 従来のEnsembleとの違い

単純なensembleでは、

```text
Input
  |
  +--> Judge 1
  +--> Judge 2
  +--> Judge 3
  +--> Judge 4
  +--> Judge 5
          |
          v
      Average / Vote
```

となる。

Dynamic Judge Networkでは、

```text
Input
  |
  v
Judge 1
  |
  +----> Judge 4
  |
Judge 2 ----| Judge 5
  |
  +----> Judge 7
             |
             v
          Decision
```

のように、Judgeの判断によって次に実行されるJudgeが変化する。

重要なのはJudgeの総数ではなく、

- 実際に発火したJudge数
- 推論経路
- Judge間の相互作用
- 推論深度
- どの時点で停止したか

である。

---

## 6. Judgeの多様性

Judgeを増やすだけでは十分ではない。

例えば、

```text
J1: 上昇するか？
J2: 上昇するか？
J3: 上昇するか？
```

という構成では、誤りが強く相関する可能性が高い。

代わりに、

```text
J1: Trend
J2: Momentum
J3: Mean Reversion
J4: Volatility
J5: Breakout
J6: Noise
J7: Regime
J8: Contrarian
J9: Risk
J10: Counter-evidence
```

のように、異なる観点から同じ問題を見る。

重要な研究対象の一つは、

> **Judge間のerror correlationをどこまで下げられるか**

である。

単独精度が若干低いJudgeでも、他Judgeと異なる失敗をするならensemble全体には有用な可能性がある。

概念的にはJudgeのUtilityを、

```text
Utility(J_i)
    = Accuracy
    + UniqueContribution
    - ErrorCorrelation
    - LatencyCost
    - ComputeCost
```

のように考える。

これは現時点では概念式であり、実装仕様ではない。

---

## 7. 生物的発想から取り入れる要素

### 7.1 Sparse Activation

すべてのJudgeを毎回実行しない。

100 Judge存在していても、ある問題では5 Judge、別の問題では12 Judgeだけが実行される、といった構造を目指す。

### 7.2 Excitation

あるJudgeの結果によって別Judgeを発火しやすくする。

```text
Trend strongly positive
        |
        v
Momentum Judge activated
        |
        v
Overextension Judge activated
```

### 7.3 Inhibition

あるJudgeの結果によって、別のJudgeや判断方向を抑制する。

```text
Danger = 0.98
    |
    +--> suppress optimistic path
    |
    +--> activate additional risk analysis
```

### 7.4 Counter-evidence

ある方向に判断が傾いた場合、意図的に反証Judgeを発火させる。

```text
HIGH hypothesis
      |
      v
"Find evidence against HIGH"
      |
      v
Counter Judge
```

単なる多数決よりも、多様な推論を維持することを狙う。

### 7.5 Early Stopping

十分な確信が形成された場合、それ以上Judgeを実行しない。

```text
J1 = 0.97
J2 = 0.95
J3 = 0.96

Consensus sufficiently high
        |
        v
STOP
```

逆にJudge間の不一致が大きければ追加Judgeを実行する。

### 7.6 Plasticity / Memory

将来的には、

```text
J3 -> J8 -> J14
```

という経路が特定の問題で高い成功率を持つ場合、その経路を発火しやすくする。

失敗が多い接続は弱める。

```text
successful path -> strengthen
failed path     -> weaken
unused path     -> prune candidate
```

これにより問題ごとに有効な「思考回路」が形成される可能性を検証する。

### 7.7 Adaptive activation hypotheses (future)

The [SpikingBrain-inspired input](djn-research-input-spikingbrain.md)
motivates tests at the *Judge network* level, distinct from the paper's
model-internal spiking mechanisms:

- Compare fixed Judge activation thresholds with deterministic thresholds
  adjusted by the current Evidence State, uncertainty, disagreement,
  expected information value, and remaining budget.
- Test whether strong directional consensus should make redundant
  supporting Judges harder to activate while making counter-evidence
  Judges easier to activate. Compare both choices against fixed-threshold
  controls; neither benefit is assumed.
- Test group selection against flat Judge routing only after a useful
  Judge pool exists. Treat group selection and per-Judge selection as
  separate mechanisms in an ablation.
- Permit temporary extra waves for valid but conflicting, unusual, or
  high-risk inputs, subject to a budget and a measured benefit. Critically
  missing data still stops at the deterministic sufficiency gate with
  `SKIP`; it is not a reason to run additional Judges.

Start with inspectable rules and log their inputs and decisions. Learned
thresholds and routing belong after fixed baselines and sufficient data.
Judge sparsity is a measurement, not a goal to maximize on its own.

---

## 8. 速度に関する仮説

Judge数が多いこと自体は必ずしも遅さを意味しない。

並列実行できるため、レイテンシを支配するのは主に、

**Judge総数ではなくcritical path depth**

である。

例えば、

```text
Stage 1:
J1 J2 J3 J4      parallel

Stage 2:
   J7 J8         parallel

Stage 3:
     J12

Decision
```

なら、Judgeが7個実行されても逐次深度は3である。

したがって研究上は、

- breadth
- depth
- activated judge count
- parallelism
- early-stop rate

を別々に計測する。

目標は単純な最高精度ではなく、

```text
Accuracy
Latency
Compute
Cost
Coverage
```

のPareto frontierを改善することである。

---

## 9. 初期PoC: High & Low

最初の実験対象として、High & Low型の方向予測問題を利用する。

これは本システムの最終用途を意味しない。

採用理由は、

- 出力が離散的
- HIGH / LOW / SKIPで表現できる
- Ground Truthを自動生成できる
- 大量データを蓄積しやすい
- 人手ラベリングへの依存が小さい
- 時系列で継続評価できる
- latency計測が容易
- Judgeごとの寄与を分析しやすい

ためである。

実資金による取引を目的とせず、研究・バックテスト・ペーパートレード用のベンチマークとして扱う。

---

## 10. High & Low Judge候補

初期候補として以下を想定する。

```text
Trend Judge
Momentum Judge
Mean-Reversion Judge
Volatility Judge
Breakout Judge
Support/Resistance Judge
Noise Judge
Regime Judge
Overextension Judge
Contrarian Judge
Counter-HIGH Judge
Counter-LOW Judge
Uncertainty Judge
```

Judge数は固定しない。

最初は10〜20程度から開始し、実験結果をもとに増減させる。

---

## 11. 出力

最終的な意思決定は、

```text
HIGH
LOW
SKIP
```

とする。

特にSKIPを重要な出力として扱う。

本研究では、

> すべてのケースで回答すること

を目的としない。

むしろ、

> **判断可能な局面を正しく選択できること**

を重要視する。

したがって、

```text
accuracy
coverage
```

をセットで評価する。

例:

```text
confidence > 0.50
accuracy = 54%
coverage = 100%

confidence > 0.70
accuracy = 59%
coverage = 42%

confidence > 0.85
accuracy = 64%
coverage = 13%
```

このようなAccuracy-Coverage曲線を評価対象とする。

---

## 12. Baselines and reference

Compare configurations on the same data and evaluation protocol. These
labels follow [Research Direction Update §19](djn-research-direction-update.md#19-refined-baselines).

### Baseline A — Single Judge

`Input -> one Judge -> decision`.

### Baseline B — Single Judge + Confidence Escalation

Start with one Judge and escalate only when its confidence is
insufficient; the escalation target and threshold belong in that
baseline's spec. This is a cascade comparator for DJN's multi-Judge
routing claim.

### Baseline C — Fixed Multi-Judge

Execute the same selected Judges for every input and use simple
aggregation, starting with an average. This includes the fixed parallel
ensemble originally called Baseline B.

### Baseline D — Diverse Fixed Multi-Judge

Execute every specialist role on every input, then aggregate. The
specialists should differ in failure mode, not only prompt wording. This
was originally called Baseline C.

### Experimental E — Dynamic Judge Network

Use intermediate evidence to select later Judges, counter-evidence, and
stopping paths. Activation Waves and compact Evidence State are separate
mechanisms to test, not properties to assume every DJN run needs.

### Reference F — Frontier LLM

Evaluate the same task as a quality, cost, and latency reference. Beating
the frontier model is not an initial success criterion.

Experiment 1 begins with fixed Judges and averaging. Its spec will
define the exact A/C comparisons; B and D need their own explicit
comparison boundaries before results are attributed to a mechanism.

---

## 13. 必須メトリクス

最低限以下を保存する。

### Prediction quality

- Accuracy
- Precision
- Recall
- F1
- Brier Score
- Calibration
- HIGH accuracy
- LOW accuracy
- SKIP rate
- Coverage
- Accuracy at coverage

### Performance

- total latency
- P50 latency
- P95 latency
- P99 latency
- provider, routing, aggregation, storage, and wave latency
- attempted, fetched, activated, and used Judge counts
- maximum graph depth
- wave count
- early-stop rate

### Diversity

- Judge-to-Judge agreement
- error correlation
- unique correct decisions
- marginal contribution
- ensemble gain

### Resource

- provider request count
- questions per request
- input size
- token usage if applicable
- CPU/GPU usage where practical
- API cost where applicable

### Sparse execution (later dynamic studies)

Record the candidate Judge pool and its version for each comparison.
Define `judge_sparsity` as one minus the number of distinct Judges whose
questions were attempted divided by the available Judge count. Define
`activation_sparsity` with distinct activated Judges over the same
denominator. Keep fetched and used counts separate, and log retries and
provider requests independently. When group routing exists, define
group sparsity against a declared candidate-group pool. Handle an empty
pool explicitly rather than dividing by zero. Report gate-failed inputs
separately so no-execution `SKIP` cases do not inflate the apparent
benefit of routing. Speculative fetching can make activation sparsity
look high without reducing provider work; report requests, latency, and
cost alongside these ratios. Any weighted compute sparsity metric needs
an explicit dense comparator and actual or defensible cost weights.

Attempted questions, fetched answers, activated Judges, and used evidence
are distinct. See [Research Direction Update](djn-research-direction-update.md)
§§9–13 and 21 for the proposed measurement model. The current foundation
database records data from which attempted/answered counts can be derived
and has a nullable `was_used` field, but no independent activated flag or
wave/evidence-state records yet.

---

## 14. 必須ログ

再現可能性を優先する。

最低限、各判断について以下を保存する。

```text
experiment_id
timestamp

input_id
input_features
task_type

judge_id
judge_version
judge_prompt_or_definition
raw_provider_answer
interpreted_judge_output
judge_confidence
judge_latency

wave_id
wave_index
requested_judges
fetched_judges
activated_judges
used_judges
evidence_state_before
evidence_state_after

activation_source
activation_reason
graph_depth
parent_judge
stop_evaluated
stop_result
stop_reason

aggregator_version
aggregate_score
final_confidence
final_decision

ground_truth
is_correct

total_latency
attempted_judge_count
fetched_judge_count
activated_judge_count
used_judge_count
provider_request_count
questions_per_request
early_stopped
```

可能な限り、後から同一条件を再実行できる形式にする。

Also record network state around each wave, activation scores, consensus,
disagreement, uncertainty, input size, provider usage, and
provider/routing/aggregation/storage latency separately. The full field
list is in [Research Direction Update §21](djn-research-direction-update.md#21-logging-requirements).
These are future logging requirements, not a description of the current
foundation schema.

For later threshold, group-routing, and burst ablations, also preserve
the candidate pool, group membership, base and adjusted thresholds,
activation scores, adjustment/suppression reasons, burst trigger, and
budget state. Add these fields when the corresponding mechanism is
specified; they are not claims about the current storage schema. See the
[SpikingBrain-inspired input](djn-research-input-spikingbrain.md) for
candidate research questions and fields.

---

## 15. Ablation Test

Experiment 1 is **Fixed Judges + Average**. Add one mechanism at a time
after the simple and diverse fixed baselines; otherwise a gain cannot be
attributed to a particular mechanism. The current candidate sequence,
refined in [Research Direction Update §20](djn-research-direction-update.md#20-ablations),
is:

```text
fixed execution -> diverse fixed roles
-> deterministic dynamic activation -> Activation Waves
-> counter-evidence -> inhibition -> early stopping
-> Evidence State compression -> deterministic pre-gates
-> speculative batching -> learned routing -> path memory/plasticity
```

Feature computation may be deterministic from the start; the
deterministic pre-gate *ablation* tests whether skipping model work before
Wave 0 improves the measured frontier. Excitation and learned edge
weights remain future candidates rather than being bundled into the
first dynamic-routing result. Later experiment numbers belong in their
own specs, where each has a hypothesis, baseline, metric, ablation, and
required logs.

Compare changes in accuracy, latency, attempted/fetched/activated/used
Judge counts, coverage, error correlation, wave count, and cost under the
same data protocol.

The SpikingBrain-inspired threshold study is a later candidate within
dynamic activation, not a replacement for Experiment 1 or the A–F
baselines. Establish simple fixed-threshold dynamic routing before
testing state-adaptive thresholds against the same all-on and fixed
controls. Test counter-evidence threshold adjustment only after a
counter-evidence baseline exists; isolate group routing and burst
execution in their own comparisons. Learned policies follow only if
simpler policies have measured value. Read any sparsity gain with
accuracy, calibration, coverage, latency, provider calls, and cost.

---

## 16. Aggregator

初期段階では複雑なモデルを使用しない。

候補:

1. Simple Average
2. Weighted Sum
3. Majority Vote
4. Logistic Regression

データ蓄積後に、

- small MLP
- learned stacking
- context-dependent weighting

などを検討する。

重要なのは、初期PoCで「高度なAggregatorのおかげで勝った」という状態を避けることである。

まずJudge Networkそのものの価値を検証する。

Keep directional aggregation (`HIGH` versus `LOW`) separate from the
absolute actionability gate (`ACT` versus `SKIP`). A directional preference
alone does not justify an action, and missing evidence must be explicit.

---

## 17. Judge Graph

Start with inspectable deterministic routing. A node can be a
deterministic gate, rule, classifier, provider-backed Judge, numerical
model, or tool; a graph of only AI Judges is not required. Shared-state
batching belongs to an executor and must not change the abstract Judge
contract.

概念例:

```text
Node:
    kind: deterministic_gate | Judge | classifier | tool
    input/output contract

Edge:
    source
    target
    activation condition
    optional type: excitatory | inhibitory

Runtime State:
    Evidence State
    attempted / fetched / activated / used
    wave index and stop reason
```

Learned edge weights and activation-score formulas are later candidates,
after deterministic routing has been measured. An illustrative form is:

```text
activation_j =
    f(
        external_signal
        + Σ excitatory_signal
        - Σ inhibitory_signal
        - execution_cost
    )
```

のような形を考える。

ただし、初期段階で生物学的忠実性を追求しない。

シンプルで説明可能なルールから開始する。

---

## 18. 学習フェーズ

最初からend-to-end learningを行わない。

### Phase 0 — Hand-designed

```text
Human-defined Judges
Human-defined graph
Fixed thresholds
Simple aggregation
```

### Phase 1 — Measurement

大量の実測ログを収集する。

### Phase 2 — Weight Learning

```text
Judge weights
Edge weights
Thresholds
```

を過去データから最適化する。

### Phase 3 — Routing Learning

```text
P(Judge useful | state)
```

を学習し、必要なJudgeの予測精度を上げる。

### Phase 4 — Structural Learning

必要に応じて、

```text
edge creation
edge pruning
Judge pruning
Judge specialization
```

を検討する。

---

## 19. 将来的な汎用化

単一タスクで有効性が確認できた後、

```text
User Input
    |
    v
Small LLM Router
    |
    v
TaskSpec
    |
    v
Judge Network Selection
    |
    v
Dynamic Judge Network
    |
    v
Decision
```

へ拡張する。

Small LLMの役割は回答生成ではない。

主に、

- domain classification
- task classification
- risk classification
- initial Judge selection
- TaskSpec generation

を担当する。

Routerがボトルネックになった場合、蓄積データを利用して小型classifierへdistillすることも検討する。

---

## 20. Frontier LLMとの関係

Frontier LLMを排除することが目的ではない。

将来的には、

```text
Dynamic Judge Network
        |
   confidence?
    /       \
 high       low
  |          |
Decision   Frontier LLM
```

というcascadeを想定する。

つまり、

> **簡単な問題にはほとんど計算資源を使わず、難しい問題だけ高価な知能へエスカレーションする。**

ことを目指す。

評価指標として、

```text
Frontier-like accuracy
at significantly lower
average latency / cost
```

を重視する。

---

## 21. 非目標

初期段階では以下を目的としない。

- 人間の脳の忠実な再現
- ショウジョウバエconnectomeのコピー
- AGIの構築
- 新しいFoundation Modelの事前学習
- Frontier LLMの全面的な代替
- 実資金による自動取引
- 複数ドメインへの即時対応
- 複雑なend-to-end neural architecture

研究対象を広げすぎないこと。

---

## 22. 重要な設計原則

### Measure before optimize

直感でJudgeや接続を最適化しない。

必ずログを残し、実測値から判断する。

### Baseline first

新しい機構を追加する前に必ず比較対象を用意する。

### One variable at a time

Ablation可能な形で機能を追加する。

### Reproducibility

prompt、Judge定義、モデルversion、threshold等をversion管理する。

### Diversity over quantity

Judge数を増やすことより、異なる失敗パターンを持つJudgeを作る。

### Latency is a first-class metric

精度だけを最適化しない。

### SKIP is valid

確信がない場合に判断しない能力を評価する。

### Jev is replaceable

Jev固有のコードとJudge Network runtimeを密結合させない。

---

## 23. Claude Code / Codexへの実装方針

Claude Code / Codexは、本プロジェクトを単なるアプリケーション開発として扱わないこと。

変更時には、

1. 研究仮説を壊していないか
2. 比較実験可能か
3. ログが十分か
4. 再現可能か
5. 新機構の効果を単独測定できるか
6. latencyへの影響を測定できるか

を考慮する。

Before adding a mechanism, state its hypothesis, baseline, metric,
ablation, and required logs. Keep raw observations durable when a later
wave receives compressed Evidence State.

過度な抽象化は避ける。

PoC段階では、

> **読みやすく、測定しやすく、捨てやすいコード**

を優先する。

---

## 24. 推奨初期モジュール構成

言語・フレームワークは実装開始時に決定するが、責務として以下を分離する。

```text
src/
  judges/
      judge interface
      jev adapter
      judge definitions

  graph/
      node
      edge
      activation
      inhibition
      scheduler

  aggregation/
      average
      weighted
      logistic

  runtime/
      execution engine
      parallel executor
      early stopping

  experiments/
      baseline
      dynamic network
      ablation

  data/
      market input
      feature generation
      ground truth

  metrics/
      accuracy
      calibration
      latency
      diversity

  storage/
      experiment log
      prediction log
      judge log

  escalation/
      frontier adapter

tests/
benchmarks/
configs/
docs/
```

実際のディレクトリ構成は実装言語に合わせて変更してよい。

責務分離の意図を維持すること。

---

## 25. 最初に答えるべき研究質問

### RQ1

複数の多様な軽量Judgeは、単一Judgeより高い判断精度を得られるか？

### RQ2

単純な固定ensembleに対して、Dynamic Judge Networkは同等以上の精度をより少ないJudge実行数で実現できるか？

### RQ3

Dynamic Activationは平均レイテンシを削減できるか？

### RQ4

Excitation / Inhibitionは精度または計算効率を改善するか？

### RQ5

Counter-evidence Judgeはerror correlationを低下させるか？

### RQ6

Early Stoppingは精度を大きく損なわずレイテンシを削減できるか？

### RQ7

過去の成功・失敗からJudge間接続を更新すると性能が改善するか？

### RQ8

Accuracy-Coverage trade-offにおいて、単一モデルより優れた領域を形成できるか？

### RQ9

How much marginal accuracy or calibration does each additional
Activation Wave contribute relative to its latency and provider cost?

### RQ10

When later Judges receive compact Evidence State instead of raw state,
what changes in accuracy, calibration, input size, and latency?

### RQ11

Does shared-state speculative batching outperform sparse remote
execution after attempted, fetched, activated, and used counts are
reported separately?

---

## 26. Success criteria

Beating a frontier LLM is not an initial success criterion. Compare the
single Judge, fixed ensembles, and dynamic network on the same samples
and report accuracy at coverage, calibration, `SKIP` rate, latency, and
provider cost. A dynamic configuration is useful if it improves the
measured trade-off, even when one metric alone is not best.

Judge-count savings require a precise denominator. Report attempted
questions and fetched answers as resource measures, and activated and
used Judges as routing measures. A path that uses few Judges but fetches
an entire speculative batch has not established a provider-cost saving.

A negative result is also informative when logs can separate lack of
Judge diversity, correlated errors, routing overhead, excess wave depth,
Evidence State information loss, and aggregation failure.

---

## 27. 長期ビジョン

最終的に目指すものは、

> **問題に応じて必要な小さな知能だけが活性化し、それらが互いに影響しながら判断を形成し、十分な確信に達した時点で思考を停止する推論システム**

である。

The updated target loop is:

```text
Stimulus
   |
   v
Deterministic facts and validity gates
   |
   v
Activation Wave 0 (independent Judges)
   |
   v
Compact Evidence State
   |
   v
Controller: stop, activate, or inhibit
   |
   +---- more evidence ----> later wave / counter-evidence
   |                           |
   |                           +----> Evidence State
   v
Direction + actionability gate
   |
   v
HIGH / LOW / SKIP
   |
   v
Outcome and measurement (future path learning)
```

というループを形成する。

これはTransformer内部のMoEとは異なり、**推論レベルでの動的な計算経路選択**を対象とする。

---

## 28. 一文での定義

> **Dynamic Judge Network is a bio-inspired reasoning architecture that dynamically activates diverse lightweight evaluators, combines their competing evidence, and allocates additional computation only when uncertainty requires it.**

日本語では、

> **Dynamic Judge Networkは、多様な軽量判断器を必要に応じて動的に発火させ、相反する証拠を統合し、不確実な場合にのみ追加計算を投入する、生物の意思決定に着想を得た推論アーキテクチャである。**

---

## 29. 現時点で最も重要なこと

このプロジェクトでは、最初から複雑なAIモデルを作らない。

まず、

```text
Single Task
    |
Multiple Diverse Judges
    |
Fixed Ensemble
    |
Dynamic Activation
    |
Measurement
```

までを実装する。

そして、

> **「動的なJudge Networkに、本当に速度・精度上の利点が存在するか？」**

を実測によって確認する。

その結果を見てから、

- inhibition
- memory
- learned routing
- learned graph
- Small LLM Router
- Frontier escalation
- multi-domain generalization

へ進む。

**Architecture follows evidence.**
