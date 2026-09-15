import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const load = async name => {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
};
const { bestProducts, worstProducts, bestVideos, worstVideos } = await load('performers');

const product = (id, status, net_profit) => ({ product_id: id, status, net_profit: String(net_profit) });
const video = (id, classification) => ({ video_id: id, classification });

test('best products are SCALE/HEALTHY sorted by profit, worst are REDUCE/INVESTIGATE by loss', () => {
  const rows = [product(1, 'SCALE', 100), product(2, 'HEALTHY', 300), product(3, 'REDUCE', -500),
                product(4, 'WATCH', 50), product(5, 'INVESTIGATE', -50)];
  assert.deepEqual(bestProducts(rows).map((r) => r.product_id), [2, 1]);
  assert.deepEqual(worstProducts(rows).map((r) => r.product_id), [3, 5]);
});

test('best/worst product lists respect the n limit', () => {
  const rows = [product(1, 'SCALE', 10), product(2, 'SCALE', 20), product(3, 'SCALE', 30)];
  assert.equal(bestProducts(rows, 2).length, 2);
});

test('WATCH/SMALL_SAMPLE products appear in neither list — no measured evidence either way', () => {
  const rows = [product(1, 'WATCH', -10), product(2, 'SMALL_SAMPLE', -20)];
  assert.equal(bestProducts(rows).length, 0);
  assert.equal(worstProducts(rows).length, 0);
});

test('an INVESTIGATE row with unmeasured (null) profit is not silently treated as a known break-even', () => {
  // product_status() sets INVESTIGATE with net_profit=null when profit inputs are missing or
  // preliminary — that must outrank a real REDUCE loss (a known -1), not tie or lose to it.
  const rows = [
    { product_id: 1, status: 'REDUCE', net_profit: '-1' },
    { product_id: 2, status: 'INVESTIGATE', net_profit: null },
    { product_id: 3, status: 'REDUCE', net_profit: '-5' },
  ];
  assert.deepEqual(worstProducts(rows).map((r) => r.product_id), [2, 3, 1]);
});

test('best videos are WINNER/PROMISING, worst are LOSER/FATIGUING/TRAFFIC_NO_SALES', () => {
  // video_cards() sorts ascending severity within the worst group (TRAFFIC_NO_SALES, then
  // FATIGUING, then LOSER) — this fixture matches that real backend order, not a convenient one.
  const cards = [video(1, 'WINNER'), video(2, 'NEUTRAL'), video(4, 'PROMISING'), video(6, 'TRAFFIC_NO_SALES'), video(5, 'FATIGUING'), video(3, 'LOSER')];
  assert.deepEqual(bestVideos(cards).map((c) => c.video_id), [1, 4]);
  assert.deepEqual(worstVideos(cards).map((c) => c.video_id), [3, 5, 6]);
});

test('worst videos surfaces the most severe class first, not just the first n in source order', () => {
  // regression: 5 mild TRAFFIC_NO_SALES videos ahead of 2 true LOSER videos in the backend's
  // best-to-worst order must not push the LOSER videos past the default n=5 cutoff.
  const cards = [
    video(101, 'TRAFFIC_NO_SALES'), video(102, 'TRAFFIC_NO_SALES'), video(103, 'TRAFFIC_NO_SALES'),
    video(104, 'TRAFFIC_NO_SALES'), video(105, 'TRAFFIC_NO_SALES'),
    video(201, 'LOSER'), video(202, 'LOSER'),
  ];
  const worst = worstVideos(cards).map((c) => c.video_id);
  assert.ok(worst.includes(201) && worst.includes(202), `LOSER videos dropped: ${worst}`);
  assert.deepEqual(worst.slice(0, 2), [202, 201]);
});

test('INSUFFICIENT_DATA/LOW_ATTENTION/WATCH videos are excluded from worst — inconclusive, not a measured loss', () => {
  const cards = [video(1, 'INSUFFICIENT_DATA'), video(2, 'LOW_ATTENTION'), video(3, 'WATCH')];
  assert.equal(worstVideos(cards).length, 0);
});
