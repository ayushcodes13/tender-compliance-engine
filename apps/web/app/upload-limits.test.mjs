import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveMaxFileBytes, MAX_FILE_BYTES, LOCAL_MAX_FILE_BYTES } from './upload-limits.ts';

test('resolveMaxFileBytes defaults to 32 MB for local development and on-premise runs', () => {
  const bytes = resolveMaxFileBytes({});
  assert.equal(bytes, 32 * 1024 * 1024);
  assert.equal(bytes, LOCAL_MAX_FILE_BYTES);
});

test('resolveMaxFileBytes enforces 4 MB limit on hosted Vercel environments', () => {
  assert.equal(resolveMaxFileBytes({ VERCEL: '1' }), 4 * 1024 * 1024);
  assert.equal(resolveMaxFileBytes({ VERCEL_ENV: 'preview' }), 4 * 1024 * 1024);
  assert.equal(resolveMaxFileBytes({ VERCEL_ENV: 'production' }), 4 * 1024 * 1024);
  assert.equal(resolveMaxFileBytes({ VERCEL: '1' }), MAX_FILE_BYTES);
});

test('resolveMaxFileBytes respects explicit MAX_FILE_BYTES override', () => {
  const customLimit = 16 * 1024 * 1024;
  assert.equal(resolveMaxFileBytes({ MAX_FILE_BYTES: String(customLimit) }), customLimit);
  assert.equal(resolveMaxFileBytes({ VERCEL: '1', MAX_FILE_BYTES: String(customLimit) }), customLimit);
});
