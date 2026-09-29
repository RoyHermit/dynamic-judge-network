import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateScenario } from '../assets/simulator.mjs';

const clearHigh = {
  trend: 85,
  momentum: 70,
  reversal: 10,
  noise: 10,
  completeness: 95,
  maxWaves: 2,
  speculative: false,
};

test('missing data stops before any Judge question', () => {
  const result = evaluateScenario({ ...clearHigh, completeness: 25 });
  assert.equal(result.decision, 'SKIP');
  assert.equal(result.stopReason, 'missing-data');
  assert.equal(result.waves.length, 0);
  assert.deepEqual(result.counts, {
    requested: 0, fetched: 0, activated: 0, used: 0, providerRequests: 0,
  });
});

test('an unavailable feature is missing evidence, not a neutral signal', () => {
  const result = evaluateScenario({ ...clearHigh, momentum: undefined });
  assert.equal(result.decision, 'SKIP');
  assert.equal(result.stopReason, 'missing-data');
  assert.equal(result.counts.requested, 0);
  assert.equal(result.fixedBaseline.questions, 0);
});

test('clear directional evidence stops after Wave 0', () => {
  const high = evaluateScenario(clearHigh);
  const low = evaluateScenario({ ...clearHigh, trend: -85, momentum: -70 });
  assert.equal(high.decision, 'HIGH');
  assert.equal(low.decision, 'LOW');
  assert.equal(high.waves.length, 1);
  assert.deepEqual(high.counts, {
    requested: 3, fetched: 3, activated: 3, used: 3, providerRequests: 1,
  });
});

test('conflicting evidence activates a counter Judge and can still SKIP', () => {
  const result = evaluateScenario({
    ...clearHigh, trend: 70, momentum: -60, reversal: 65, noise: 35,
  });
  assert.equal(result.waves.length, 2);
  assert.ok(result.waves[1].judges.includes('counter-high'));
  assert.ok(result.waves[1].judges.includes('mean-reversion'));
  assert.equal(result.decision, 'SKIP');
  assert.equal(result.counts.providerRequests, 2);
});

test('a one-wave budget does not force a weak decision', () => {
  const result = evaluateScenario({
    ...clearHigh, trend: 45, momentum: 20, reversal: 70, noise: 55, maxWaves: 1,
  });
  assert.equal(result.decision, 'SKIP');
  assert.equal(result.stopReason, 'budget');
  assert.equal(result.waves.length, 1);
});

test('speculative fetch is charged even when the answer is not activated', () => {
  const result = evaluateScenario({ ...clearHigh, speculative: true });
  assert.equal(result.decision, 'HIGH');
  assert.deepEqual(result.counts, {
    requested: 4, fetched: 4, activated: 3, used: 3, providerRequests: 1,
  });
  assert.ok(result.fetchedJudges.includes('mean-reversion'));
  assert.ok(!result.activatedJudges.includes('mean-reversion'));
});

test('fixed comparator includes both directional counter Judges on every valid input', () => {
  const result = evaluateScenario(clearHigh);
  assert.equal(result.fixedBaseline.questions, 6);
  assert.ok(result.fixedBaseline.judges.includes('counter-high'));
  assert.ok(result.fixedBaseline.judges.includes('counter-low'));
});
