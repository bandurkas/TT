import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const load = async name => {
  const source = readFileSync(new URL(`../src/lib/${name}.ts`, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
};
const { videoSignal, videoWatchUrl } = await load('bridge');

test('a video with no orders is "no sales" regardless of what it carries', () => {
  const byProduct = new Map([[1, { verdict: 'scale' }]]);
  assert.deepEqual(videoSignal({ orders: 0, products: [1] }, byProduct, true), { tone: 'gray', label: 'без продаж' });
});

test('orders plus a scaling product, and nothing losing, is the clearest "invest more" signal', () => {
  const byProduct = new Map([[1, { verdict: 'hold' }], [2, { verdict: 'scale' }]]);
  assert.equal(videoSignal({ orders: 3, products: [1, 2] }, byProduct, true).tone, 'good');
});

test('a scaling product never outvotes a losing one carried by the same video', () => {
  // ad exposure is bought per video, not per product: boosting this video also feeds the
  // "cut" product's loss, so it must not read as a plain "invest more".
  const byProduct = new Map([[1, { verdict: 'cut' }], [2, { verdict: 'scale' }]]);
  const sig = videoSignal({ orders: 3, products: [1, 2] }, byProduct, true);
  assert.equal(sig.tone, 'warn');
  assert.notEqual(sig.label, 'продажи есть — лить бюджет');
});

test('orders plus only hold/cut products never overstate as "invest more"', () => {
  const holdOnly = new Map([[1, { verdict: 'hold' }]]);
  assert.equal(videoSignal({ orders: 1, products: [1] }, holdOnly, false).tone, 'warn');
  const cutOnly = new Map([[1, { verdict: 'cut' }]]);
  assert.equal(videoSignal({ orders: 1, products: [1] }, cutOnly, false).tone, 'bad');
});

test('orders with no linked product verdict is called out, not silently scored', () => {
  const empty = new Map();
  const sig = videoSignal({ orders: 2, products: [] }, empty, false);
  assert.equal(sig.tone, 'gray');
  assert.equal(sig.label, 'sales, product not scored');
});

test('a "no_data" product verdict is missing evidence, not evidence of a loss', () => {
  // no_data means the product itself has no orders/spend measured in the period — it must not
  // read the same as "cut" (a real, measured loss).
  const noData = new Map([[1, { verdict: 'no_data' }]]);
  const sig = videoSignal({ orders: 1, products: [1] }, noData, false);
  assert.equal(sig.tone, 'gray');
  assert.notEqual(sig.label, 'sells, but at a loss');
});

test('watch URL builds from video id alone and falls back when the handle is missing', () => {
  assert.equal(videoWatchUrl({ video_reference: 'user556272867', external_video_id: '7685303303969852673' }),
    'https://www.tiktok.com/@user556272867/video/7685303303969852673');
  assert.equal(videoWatchUrl({ video_reference: null, external_video_id: '123' }),
    'https://www.tiktok.com/@tiktok/video/123');
});
