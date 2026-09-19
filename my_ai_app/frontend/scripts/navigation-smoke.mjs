import assert from "node:assert/strict";
import { chromium, expect } from "@playwright/test";

const origin = "http://localhost:3000";
const browser = await chromium.launch();
try {
  for (const mobile of [false, true]) {
    const context = await browser.newContext({
      viewport: mobile ? { width: 390, height: 844 } : { width: 1280, height: 800 },
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    // Hold the actual route response, including prefetch, to exercise a slow network.
    await page.route("**/register?*", async (route) => {
      if (route.request().headers().rsc === "1") await gate;
      await route.continue();
    });
    try {
      await page.goto(origin, { timeout: 120000 });
      if (mobile) await page.getByRole("button", { name: "Open menu", exact: true }).click();
      const link = page.locator('header a[href="/register"]:visible');
      await link.click();
      await expect(link.getByRole("status")).toHaveText("Loading...");
      assert.equal(
        new URL(page.url()).pathname,
        "/",
        "Feedback must appear before the route arrives",
      );
      release();
      await expect(page.getByLabel("Confirm password", { exact: false })).toBeVisible({
        timeout: 120000,
      });
      await expect(page.getByRole("status").filter({ hasText: "Loading..." })).toHaveCount(0);
      assert.deepEqual(errors, []);
      console.log(`${mobile ? "Mobile" : "Desktop"}: one click, pending feedback, signup visible`);
    } finally {
      release();
      await context.close();
    }
  }

  const page = await browser.newPage();
  await page.goto(origin, { timeout: 120000 });
  const start = Date.now();
  await page.locator('header a[href="/register"]:visible').click();
  await expect(page.getByLabel("Confirm password", { exact: false })).toBeVisible({
    timeout: 120000,
  });
  console.log(`Signup navigation: ${Date.now() - start} ms`);
  for (const path of ["/register", "/login", "/api/health"]) {
    const samples = [];
    for (let i = 0; i < 3; i++) {
      const start = Date.now();
      const response = await page.request.get(origin + path);
      assert.equal(response.status(), 200, path);
      samples.push(Date.now() - start);
    }
    console.log(`${path}: HTTP 200; ${samples.join(", ")} ms`);
  }
} finally {
  await browser.close();
}
