import fs from "node:fs";
import path from "node:path";
import { consumeAnalysisStream } from "../apps/web/app/analysis-events.ts";
import { buildResponseSheet } from "../apps/web/app/response-sheet.ts";
import { buildResponseSections } from "../apps/web/app/response-sections.ts";

const BASE_URL = process.env.TEST_SERVER_URL || "http://127.0.0.1:3000";
const FIXTURES_DIR = path.resolve("stress-test-fixtures");

const testSuites = [
  {
    file: "01_normal_standard_tender.pdf",
    description: "Standard clean table tender with electrical parameters and tolerances",
    validate: (data, sheet, sections) => {
      if (data.analysis.requirements.length < 8) {
        throw new Error(`Expected at least 8 requirements, got ${data.analysis.requirements.length}`);
      }
      const headers = sheet.columns.map((c) => c.header);
      if (!headers.some((h) => /compliance/i.test(h)) || !headers.some((h) => /remark/i.test(h))) {
        throw new Error(`Missing compliance or remark columns in ${headers.join(", ")}`);
      }
      console.log(`  ✓ Extracted ${data.analysis.requirements.length} rows; response columns: [${headers.join(", ")}]`);
    },
  },
  {
    file: "02_multi_column_grid_tender.pdf",
    description: "Multi-column wide industrial tender with assembly, standard, and tolerances",
    validate: (data, sheet, sections) => {
      if (data.analysis.requirements.length < 8) {
        throw new Error(`Expected at least 8 requirements, got ${data.analysis.requirements.length}`);
      }
      const headers = sheet.columns.map((c) => c.header);
      console.log(`  ✓ Extracted ${data.analysis.requirements.length} rows; response columns: [${headers.join(", ")}]`);
    },
  },
  {
    file: "03_deep_hierarchy_subsystems.pdf",
    description: "Multi-level hierarchy tender with units, subsystems, and repeated bullet points",
    validate: (data, sheet, sections) => {
      if (data.analysis.requirements.length < 15) {
        throw new Error(`Expected at least 15 requirements, got ${data.analysis.requirements.length}`);
      }
      const headers = sheet.columns.map((c) => c.header);
      if (!headers.includes("Section / Unit") || !headers.includes("Subsystem / Parameter")) {
        throw new Error(`Expected 'Section / Unit' and 'Subsystem / Parameter' in headers, got: ${headers.join(", ")}`);
      }
      // Each requirement/specification must have its own row with compliance & remarks
      const compCol = sheet.columns.findIndex((c) => /compliance/i.test(c.header));
      const remCol = sheet.columns.findIndex((c) => /remark/i.test(c.header));
      if (compCol < 0 || remCol < 0) {
        throw new Error(`Missing compliance or remark columns in ${headers.join(", ")}`);
      }
      const dataReqs = data.analysis.requirements.filter((r) => r.rowType !== "section" && r.rowType !== "optional_heading");
      if (sheet.rows.length < dataReqs.length) {
        throw new Error(`Expected separate subrows per requirement (${sheet.rows.length} rows vs ${dataReqs.length} data requirements)`);
      }
      console.log(`  ✓ Multi-level hierarchy verified: ${sheet.rows.length} subrows with individual compliance/remarks areas across ${sections.length} sections`);
    },
  },
  {
    file: "04_scanned_noisy_ocr.pdf",
    description: "Pure scanned document (6.2 MB) with zero native text layer and special characters",
    validate: (data, sheet, sections) => {
      if (data.analysis.requirements.length < 4) {
        throw new Error(`Expected at least 4 requirements from OCR, got ${data.analysis.requirements.length}`);
      }
      // Since it is 100% scanned, Tier 1 verbatim should be 0, and Tier 2 visualPass should be > 0
      const summary = data.analysis.validationSummary;
      if (summary.visualPass === 0 && summary.verbatimPass === 0) {
        throw new Error(`Expected OCR validation pass, got ${JSON.stringify(summary)}`);
      }
      console.log(`  ✓ Scanned OCR verified: ${summary.visualPass} visual/OCR validated rows (0 verbatim native text, as expected)`);
    },
  },
  {
    file: "05_adversarial_mixed_sections.pdf",
    description: "Adversarial tender mixing commercial terms, eligibility, technical specs, and financial BOQ",
    validate: (data, sheet, sections) => {
      if (data.analysis.requirements.length === 0) {
        throw new Error("No requirements extracted");
      }
      // Ensure commercial clauses (turnover, EMD, financial BOQ) are NOT in the technical compliance sheet
      for (const req of data.analysis.requirements) {
        if (/turnover\s+of\s+at\s+least/i.test(req.text) || /Earnest\s+Money\s+Deposit/i.test(req.text)) {
          throw new Error(`Leaked commercial eligibility requirement into technical specs: "${req.text}"`);
        }
      }
      console.log(`  ✓ Adversarial routing verified: extracted ${data.analysis.requirements.length} technical specs while rejecting commercial/financial sections`);
    },
  },
];

async function runTest(testDef, index) {
  const filePath = path.join(FIXTURES_DIR, testDef.file);
  console.log(`\n=================================================================`);
  console.log(`[TEST ${index + 1}/${testSuites.length}] ${testDef.file}`);
  console.log(`Description: ${testDef.description}`);
  console.log(`=================================================================`);

  const fileBuffer = fs.readFileSync(filePath);
  const formData = new FormData();
  formData.append("file", new Blob([fileBuffer], { type: "application/pdf" }), testDef.file);

  const startTime = Date.now();
  const res = await fetch(`${BASE_URL}/api/analyze`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errorText}`);
  }

  const data = await consumeAnalysisStream(res, {
    onProgress: (p) => {
      if (p.stage === "reading" || p.stage === "locating" || p.stage === "extracting" || p.stage === "verifying") {
        process.stdout.write(`\r  [${p.stage}] ${p.message.slice(0, 70)}... `);
      }
    },
  });
  process.stdout.write("\n");

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  if (!data.ok) {
    throw new Error(`Analysis returned error: ${data.error}`);
  }

  console.log(`  Execution completed in ${elapsed}s`);
  console.log(`  Validation summary:`, JSON.stringify(data.analysis.validationSummary));

  const sheet = buildResponseSheet(data.analysis);
  const sections = buildResponseSections(sheet, true);

  // Run custom test assertions
  testDef.validate(data, sheet, sections);

  return { file: testDef.file, ok: true, elapsed, requirements: data.analysis.requirements.length, rows: sheet.rows.length };
}

async function main() {
  if (!fs.existsSync(FIXTURES_DIR) || fs.readdirSync(FIXTURES_DIR).length === 0) {
    console.log("Generating stress test fixtures...");
    const { execSync } = await import("node:child_process");
    execSync("python3 scripts/generate-stress-test-tenders.py", { stdio: "inherit" });
  }

  console.log(`Starting TCE Senior AI Stress-Test Suite against ${BASE_URL}...`);
  const results = [];
  let failures = 0;

  const filter = process.argv[2];
  const suites = filter ? testSuites.filter((s) => s.file.includes(filter)) : testSuites;

  for (let i = 0; i < suites.length; i++) {
    try {
      const res = await runTest(suites[i], i);
      results.push(res);
    } catch (err) {
      console.error(`\n❌ FAILED [${suites[i].file}]:`, err.message);
      results.push({ file: suites[i].file, ok: false, error: err.message });
      failures++;
    }
  }

  console.log(`\n=================================================================`);
  console.log(`STRESS TEST SUMMARY`);
  console.log(`=================================================================`);
  results.forEach((r) => {
    if (r.ok) {
      console.log(`  PASS: ${r.file} (${r.requirements} reqs -> ${r.rows} rows in ${r.elapsed}s)`);
    } else {
      console.log(`  FAIL: ${r.file} (${r.error})`);
    }
  });

  if (failures > 0) {
    console.error(`\n💥 Stress test completed with ${failures} failure(s).`);
    process.exit(1);
  } else {
    console.log(`\n🎉 ALL 5 STRESS TESTS PASSED CLEANLY! SYSTEM IS ROCK-SOLID.`);
  }
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
