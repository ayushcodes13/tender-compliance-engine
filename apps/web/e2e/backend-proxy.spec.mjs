import { expect, test } from "@playwright/test";

test("backend proxy follows same-origin canonical redirects server-side", async ({ request, baseURL }) => {
  const response = await request.get(
    `${baseURL}/api/backend/projects/proxy-redirect/submissions`,
    { maxRedirects: 0 }
  );

  expect(response.status()).toBe(200);
  expect(response.headers().location).toBeUndefined();
  await expect(response.json()).resolves.toEqual([
    { id: "canonical-route-reached" },
  ]);
});

test("backend proxy fails closed on same-origin write redirects", async ({ request, baseURL }) => {
  const response = await request.post(
    `${baseURL}/api/backend/projects/proxy-redirect/write`,
    { data: { value: "do not replay" }, maxRedirects: 0 }
  );

  expect(response.status()).toBe(502);
  expect(response.headers().location).toBeUndefined();
  await expect(response.json()).resolves.toEqual({
    detail: "The upstream service redirected a write request. Please retry.",
  });
});
