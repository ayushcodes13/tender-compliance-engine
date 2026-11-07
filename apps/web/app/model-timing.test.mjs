import assert from 'node:assert/strict';
import test from 'node:test';
import { emitModelTiming } from './model-timing.ts';

test('model timing is opt-in and emits only whitelisted aggregate fields', () => {
  const lines = [];
  emitModelTiming({
    phase: 'response_parsed',
    requestKind: 'general_requirement_extraction',
    batchIndex: 2,
    totalBatches: 3,
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
    batchIndex: 2,
    totalBatches: 3,
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

test('request-start timing identifies incomplete coverage requests without content', () => {
  const lines = [];
  emitModelTiming({
    phase: 'request_started',
    requestKind: 'text_page_omission_audit',
    batchIndex: 1,
    totalBatches: 4,
    batchPageCount: 2,
    inputCharacters: 8_000,
    sourceText: 'must not be logged',
  }, (line) => lines.push(line), true);

  assert.deepEqual(JSON.parse(lines[0].slice('[TCE_MODEL_TIMING] '.length)), {
    phase: 'request_started',
    requestKind: 'text_page_omission_audit',
    batchIndex: 1,
    totalBatches: 4,
    batchPageCount: 2,
    inputCharacters: 8_000,
  });
});

test('vector timing records only numeric page and request metadata', () => {
  const lines = [];
  emitModelTiming({
    phase: 'request_started',
    requestKind: 'vector_table_row_classification',
    pageNumber: 7,
    batchPageCount: 1,
    inputCharacters: 12_345,
    sourceCells: ['secret source content'],
  }, (line) => lines.push(line), true);

  assert.deepEqual(JSON.parse(lines[0].slice('[TCE_MODEL_TIMING] '.length)), {
    phase: 'request_started',
    requestKind: 'vector_table_row_classification',
    pageNumber: 7,
    batchPageCount: 1,
    inputCharacters: 12_345,
  });
});

test('vector request failure logs use a bounded enum and never an error message', () => {
  const lines = [];
  emitModelTiming({
    phase: 'request_failed',
    requestKind: 'vector_table_row_classification',
    pageNumber: 11,
    batchPageCount: 1,
    inputCharacters: 1_131,
    requestHeadersWaitMs: 90_000,
    failureKind: 'provider_connection',
    error: 'sensitive provider response text',
  }, (line) => lines.push(line), true);

  assert.deepEqual(JSON.parse(lines[0].slice('[TCE_MODEL_TIMING] '.length)), {
    phase: 'request_failed',
    requestKind: 'vector_table_row_classification',
    failureKind: 'provider_connection',
    pageNumber: 11,
    batchPageCount: 1,
    inputCharacters: 1_131,
    requestHeadersWaitMs: 90_000,
  });
});

test('vector response timing includes safe parse, response-size, and provider-usage fields', () => {
  const lines = [];
  emitModelTiming({
    phase: 'response_parsed',
    requestKind: 'vector_source_row_audit',
    batchIndex: 2,
    totalBatches: 4,
    pageNumber: 11,
    batchPageCount: 1,
    inputCharacters: 2_400,
    requestHeadersWaitMs: 8_000,
    responseBodyAndEnvelopeMs: 12,
    jsonParseMs: 1,
    responseStatus: 200,
    responseCharacters: 120,
    promptTokens: 800,
    completionTokens: 100,
    totalTokens: 900,
    responseBody: 'must never be logged',
  }, (line) => lines.push(line), true);

  assert.deepEqual(JSON.parse(lines[0].slice('[TCE_MODEL_TIMING] '.length)), {
    phase: 'response_parsed',
    requestKind: 'vector_source_row_audit',
    batchIndex: 2,
    totalBatches: 4,
    pageNumber: 11,
    batchPageCount: 1,
    inputCharacters: 2_400,
    requestHeadersWaitMs: 8_000,
    responseBodyAndEnvelopeMs: 12,
    jsonParseMs: 1,
    responseStatus: 200,
    responseCharacters: 120,
    promptTokens: 800,
    completionTokens: 100,
    totalTokens: 900,
  });
});

test('page-routing response timing records bounded request and usage metadata only', () => {
  const lines = [];
  emitModelTiming({
    phase: 'response_parsed',
    requestKind: 'page_routing',
    batchIndex: 1,
    totalBatches: 2,
    batchPageCount: 8,
    inputCharacters: 18_000,
    requestHeadersWaitMs: 32_000,
    responseBodyAndEnvelopeMs: 3,
    jsonParseMs: 1,
    responseStatus: 200,
    responseCharacters: 2_400,
    promptTokens: 8_000,
    completionTokens: 600,
    totalTokens: 8_600,
    pageReasons: ['private tender content'],
  }, (line) => lines.push(line), true);

  const record = JSON.parse(lines[0].slice('[TCE_MODEL_TIMING] '.length));
  assert.equal(record.requestKind, 'page_routing');
  assert.equal(record.batchPageCount, 8);
  assert.equal(record.totalTokens, 8_600);
  assert.equal('pageReasons' in record, false);
});
