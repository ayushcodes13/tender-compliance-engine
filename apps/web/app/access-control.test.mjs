import test from "node:test";
import assert from "node:assert/strict";
import { applicationAccessResponse, checkApplicationAccess } from "./access-control.ts";

function authorization(username, password) {
  return `Basic ${Buffer.from(`${username}:${password}`, "utf8").toString("base64")}`;
}

test("requires configured Basic credentials when an access password is set", () => {
  assert.equal(checkApplicationAccess(null, "secret", "production"), "unauthorized");
  assert.equal(checkApplicationAccess("Bearer secret", "secret", "production"), "unauthorized");
  assert.equal(checkApplicationAccess(authorization("tender", "wrong"), "secret", "production"), "unauthorized");
  assert.equal(checkApplicationAccess(authorization("other", "secret"), "secret", "production"), "unauthorized");
  assert.equal(checkApplicationAccess(authorization("tender", "secret"), "secret", "production"), "allow");
});

test("accepts UTF-8 passwords and rejects malformed Basic credentials", () => {
  assert.equal(checkApplicationAccess(authorization("tender", "sëcret🔒"), "sëcret🔒", "production"), "allow");
  assert.equal(checkApplicationAccess("Basic !!!", "secret", "production"), "unauthorized");
  assert.equal(checkApplicationAccess("Basic dGVuZGVy", "secret", "production"), "unauthorized");
});

test("fails closed in production when access protection is not configured", async () => {
  const decision = checkApplicationAccess(null, "", "production");
  assert.equal(decision, "misconfigured");
  const response = applicationAccessResponse(decision);
  assert.equal(response.status, 503);
  assert.match(response.headers.get("cache-control"), /no-store/);
  assert.match(await response.text(), /APP_ACCESS_PASSWORD/);
});

test("keeps local development usable when access protection is not configured", () => {
  assert.equal(checkApplicationAccess(null, undefined, "development"), "allow");
});

test("unauthenticated requests receive a no-store Basic challenge", () => {
  const response = applicationAccessResponse("unauthorized");
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("www-authenticate"), 'Basic realm="Tender Compliance Engine", charset="UTF-8"');
  assert.equal(response.headers.get("cache-control"), "no-store");
});
