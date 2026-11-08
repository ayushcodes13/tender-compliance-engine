import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveClientMaxFileBytes, resolveMaxFileBytes, MAX_FILE_BYTES, LOCAL_MAX_FILE_BYTES } from './upload-limits.ts';

test('resolveClientMaxFileBytes matches the configured deployment upload ceiling', () => {
  assert.equal(resolveClientMaxFileBytes(String(LOCAL_MAX_FILE_BYTES), 'production'), LOCAL_MAX_FILE_BYTES);
  assert.equal(resolveClientMaxFileBytes(String(MAX_FILE_BYTES), 'production'), MAX_FILE_BYTES);
});

test('resolveClientMaxFileBytes falls back to local and Vercel limits by build environment', () => {
  assert.equal(resolveClientMaxFileBytes(undefined, 'development'), LOCAL_MAX_FILE_BYTES);
  assert.equal(resolveClientMaxFileBytes(undefined, 'production'), MAX_FILE_BYTES);
  assert.equal(resolveClientMaxFileBytes('invalid', 'production'), MAX_FILE_BYTES);
});

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
