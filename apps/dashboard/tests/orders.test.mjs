import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const load = async name => {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
};
const { orderMoney, orderText } = await load('orders');
const { demoOrders, demoOrderPage } = await load('order-mock');
const all = demoOrders(JSON.parse(readFileSync(new URL('../fixtures/orders.json', import.meta.url), 'utf8')));

test('full stored money preserves large integer and fractional precision without abbreviations', () => {
  assert.equal(orderMoney('9007199254740993.123456', 'en', 'USD'), 'USD 9,007,199,254,740,993.123456');
  assert.equal(orderMoney('-2500000.000000', 'en'), '−Rp 2,500,000');
  assert.equal(orderMoney('-0.000000', 'en'), 'Rp 0');
  assert.equal(orderMoney(null, 'ru'), '—');
  assert.equal(orderMoney('NaN', 'en'), '—');
});

test('every financial line and warning has Russian and English descriptions', () => {
  for (const o of all) {
    for (const line of o.lines) assert.notEqual(orderText('ru', line.key), line.key);
    for (const w of o.warnings) assert.notEqual(orderText('ru', `warning_${w}`), `warning_${w}`);
  }
  assert.match(orderText('ru', 'fee_residual'), /без отдельной разбивки/);
});

test('demo totals use all matches, independent of page, and do not include missing calculations', () => {
  const first = demoOrderPage(all, new URLSearchParams('limit=1'));
  const next = demoOrderPage(all, new URLSearchParams('limit=1&offset=1'));
  assert.deepEqual(first.summary, next.summary);
  assert.equal(first.total, 34);
  assert.equal(first.summary.missing_orders, 7);
  assert.equal(first.rows.length, 1);
  assert.notEqual(first.rows[0].id, next.rows[0].id);
});

test('demo search, final, loss, date, empty and missing-data filters work', () => {
  const find = q => demoOrderPage(all, new URLSearchParams(q));
  assert.equal(find('search=DEMO-000001').total, 1);
  assert.equal(find('search=does-not-exist').total, 0);
  assert.equal(find('search=комплектация').total, 34);
  assert.ok(find('loss_only=true').rows.every(o => o.amounts.net_profit.startsWith('-')));
  assert.ok(find('state=final').rows.every(o => o.state === 'final'));
  assert.equal(find('from=2026-09-01&to=2026-09-02').total, 0);
  const missing = find('state=not_calculated');
  assert.equal(missing.summary.calculated_orders, 0);
  assert.equal(missing.summary.profit_share, null);
});
