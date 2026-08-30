import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/kpi.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { kpiChange } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const card = { key: 'net_margin', kind: 'pct', value: '0.287', prev: '0.470', change_abs: '-0.183', change_pct: '-0.389' };

test('falling positive margin is deterioration; rate difference uses percentage points', () => {
  assert.deepEqual(kpiChange(card), { raw: '-0.183', points: true, direction: -0.183, tone: 'dn' });
});
test('rising refunds from zero are deterioration, not a green threshold status', () => {
  const change = kpiChange({ ...card, key: 'refund_rate', prev: '0', value: '0.0125', change_abs: '0.0125', change_pct: null });
  assert.equal(change.tone, 'dn');
  assert.equal(change.raw, '0.0125');
  assert.equal(change.points, true);
});
test('falling refunds improve; unchanged rates remain neutral', () => {
  assert.equal(kpiChange({ ...card, key: 'refund_rate' }).tone, 'up');
  assert.equal(kpiChange({ ...card, change_abs: '0' }).tone, 'muted');
});
test('advertising spend has no automatic good/bad direction', () => {
  assert.equal(kpiChange({ ...card, key: 'ad_spend', kind: 'money' }).tone, 'muted');
});
test('money uses the API relative change; an improving loss is positive', () => {
  const change = kpiChange({ ...card, key: 'net_profit', kind: 'money', value: '-50', prev: '-100', change_abs: '50', change_pct: '0.5' });
  assert.equal(change.raw, '0.5');
  assert.equal(change.points, false);
  assert.equal(change.tone, 'up');
});
test('missing or invalid comparison never appears as zero change', () => {
  assert.equal(kpiChange({ ...card, prev: null }), null);
  assert.equal(kpiChange({ ...card, value: null }), null);
  assert.equal(kpiChange({ ...card, change_abs: null }), null);
  assert.equal(kpiChange({ ...card, change_abs: 'NaN' }), null);
});
