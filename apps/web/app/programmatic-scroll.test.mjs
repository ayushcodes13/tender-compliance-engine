import test from "node:test";
import assert from "node:assert/strict";
import { guardPageSyncUntilScrollSettles } from "./programmatic-scroll.ts";

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("keeps page synchronization guarded beyond 450 ms and settles after scrollend", async () => {
  const stage = new EventTarget();
  let settled = false;
  const cancel = guardPageSyncUntilScrollSettles(stage, () => { settled = true; }, { idleMs: 180, fallbackMs: 1500 });

  for (let frame = 0; frame < 6; frame += 1) {
    stage.dispatchEvent(new Event("scroll"));
    await delay(90);
    assert.equal(settled, false);
  }
  assert.equal(settled, false, "scroll events keep the guard active past the old fixed timeout");
  stage.dispatchEvent(new Event("scrollend"));
  assert.equal(settled, true);
  cancel();
});

test("uses scroll inactivity when a browser does not emit scrollend", async () => {
  const stage = new EventTarget();
  let settled = false;
  guardPageSyncUntilScrollSettles(stage, () => { settled = true; }, { idleMs: 35, fallbackMs: 200 });

  stage.dispatchEvent(new Event("scroll"));
  await delay(20);
  assert.equal(settled, false);
  stage.dispatchEvent(new Event("scroll"));
  await delay(20);
  assert.equal(settled, false, "each scroll event extends the quiet period");
  await delay(30);
  assert.equal(settled, true);
});

test("releases page synchronization after the fallback for a browser without scroll events", async () => {
  const stage = new EventTarget();
  let settled = false;
  guardPageSyncUntilScrollSettles(stage, () => { settled = true; }, { idleMs: 80, fallbackMs: 25 });
  await delay(40);
  assert.equal(settled, true);
});
