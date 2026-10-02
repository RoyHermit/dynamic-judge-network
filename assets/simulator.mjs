// An inspectable teaching model. These rules and scores are illustrative;
// they are not Jev outputs, calibrated probabilities, or research results.
const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const round = (value) => Math.round(value * 100) / 100;
const fixedJudgeIds = ['trend', 'momentum', 'noise', 'mean-reversion', 'counter-high', 'counter-low'];
const boundedInput = (value, min, max) =>
  value === null || value === undefined || value === '' || !Number.isFinite(Number(value))
    ? null
    : clamp(Number(value), min, max);

export function evaluateScenario(rawInput) {
  const input = {
    trend: boundedInput(rawInput.trend, -100, 100),
    momentum: boundedInput(rawInput.momentum, -100, 100),
    reversal: boundedInput(rawInput.reversal, 0, 100),
    noise: boundedInput(rawInput.noise, 0, 100),
    completeness: boundedInput(rawInput.completeness, 0, 100),
    maxWaves: Number(rawInput.maxWaves) === 1 ? 1 : 2,
    speculative: Boolean(rawInput.speculative),
    routingPolicy: rawInput.routingPolicy === 'adaptive' ? 'adaptive' : 'fixed',
  };
  const missingFeature = ['trend', 'momentum', 'reversal', 'noise', 'completeness']
    .some((name) => input[name] === null);
  const gatePassed = !missingFeature && input.completeness >= 40;
  const waves = [];
  const fetchedJudges = [];
  const activatedJudges = [];
  const usedJudges = [];
  const trace = [];
  let providerRequests = 0;
  let routing = null;

  function recordWave(index, judges, newlyFetched, reason) {
    waves.push({ index, judges, newlyFetched, reason });
    providerRequests += 1;
    for (const judge of newlyFetched) {
      if (!fetchedJudges.includes(judge)) fetchedJudges.push(judge);
    }
    for (const judge of judges) {
      if (!activatedJudges.includes(judge)) activatedJudges.push(judge);
      if (!usedJudges.includes(judge)) usedJudges.push(judge);
    }
  }

  function finish(decision, stopReason, evidence, routeReason) {
    return {
      input,
      decision,
      stopReason,
      routeReason,
      routing,
      evidence,
      waves,
      trace,
      fetchedJudges,
      activatedJudges,
      usedJudges,
      counts: {
        requested: fetchedJudges.length,
        fetched: fetchedJudges.length,
        activated: activatedJudges.length,
        used: usedJudges.length,
        providerRequests,
      },
      fixedBaseline: {
        judges: gatePassed ? [...fixedJudgeIds] : [],
        questions: gatePassed ? fixedJudgeIds.length : 0,
        providerRequests: gatePassed ? 1 : 0,
      },
    };
  }

  if (!gatePassed) {
    trace.push({
      title: 'Deterministic gate',
      detail: missingFeature
        ? 'A required feature is missing or invalid; no Judge question is sent.'
        : 'Data completeness is below 40%; no Judge question is sent.',
    });
    return finish('SKIP', 'missing-data', null, 'The input is incomplete.');
  }
  trace.push({ title: 'Deterministic gate', detail: 'Input passes the data sufficiency check.' });

  const waveZeroJudges = ['trend', 'momentum', 'noise'];
  const waveZeroFetched = input.speculative
    ? [...waveZeroJudges, 'mean-reversion']
    : waveZeroJudges;
  recordWave(0, waveZeroJudges, waveZeroFetched, 'Initial independent judgments');
  trace.push({
    title: 'Wave 0',
    detail: input.speculative
      ? 'Trend, Momentum, and Noise are activated. Mean Reversion is fetched speculatively.'
      : 'Trend, Momentum, and Noise share one illustrative provider request.',
  });

  const trend = input.trend / 100;
  const momentum = input.momentum / 100;
  const reversal = input.reversal / 100;
  const noise = input.noise / 100;
  const disagreement = Math.abs(trend - momentum) / 2;
  let directionScore = 0.55 * trend + 0.45 * momentum;
  let uncertainty = clamp(1 - Math.abs(directionScore) + 0.25 * noise + 0.125 * disagreement);
  const preliminaryDirection = directionScore >= 0 ? 'HIGH' : 'LOW';
  const waveZeroEvidence = {
    directionScore: round(directionScore),
    disagreement: round(disagreement),
    uncertainty: round(uncertainty),
  };
  const threshold = input.routingPolicy === 'adaptive'
    ? clamp(0.55 + 0.05 * Math.abs(directionScore) - 0.12 * reversal - 0.10 * disagreement, 0.40, 0.65)
    : 0.55;
  const triggers = [];
  if (uncertainty >= threshold) triggers.push('uncertainty');
  if (reversal >= 0.55) triggers.push('reversal risk');
  if (disagreement >= 0.45) triggers.push('Judge disagreement');
  const needsMoreEvidence = triggers.length > 0;
  routing = {
    policy: input.routingPolicy,
    uncertainty: round(uncertainty),
    threshold: round(threshold),
    triggers,
  };
  const routeReason = needsMoreEvidence
    ? `Wave 1 is requested by ${triggers.join(', ')} under the ${input.routingPolicy} routing rule.`
    : `No Wave 1 trigger fired under the ${input.routingPolicy} routing rule.`;

  if (needsMoreEvidence && input.maxWaves === 1) {
    trace.push({ title: 'Stop', detail: 'More evidence is needed, but the wave budget is exhausted. Return SKIP.' });
    return finish('SKIP', 'budget', {
      ...waveZeroEvidence,
      actionability: null,
      waveZero: waveZeroEvidence,
    }, 'More evidence is needed, but the wave budget is exhausted.');
  }

  let counterStrength = 0;
  if (needsMoreEvidence) {
    const counterJudge = preliminaryDirection === 'HIGH' ? 'counter-high' : 'counter-low';
    const waveOneJudges = [counterJudge];
    if (input.reversal >= 45 || input.noise >= 55) waveOneJudges.push('mean-reversion');
    const newlyFetched = waveOneJudges.filter((judge) => !fetchedJudges.includes(judge));
    recordWave(1, waveOneJudges, newlyFetched, routeReason);
    trace.push({
      title: 'Wave 1',
      detail: `The controller activates ${waveOneJudges.map((judge) => judge.replaceAll('-', ' ')).join(' and ')} against the ${preliminaryDirection} hypothesis.`,
    });
    counterStrength = clamp(0.5 * reversal + 0.25 * noise + 0.25 * disagreement);
    const sign = preliminaryDirection === 'HIGH' ? 1 : -1;
    directionScore -= sign * 0.32 * counterStrength;
    if (waveOneJudges.includes('mean-reversion')) directionScore -= sign * 0.18 * reversal;
    uncertainty = clamp(1 - Math.abs(directionScore) + 0.25 * noise + 0.125 * disagreement + 0.15 * counterStrength);
  }

  const actionability = clamp(
    1 - 0.35 * noise - 0.28 * reversal - 0.25 * disagreement
      - 0.12 * (1 - input.completeness / 100) - 0.12 * counterStrength,
  );
  const evidence = {
    directionScore: round(directionScore),
    disagreement: round(disagreement),
    uncertainty: round(uncertainty),
    actionability: round(actionability),
    waveZero: waveZeroEvidence,
  };

  let decision;
  let stopReason;
  if (Math.abs(directionScore) < 0.34 || uncertainty > 0.68) {
    decision = 'SKIP';
    stopReason = 'insufficient-evidence';
  } else if (actionability < 0.55) {
    decision = 'SKIP';
    stopReason = 'low-actionability';
  } else {
    decision = directionScore > 0 ? 'HIGH' : 'LOW';
    stopReason = 'sufficient-evidence';
  }
  trace.push({
    title: 'Direction + actionability',
    detail: decision === 'SKIP'
      ? 'The directional evidence or actionability gate is insufficient; decline to act.'
      : `The evidence supports ${decision} and passes the actionability gate.`,
  });
  return finish(decision, stopReason, evidence, routeReason);
}
