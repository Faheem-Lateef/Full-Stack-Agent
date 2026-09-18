import assert from "node:assert/strict";
import { randomUUID, randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { chromium } from "@playwright/test";

// Local-only integration check. Cleanup is constrained to this run's unique emails.
const origin = "http://localhost:3000";
const api = "http://127.0.0.1:8000/api/v1";
const emails = [0, 1].map(() => `smoke-${randomUUID()}@example.com`);
const password = randomBytes(24).toString("base64url");
let browser;
async function request(path, options = {}) {
  return fetch(`${api}${path}`, { ...options, signal: AbortSignal.timeout(20000) });
}
try {
  const ready = await (await request("/health/ready")).json();
  assert.equal(ready.checks.database.status, "healthy");
  for (const [index, email] of emails.entries()) {
    const response = await request("/auth/register", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name: "Smoke Test", role: "admin" }),
    });
    assert.equal(response.status, 201, "Registration must succeed");
    const user = await response.json();
    if (index === 1) assert.equal(user.role, "user", "Public signup cannot request admin");
  }
  const login = await request("/auth/login", {
    method: "POST", body: new URLSearchParams({ username: emails[1], password }),
  });
  assert.equal(login.status, 200);
  const token = (await login.json()).access_token;
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  assert.equal((await request("/auth/me", { headers })).status, 200);
  assert.equal((await request("/users/me", { method: "PATCH", headers, body: JSON.stringify({ role: "admin" }) })).status, 403);
  assert.equal((await request("/users", { headers })).status, 403);
  const created = await request("/conversations", { method: "POST", headers, body: JSON.stringify({ title: "Smoke conversation" }) });
  assert.equal(created.status, 201, "Conversation creation must succeed");
  const conversation = await created.json();
  assert.equal((await request(`/conversations/${conversation.id}`, { headers })).status, 200);
  assert.equal((await request(`/conversations/${conversation.id}`, { method: "DELETE", headers })).status, 204);

  browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const home = await page.goto(origin, { timeout: 60000 });
  assert.equal(home.status(), 200);
  await page.waitForFunction(() => document.title.includes("AgentHarbor"));
  await page.goto(`${origin}/login`);
  await page.getByLabel(/email/i).fill(emails[1]);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /sign in|log in|login/i }).click();
  await page.waitForURL(/chat|dashboard|onboarding/, { timeout: 60000 });
  await page.goto(`${origin}/dashboard`);
  await page.waitForLoadState("networkidle", { timeout: 60000 });
  assert(!page.url().includes("/login"), "Session must persist across navigation");
  await page.locator("main").waitFor({ state: "visible", timeout: 60000 });
  assert.deepEqual(errors, [], "No uncaught browser errors");
  console.log("PASS: database, registration, authorization, saved conversations, branding, browser login and dashboard.");
  console.log(`AI provider: ${ready.checks.llm.status} (no paid model request performed).`);
} finally {
  if (browser) await browser.close();
  const backend = resolve("../backend");
  const python = process.platform === "win32" ? resolve(backend, ".venv/Scripts/python.exe") : resolve(backend, ".venv/bin/python");
  execFileSync(python, ["-c", `
import sys
import psycopg2
from dotenv import dotenv_values
values = dotenv_values('.env')
emails = sys.argv[1:]
assert len(emails) == 2 and all(e.startswith('smoke-') and e.endswith('@example.com') for e in emails)
conn = psycopg2.connect(host=values['POSTGRES_HOST'], port=values['POSTGRES_PORT'], user=values['POSTGRES_USER'], password=values['POSTGRES_PASSWORD'], dbname=values['POSTGRES_DB'])
with conn:
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM users WHERE email = ANY(%s)', (emails,))
conn.close()
`, ...emails], { cwd: backend, stdio: ["ignore", "pipe", "pipe"] });
}
