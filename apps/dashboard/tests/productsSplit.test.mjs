import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const load = async name => {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
};
const { sortProducts, filterProducts, marginTone } = await load('productsSplit');

const row = (id, title, overrides = {}) => ({
  product_id: id, title, external_product_id: null, units: 0, orders: 0, gmv: '0',
  net_seller_revenue: '0', fees: '0', affiliate: '0', cogs: '0', ad_cost: null,
  ad_cost_is_estimate: false, refunds: '0', net_profit: null, net_margin: null,
  cvr: null, ctr: null, status: 'WATCH', status_reason: '', ...overrides,
});

test('sortProducts orders descending by the given numeric key', () => {
  const rows = [row(1, 'A', { net_profit: '100' }), row(2, 'B', { net_profit: '300' }), row(3, 'C', { net_profit: '-50' })];
  assert.deepEqual(sortProducts(rows, 'net_profit').map((r) => r.product_id), [2, 1, 3]);
});

test('sortProducts sinks unmeasured (null) values to the bottom regardless of sign of the rest', () => {
  const rows = [row(1, 'A', { net_margin: '-0.9' }), row(2, 'B', { net_margin: null }), row(3, 'C', { net_margin: '0.4' })];
  assert.deepEqual(sortProducts(rows, 'net_margin').map((r) => r.product_id), [3, 1, 2]);
});

test('sortProducts is stable/no-throw when every row has a null value for the key', () => {
  const rows = [row(1, 'A'), row(2, 'B')];
  assert.deepEqual(sortProducts(rows, 'cvr').map((r) => r.product_id), [1, 2]);
});

test('filterProducts matches title case-insensitively', () => {
  const rows = [row(1, 'Quarter Crew Socks'), row(2, 'Ankle Pack')];
  assert.deepEqual(filterProducts(rows, 'crew').map((r) => r.product_id), [1]);
  assert.deepEqual(filterProducts(rows, 'QUARTER').map((r) => r.product_id), [1]);
});

test('filterProducts with blank/whitespace query returns all rows unchanged', () => {
  const rows = [row(1, 'A'), row(2, 'B')];
  assert.deepEqual(filterProducts(rows, '   ').map((r) => r.product_id), [1, 2]);
});

test('filterProducts with no match returns an empty list', () => {
  const rows = [row(1, 'Quarter Crew Socks')];
  assert.deepEqual(filterProducts(rows, 'zzz'), []);
});

test('marginTone grades by magnitude: null untoned, negative bad, thin-but-positive warn, healthy good', () => {
  assert.equal(marginTone(null), '');
  assert.equal(marginTone(-0.05), 'dn');
  assert.equal(marginTone(0.1), 'wn');
  assert.equal(marginTone(0.3), 'up');
});

test('marginTone treats exactly 0% and exactly 15% as the lower tier, not rounded up', () => {
  assert.equal(marginTone(0), 'wn');
  assert.equal(marginTone(0.15), 'up');
});
