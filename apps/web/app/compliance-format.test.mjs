import test from "node:test";
import assert from "node:assert/strict";
import { splitHeadingPrefix } from "./compliance-format.ts";

test("splits a literal section heading from its description without changing text", () => {
  const text = "6. MBE process control system\nElectronic Cabinets for PID controllers.";
  const parts = splitHeadingPrefix(text, "6. MBE process control system");
  assert.deepEqual(parts, {
    heading: "6. MBE process control system",
    remainder: "\nElectronic Cabinets for PID controllers.",
  });
  assert.equal(`${parts?.heading}${parts?.remainder}`, text);
});

test("accepts source line wrapping between heading words", () => {
  const parts = splitHeadingPrefix("4. MBE\nsources - Vendor to provide...", "4. MBE sources");
  assert.deepEqual(parts, { heading: "4. MBE\nsources", remainder: " - Vendor to provide..." });
});

test("rejects a heading suggestion that is not a literal prefix", () => {
  assert.equal(splitHeadingPrefix("6. MBE process control system", "MBE process"), null);
  assert.equal(splitHeadingPrefix("MBE process control system", "6. MBE process"), null);
});
