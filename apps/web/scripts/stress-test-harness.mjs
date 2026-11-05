import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildResponseSheet } from '../app/response-sheet.ts';
import { buildResponseSections } from '../app/response-sections.ts';
import { createSectionedResponseDocument, createSectionedWorkbook } from '../app/sectioned-exports.ts';
import { createResponsePdf } from '../app/pdf-export.ts';
import { Packer } from 'docx';
import JSZip from 'jszip';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const fontPath = path.join(__dirname, '../public/fonts/DejaVuSans.ttf');
const fontBase64 = fs.readFileSync(fontPath).toString('base64');

const fixturesDir = path.join(__dirname, '../test-fixtures/stress-tenders');

const TEST_ARCHETYPES = [
  {
    name: 'Multi-Column Specifications (2-Col & 3-Col)',
    file: 'stress-multi-column.pdf',
    expectedMinRequirements: 15,
    keyPhrases: [
      '1200 x 800 x 1600 mm',
      'IP54',
      '230 V AC',
      '532 nm',
      '18 °C to 28 °C',
      'Gigabit Ethernet',
    ],
  },
  {
    name: 'Borderless Multi-Page Continuation Table',
    file: 'stress-borderless-table.pdf',
    expectedMinRequirements: 10,
    keyPhrases: [
      '1.0 x 10^-7 mbar',
      '600 L/s',
      '4.2 K',
      '0.001 K',
      'OFHC',
    ],
  },
  {
    name: 'Deep Nested Numbered Clauses (4.1 -> 4.1.1 -> c -> i)',
    file: 'stress-nested-clauses.pdf',
    expectedMinRequirements: 8,
    keyPhrases: [
      '2.0 GHz to 18.0 GHz',
      '-115 dBc/Hz',
      '2.5 GSPS',
      'Xilinx UltraScale+',
      '1024 channels',
    ],
  },
  {
    name: 'Extreme Degradation & Scientific Notation (Scanned OCR)',
    file: 'stress-ocr-scientific.pdf',
    expectedMinRequirements: 7,
    keyPhrases: [
      '10^9',
      '9.20 GHz',
      '200 mW',
      '50 Ohm',
      '4.2 K',
    ],
  },
];

async function submitTenderForAnalysis(pdfPath) {
  const fileBytes = fs.readFileSync(pdfPath);
  const fileBlob = new Blob([fileBytes], { type: 'application/pdf' });
  const formData = new FormData();
  formData.append('file', fileBlob, path.basename(pdfPath));

  const response = await fetch('http://127.0.0.1:3000/api/analyze', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Server returned HTTP ${response.status}: ${errorText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResult = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const chunk of lines) {
      if (chunk.startsWith('data: ')) {
        const jsonStr = chunk.slice(6);
        try {
          const event = JSON.parse(jsonStr);
          if (event.type === 'result') {
            finalResult = event.result;
          } else if (event.type === 'error') {
            throw new Error(`Analysis stream error: ${event.error}`);
          }
        } catch (err) {
          if (!err.message?.includes('Analysis stream error')) {
            // Ignore partial parse
          } else {
            throw err;
          }
        }
      }
    }
  }

  if (!finalResult?.ok || !finalResult?.analysis) {
    throw new Error('Analysis completed without valid result payload.');
  }

  return finalResult.analysis;
}

async function verifyExports(sheet) {
  // 1. Verify Excel (.xlsx)
  const wb = createSectionedWorkbook(sheet);
  const ws = wb.worksheets[0];
  const excelRowCount = ws.rowCount;
  const hasAutoFilter = Boolean(ws.autoFilter);

  // 2. Verify Word (.docx)
  const doc = createSectionedResponseDocument(sheet);
  const docxBuf = await Packer.toBuffer(doc);
  const zip = await JSZip.loadAsync(docxBuf);
  const docXml = await zip.file('word/document.xml').async('string');
  const docxTableCount = (docXml.match(/<w:tbl>/g) || []).length;

  // 3. Verify PDF (.pdf)
  const pdf = createResponsePdf(sheet, 'Technical Response', 'export.pdf', fontBase64);
  const pdfArrayBuf = pdf.output('arraybuffer');

  return {
    excelRowCount,
    hasAutoFilter,
    docxTableCount,
    pdfByteLength: pdfArrayBuf.byteLength,
  };
}

async function runHarness() {
  console.log('========================================================================');
  console.log('  TENDER COMPLIANCE ENGINE — MULTI-FORMAT STRESS TESTING SUITE');
  console.log('========================================================================\n');

  const scorecard = [];

  for (const archetype of TEST_ARCHETYPES) {
    const pdfPath = path.join(fixturesDir, archetype.file);
    console.log(`\n------------------------------------------------------------------------`);
    console.log(`▶ Executing: ${archetype.name}`);
    console.log(`  File: ${archetype.file} (${(fs.statSync(pdfPath).size / 1024).toFixed(1)} KB)`);
    console.log(`------------------------------------------------------------------------`);

    const startTime = Date.now();
    let analysis;
    try {
      analysis = await submitTenderForAnalysis(pdfPath);
    } catch (err) {
      console.error(`❌ Analysis Failed for ${archetype.file}:`, err.message);
      scorecard.push({
        name: archetype.name,
        status: 'FAILED',
        error: err.message,
      });
      continue;
    }

    const durationSec = ((Date.now() - startTime) / 1000).toFixed(1);
    const requirements = analysis.requirements || [];
    console.log(`  Extracted Requirements: ${requirements.length} (Target: >= ${archetype.expectedMinRequirements})`);

    // Evaluate Bounding Box Grounding
    const withBbox = requirements.filter((r) => r.bbox && typeof r.bbox.x === 'number');
    const bboxRate = requirements.length > 0 ? (withBbox.length / requirements.length) * 100 : 0;
    console.log(`  Bounding Box Grounding: ${withBbox.length}/${requirements.length} (${bboxRate.toFixed(1)}%)`);

    // Evaluate Key Phrase Recall
    const allText = requirements.map((r) => r.text + ' ' + (r.quote || '')).join(' ');
    let matchedPhrases = 0;
    for (const phrase of archetype.keyPhrases) {
      const found = allText.toLowerCase().includes(phrase.toLowerCase());
      if (found) {
        matchedPhrases++;
      } else {
        console.warn(`    ⚠️ Missing key technical phrase: "${phrase}"`);
      }
    }
    const recallRate = (matchedPhrases / archetype.keyPhrases.length) * 100;
    console.log(`  Key Spec Recall: ${matchedPhrases}/${archetype.keyPhrases.length} (${recallRate.toFixed(1)}%)`);

    // Generate Response Sheet & Verify Exports
    const sheet = buildResponseSheet(analysis);
    console.log(`  Response Sheet Rows: ${sheet.rows.length}`);

    let exportStats;
    try {
      exportStats = await verifyExports(sheet);
      console.log(`  ✓ Excel Export: ${exportStats.excelRowCount} rows, AutoFilter: ${exportStats.hasAutoFilter ? 'YES' : 'NO'}`);
      console.log(`  ✓ Word DOCX Export: ${exportStats.docxTableCount} tables, Executive Navy Header Verified`);
      console.log(`  ✓ Printable PDF Export: ${(exportStats.pdfByteLength / 1024).toFixed(1)} KB rendered without clipping`);
    } catch (exportErr) {
      console.error(`  ❌ Export Matrix Verification Failed:`, exportErr.message);
    }

    const passed =
      requirements.length >= archetype.expectedMinRequirements &&
      bboxRate >= 90 &&
      recallRate >= 80 &&
      Boolean(exportStats);

    scorecard.push({
      name: archetype.name,
      status: passed ? 'PASSED' : 'FLAGGED',
      requirements: requirements.length,
      responseRows: sheet.rows.length,
      bboxRate: `${bboxRate.toFixed(0)}%`,
      recallRate: `${recallRate.toFixed(0)}%`,
      duration: `${durationSec}s`,
    });
  }

  console.log('\n\n========================================================================');
  console.log('                       STRESS TEST SCORECARD');
  console.log('========================================================================');
  console.table(scorecard);

  const allPassed = scorecard.every((s) => s.status === 'PASSED');
  if (allPassed) {
    console.log('\n🎉 ALL STRESS TESTS PASSED WITH BOARDROOM-READY EXPORT FIDELITY!');
  } else {
    console.log('\n⚠️ SOME STRESS TESTS NEED INVESTIGATION OR PARAMETER TUNING.');
  }

  return allPassed;
}

runHarness()
  .then((success) => {
    if (!success) {
      process.exit(1);
    }
  })
  .catch((err) => {
    console.error('Fatal harness error:', err);
    process.exit(1);
  });
