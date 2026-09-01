import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/errors.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { readableError, ApiError } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

const res = (body, status = 422) => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status });

test('a plain FastAPI detail string is not confirmable', async () => {
  assert.deepEqual(await readableError(res({ detail: 'A newer or equal observation for this day already exists' })),
    { message: 'A newer or equal observation for this day already exists', confirmable: false });
});

test('pydantic validation arrays keep naming the offending field', async () => {
  assert.deepEqual(await readableError(res({ detail: [{ loc: ['body', 'cost'], msg: 'greater than or equal to 0' }] })),
    { message: 'cost: greater than or equal to 0', confirmable: false });
});

test('a sanity-check rejection is readable and marked confirmable', async () => {
  assert.deepEqual(await readableError(res({ detail: { message: 'looks like period totals', confirmable: true } })),
    { message: 'looks like period totals', confirmable: true });
});

test('an object detail without the flag never becomes confirmable by accident', async () => {
  for (const detail of [{ message: 'x' }, { message: 'x', confirmable: 'true' }, { message: 'x', confirmable: 1 }])
    assert.equal((await readableError(res({ detail }))).confirmable, false);
});

test('non-JSON and empty bodies fall back to text, then status', async () => {
  assert.deepEqual(await readableError(res('<html>502</html>', 502)), { message: '<html>502</html>', confirmable: false });
  assert.equal((await readableError(res('', 500))).message.length > 0, true);
});

test('ApiError carries the flag so callers can offer an override', () => {
  assert.equal(new ApiError(422, 'x', true).confirmable, true);
  assert.equal(new ApiError(422, 'x').confirmable, false);
});
