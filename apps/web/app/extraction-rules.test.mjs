import test from "node:test";
import assert from "node:assert/strict";
import { isTechnicalRequirementCandidate, splitTechnicalCandidates } from "./extraction-rules.ts";

test("keeps product specifications and measured performance", () => {
  assert.equal(isTechnicalRequirementCandidate("The equipment shall operate at 220 V AC and 50 Hz."), true);
  assert.equal(isTechnicalRequirementCandidate("The instrument must provide a minimum resolution of 10 µm."), true);
  assert.equal(isTechnicalRequirementCandidate("The system shall achieve a sample rate of 500 tests per minute."), true);
  assert.equal(isTechnicalRequirementCandidate("The sensor should provide an accuracy of ±0.2°C."), true);
  assert.equal(isTechnicalRequirementCandidate("500% overload capacity of load cell in both tension and compression modes."), true);
  assert.equal(isTechnicalRequirementCandidate("The load cell shall retain 50 kN/mm frame stiffness."), true);
});

test("excludes commercial, logistics, and procurement clauses", () => {
  assert.equal(isTechnicalRequirementCandidate("The quotations should be CIP-Bangalore Airport."), false);
  assert.equal(isTechnicalRequirementCandidate("The bidder shall submit a price quotation inclusive of GST."), false);
  assert.equal(isTechnicalRequirementCandidate("The delivery location shall be the buyer's warehouse."), false);
  assert.equal(isTechnicalRequirementCandidate("The tender shall be submitted through the CPP portal before the deadline."), false);
  assert.equal(isTechnicalRequirementCandidate("The technical proposal should contain a technical compliance table."), false);
  assert.equal(isTechnicalRequirementCandidate("Delayed installation will incur liquidated damages at 0.5% per week."), false);
  assert.equal(isTechnicalRequirementCandidate("The vendor shall provide three years of warranty, maintenance and training."), false);
  assert.equal(isTechnicalRequirementCandidate("The vendor shall visit the site to confirm infrastructure requirements."), false);
  assert.equal(isTechnicalRequirementCandidate("The tender should be submitted in two envelopes (two bid system)."), false);
  assert.equal(isTechnicalRequirementCandidate("After delivery and acceptance, suppliers should take back the waste packing material."), false);
  assert.equal(isTechnicalRequirementCandidate("The bidder should provide technical specifications of the quoted products."), false);
  assert.equal(isTechnicalRequirementCandidate("When items are provided, full performance satisfaction should be demonstrated."), false);
  assert.equal(isTechnicalRequirementCandidate("Test results shall be submitted along with the tender."), false);
  assert.equal(isTechnicalRequirementCandidate("The board resolution should be signed by an authorized signatory."), false);
  assert.equal(isTechnicalRequirementCandidate("The second column should provide specifications of the instrument against the requirement."), false);
  assert.equal(isTechnicalRequirementCandidate("Bidders should clearly indicate compliance with the technical specifications in the tender."), false);
});

test("requires both obligation language and a technical signal", () => {
  assert.equal(isTechnicalRequirementCandidate("All documentations in the tender should be in English."), false);
  assert.equal(isTechnicalRequirementCandidate("The microscope shall include a 40x objective lens."), true);
  assert.equal(isTechnicalRequirementCandidate("The bidder shall provide all information."), false);
});

test("splits enumerated technical clauses into independently reviewable candidates", () => {
  assert.deepEqual(splitTechnicalCandidates("1. The equipment shall operate at 220 V. 2. The instrument shall have 5 µm resolution."), [
    "The equipment shall operate at 220 V.",
    "The instrument shall have 5 µm resolution.",
  ]);
});
