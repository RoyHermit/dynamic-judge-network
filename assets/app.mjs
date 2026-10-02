import { evaluateScenario } from './simulator.mjs';

const controls = {
  trend: document.getElementById('trend'),
  momentum: document.getElementById('momentum'),
  reversal: document.getElementById('reversal'),
  noise: document.getElementById('noise'),
  completeness: document.getElementById('completeness'),
  maxWaves: document.getElementById('max-waves'),
  speculative: document.getElementById('speculative'),
  routingPolicy: document.getElementById('routing-policy'),
};

const presets = {
  'clear-high': { trend: 85, momentum: 70, reversal: 10, noise: 10, completeness: 95 },
  'clear-low': { trend: -85, momentum: -70, reversal: 10, noise: 10, completeness: 95 },
  conflict: { trend: 70, momentum: -60, reversal: 65, noise: 35, completeness: 90 },
  borderline: { trend: 90, momentum: 10, reversal: 54, noise: 0, completeness: 95 },
  missing: { trend: 75, momentum: 68, reversal: 15, noise: 15, completeness: 25 },
};

const judgeNames = {
  trend: 'Trend',
  momentum: 'Momentum',
  noise: 'Noise',
  'mean-reversion': 'Mean Reversion',
  'counter-high': 'Counter-HIGH',
  'counter-low': 'Counter-LOW',
};

const explanations = {
  'missing-data': 'The validity gate found insufficient data. The system declines to ask a Judge.',
  budget: 'More evidence is needed, but the wave budget is exhausted. The safe outcome is SKIP.',
  'insufficient-evidence': 'The directional evidence remains weak or uncertain after the available waves.',
  'low-actionability': 'A direction is favored, but noise, risk, or disagreement makes actionability too low.',
  'sufficient-evidence': 'Direction and actionability both pass the illustrative stopping rule.',
};

function setText(id, value) {
  document.getElementById(id).textContent = String(value);
}

function readInput() {
  return {
    trend: Number(controls.trend.value),
    momentum: Number(controls.momentum.value),
    reversal: Number(controls.reversal.value),
    noise: Number(controls.noise.value),
    completeness: Number(controls.completeness.value),
    maxWaves: Number(controls.maxWaves.value),
    speculative: controls.speculative.checked,
    routingPolicy: controls.routingPolicy.value,
  };
}

function renderControls(input) {
  setText('trend-value', `${input.trend > 0 ? '+' : ''}${input.trend}`);
  setText('momentum-value', `${input.momentum > 0 ? '+' : ''}${input.momentum}`);
  for (const name of ['reversal', 'noise', 'completeness']) {
    setText(`${name}-value`, `${input[name]}%`);
  }
}

function renderEvidence(evidence) {
  const routing = evidence?.waveZero;
  for (const [name, value] of Object.entries({
    direction: routing?.directionScore ?? null,
    disagreement: routing?.disagreement ?? null,
    uncertainty: routing?.uncertainty ?? null,
  })) {
    setText(`routing-${name}`, value === null ? '—' : `${name === 'direction' && value > 0 ? '+' : ''}${value.toFixed(2)}`);
  }
  const fields = {
    direction: evidence?.directionScore ?? null,
    disagreement: evidence?.disagreement ?? null,
    uncertainty: evidence?.uncertainty ?? null,
    actionability: evidence?.actionability ?? null,
  };
  for (const [name, value] of Object.entries(fields)) {
    const label = value === null ? '—' : `${name === 'direction' && value > 0 ? '+' : ''}${value.toFixed(2)}`;
    setText(`metric-${name}`, label);
    document.getElementById(`bar-${name}`).style.width = value === null ? '0%' : `${Math.abs(value) * 100}%`;
  }
}

function stage(id, state) {
  const element = document.getElementById(id);
  element.classList.remove('is-active', 'is-dormant', 'is-blocked');
  element.classList.add(`is-${state}`);
}

function renderRoute(result) {
  const waveOne = result.waves.find((wave) => wave.index === 1);
  const gateBlocked = result.stopReason === 'missing-data';
  stage('stage-gate', gateBlocked ? 'blocked' : 'active');
  stage('stage-wave0', gateBlocked ? 'dormant' : 'active');
  stage('stage-evidence', gateBlocked ? 'dormant' : 'active');
  stage('stage-wave1', waveOne ? 'active' : result.stopReason === 'budget' ? 'blocked' : 'dormant');
  setText('gate-status', gateBlocked ? 'Insufficient data' : 'Passed');
  setText('wave0-status', gateBlocked ? 'Not run' : '3 activated');
  setText('evidence-status', gateBlocked ? 'Not formed' : 'Summary formed');
  setText('wave1-status', waveOne ? `${waveOne.judges.length} activated` : result.stopReason === 'budget' ? 'Budget stop' : 'Not needed');
  setText('route-summary', `${result.waves.length} wave${result.waves.length === 1 ? '' : 's'}`);
  setText('route-reason', result.routeReason);
  setText('routing-detail', result.routing
    ? `Wave 1 uncertainty check: ${result.routing.uncertainty.toFixed(2)} versus ${result.routing.policy} threshold ${result.routing.threshold.toFixed(2)}. Reversal risk ≥ 0.55 or disagreement ≥ 0.45 also activates Wave 1.`
    : 'The data gate stopped routing before any threshold check.');

  const chipContainer = document.getElementById('judge-chips');
  chipContainer.replaceChildren();
  if (result.activatedJudges.length === 0) {
    const chip = document.createElement('span');
    chip.className = 'judge-chip is-fetched-only';
    chip.textContent = 'No Judge questions sent';
    chipContainer.append(chip);
    return;
  }
  for (const id of result.activatedJudges) {
    const chip = document.createElement('span');
    chip.className = 'judge-chip';
    chip.textContent = judgeNames[id];
    chipContainer.append(chip);
  }
  for (const id of result.fetchedJudges.filter((judge) => !result.activatedJudges.includes(judge))) {
    const chip = document.createElement('span');
    chip.className = 'judge-chip is-fetched-only';
    chip.textContent = `${judgeNames[id]} · fetched only`;
    chipContainer.append(chip);
  }
}

function renderCounts(result) {
  for (const name of ['requested', 'fetched', 'activated', 'used']) {
    setText(`count-${name}`, result.counts[name]);
  }
  setText('request-count', result.counts.providerRequests);
  setText('request-plural', result.counts.providerRequests === 1 ? '' : 's');
  setText('wave-count', result.waves.length);
  setText('wave-plural', result.waves.length === 1 ? '' : 's');
  setText('fixed-count', result.fixedBaseline.questions);
  setText('dynamic-count', result.counts.requested);
  const scale = result.fixedBaseline.questions || 1;
  document.getElementById('fixed-bar').style.width = `${result.fixedBaseline.questions / scale * 100}%`;
  document.getElementById('dynamic-bar').style.width = `${result.counts.requested / scale * 100}%`;
  const saved = result.fixedBaseline.questions - result.counts.requested;
  setText('comparison-note', result.fixedBaseline.questions === 0
    ? 'Both paths stop at the same data sufficiency gate.'
    : saved > 0
      ? `This toy path requested ${saved} fewer question${saved === 1 ? '' : 's'}. No quality or cost gain has been measured.`
      : 'This path requested the full fixed question set. No question-count saving in this scenario.');
}

function renderTrace(trace) {
  const list = document.getElementById('trace-list');
  list.replaceChildren();
  for (const item of trace) {
    const row = document.createElement('li');
    const title = document.createElement('strong');
    const detail = document.createElement('span');
    title.textContent = item.title;
    detail.textContent = item.detail;
    row.append(title, detail);
    list.append(row);
  }
}

function render() {
  const input = readInput();
  const result = evaluateScenario(input);
  renderControls(input);
  const verdict = document.getElementById('verdict-card');
  verdict.dataset.decision = result.decision;
  setText('decision', result.decision);
  setText('verdict-path', result.waves.length === 0 ? 'Gate stop' : result.stopReason === 'budget' ? 'Budget stop' : `Wave ${result.waves.length - 1} stop`);
  setText('decision-explanation', explanations[result.stopReason]);
  renderRoute(result);
  renderEvidence(result.evidence);
  renderCounts(result);
  renderTrace(result.trace);
}

for (const [name, control] of Object.entries(controls)) {
  control.addEventListener('input', () => {
    if (['trend', 'momentum', 'reversal', 'noise', 'completeness'].includes(name)) {
      for (const button of document.querySelectorAll('[data-preset]')) {
        button.classList.remove('is-selected');
        button.setAttribute('aria-pressed', 'false');
      }
    }
    render();
  });
}

for (const button of document.querySelectorAll('[data-preset]')) {
  button.setAttribute('aria-pressed', String(button.dataset.preset === 'clear-high'));
  button.addEventListener('click', () => {
    for (const [name, value] of Object.entries(presets[button.dataset.preset])) {
      controls[name].value = value;
    }
    for (const candidate of document.querySelectorAll('[data-preset]')) {
      const selected = candidate === button;
      candidate.classList.toggle('is-selected', selected);
      candidate.setAttribute('aria-pressed', String(selected));
    }
    render();
  });
}

render();
