import assert from 'node:assert/strict';
import test from 'node:test';
import { emitModelTiming } from './model-timing.ts';

test('model timing is opt-in and emits only whitelisted aggregate fields', () => {
  const lines = [];
  emitModelTiming({
    phase: 'response_parsed',
    requestKind: 'general_requirement_extraction',
    batchPageCount: 3,
    inputCharacters: 16_000,
    requestHeadersWaitMs: 1_200,
    responseBodyAndEnvelopeMs: 35_000,
    jsonParseMs: 4,
    responseStatus: 200,
    responseCharacters: 40_000,
    promptTokens: 9_000,
    completionTokens: 4_000,
    totalTokens: 13_000,
    sourceText: 'must never be logged',
    filename: 'private.pdf',
  }, (line) => lines.push(line), true);

  assert.equal(lines.length, 1);
  assert.match(lines[0], /^\[TCE_MODEL_TIMING\] /);
  const record = JSON.parse(lines[0].slice('[TCE_MODEL_TIMING] '.length));
  assert.deepEqual(record, {
    phase: 'response_parsed',
    requestKind: 'general_requirement_extraction',
    batchPageCount: 3,
    inputCharacters: 16_000,
    requestHeadersWaitMs: 1_200,
    responseBodyAndEnvelopeMs: 35_000,
    jsonParseMs: 4,
    responseStatus: 200,
    responseCharacters: 40_000,
    promptTokens: 9_000,
    completionTokens: 4_000,
    totalTokens: 13_000,
  });
});

test('model timing emits nothing when disabled', () => {
  const lines = [];
  emitModelTiming({
    phase: 'headers_received',
    requestKind: 'general_requirement_extraction',
    batchPageCount: 1,
    inputCharacters: 100,
    responseStatus: 200,
  }, (line) => lines.push(line), false);
  assert.deepEqual(lines, []);
});
