import assert from "node:assert/strict";
import { randomUUID, randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";

const origin = "http://localhost:3000";
const api = "http://127.0.0.1:8000/api/v1";
const emails = [0, 1].map(() => `support-smoke-${randomUUID()}@example.com`);
const password = randomBytes(24).toString("base64url");
const backend = resolve("../backend");
const python = resolve(
  backend,
  process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
);
let browser;
const call = (path, options = {}) =>
  fetch(api + path, { ...options, signal: AbortSignal.timeout(20000) });
function sqlScript(code, args = []) {
  return execFileSync(
    python,
    [
      "-c",
      `
import sys, json, uuid
import psycopg2
from dotenv import dotenv_values
v=dotenv_values('.env')
conn=psycopg2.connect(host=v['POSTGRES_HOST'], port=v['POSTGRES_PORT'], user=v['POSTGRES_USER'], password=v['POSTGRES_PASSWORD'], dbname=v['POSTGRES_DB'])
with conn:
    with conn.cursor() as cursor:
${code}
conn.close()
`,
      ...args,
    ],
    { cwd: backend, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );
}
try {
  const headers = [];
  for (const email of emails) {
    const created = await call("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name: "Support Smoke" }),
    });
    assert.equal(created.status, 201);
    const login = await call("/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username: email, password }),
    });
    assert.equal(login.status, 200);
    headers.push({
      Authorization: `Bearer ${(await login.json()).access_token}`,
      "Content-Type": "application/json",
    });
  }
  browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(origin + "/login");
  await page.getByLabel(/email/i).fill(emails[0]);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /sign in|log in|login/i }).click();
  await page.waitForURL(/chat|dashboard|onboarding/, { timeout: 60000 });
  await page.goto(origin + "/support");
  await page.getByLabel("Workspace name", { exact: true }).fill("Smoke Support Company");
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  await expect(page.getByLabel("Company workspace")).toContainText("Smoke Support Company");
  const wsResponse = await call("/workspaces", { headers: headers[0] });
  assert.equal(wsResponse.status, 200);
  const wid = (await wsResponse.json())[0].id;
  const base = `/workspaces/${wid}`;
  assert.equal((await call(base + "/knowledge", { headers: headers[1] })).status, 404);
  await page.getByRole("link", { name: "Company knowledge", exact: true }).click();
  await page
    .locator('input[type="file"]')
    .setInputFiles({
      name: "smoke-refunds.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Refund requests are reviewed within fourteen days. Contact support for order-specific details.",
      ),
    });
  await page.getByRole("button", { name: "Upload document", exact: true }).click();
  await expect(page.getByText("ready", { exact: true })).toBeVisible({ timeout: 60000 });
  await page.getByLabel("Question or keywords").fill("refund policy");
  await page.getByRole("button", { name: "Search knowledge", exact: true }).click();
  await expect(page.locator("blockquote")).toContainText("fourteen days");
  await page.getByRole("link", { name: "Team", exact: true }).click();
  await page.getByLabel("Email address", { exact: true }).fill(emails[1]);
  await page.getByRole("button", { name: "Create invitation", exact: true }).click();
  const tokenInput = page.getByLabel("New invitation token");
  await expect(tokenInput).toBeVisible();
  const token = await tokenInput.inputValue();
  assert.equal(
    (
      await call("/workspaces/accept-invitation", {
        method: "POST",
        headers: headers[1],
        body: JSON.stringify({ token }),
      })
    ).status,
    200,
  );
  assert.equal(
    (
      await call("/workspaces/accept-invitation", {
        method: "POST",
        headers: headers[1],
        body: JSON.stringify({ token }),
      })
    ).status,
    422,
  );
  const docs = await (await call(base + "/knowledge", { headers: headers[1] })).json();
  assert.equal(
    (await call(base + `/knowledge/${docs[0].id}`, { method: "DELETE", headers: headers[1] }))
      .status,
    403,
  );
  await page.getByRole("link", { name: "Reply workspace", exact: true }).click();
  await page
    .getByLabel("Customer question", { exact: true })
    .fill("How long do refund requests take?");
  await page.getByRole("button", { name: "Create support case", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Reply review", exact: true })).toBeVisible();
  const usage = await (await call(base + "/usage", { headers: headers[0] })).json();
  if (!usage.provider_configured)
    await expect(page.getByRole("button", { name: "Draft reply", exact: true })).toBeDisabled();
  const cases = await (await call(base + "/support/cases", { headers: headers[0] })).json();
  // Explicit, disposable DB fixture exercises the review UI without a paid/fake live model.
  sqlScript(
    `        wid=str(uuid.UUID(sys.argv[1])); cid=str(uuid.UUID(sys.argv[2]))
        cursor.execute("SELECT id, document_id, page FROM support_chunks WHERE workspace_id=%s LIMIT 1", (wid,))
        chunk, doc, page=cursor.fetchone()
        citations=json.dumps([dict(id=str(chunk),document_id=str(doc),page=page,title='smoke-refunds.txt')])
        cursor.execute("INSERT INTO support_drafts (id,workspace_id,case_id,reply,outcome,citations,version,history) VALUES (%s,%s,%s,%s,'answerable',%s,1,'[]')", (str(uuid.uuid4()),wid,cid,'Test fixture: refund requests are reviewed within fourteen days.',citations))`,
    [wid, cases[0].id],
  );
  const editor = page.getByLabel("Reply draft", { exact: true });
  await expect(editor).toBeVisible({ timeout: 10000 });
  await editor.fill("Reviewed test reply: refund requests are reviewed within fourteen days.");
  await page.getByRole("button", { name: "Save revision", exact: true }).click();
  await expect(page.getByText(/revision 2/)).toBeVisible();
  await page.getByRole("button", { name: "Approve draft", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Copy approved reply", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: /smoke-refunds.txt/ }).click();
  await expect(page.locator("blockquote")).toContainText("fourteen days");
  await page.reload();
  await page
    .getByRole("button", { name: "How long do refund requests take?", exact: true })
    .click();
  await expect(editor).toHaveValue(
    "Reviewed test reply: refund requests are reviewed within fourteen days.",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Reply workspace", exact: true })).toBeVisible();
  assert.deepEqual(errors, []);
  console.log(
    "PASS: workspace creation, native worker ingestion, source search, isolation, invitations, agent permissions, draft editing/approval, source preview, persistence and mobile layout. Draft seeded explicitly as a test fixture; no live AI request.",
  );
} finally {
  if (browser) await browser.close();
  sqlScript(
    `        emails=sys.argv[1:]
        assert len(emails)==2 and all(e.startswith('support-smoke-') and e.endswith('@example.com') for e in emails)
        cursor.execute("DELETE FROM support_workspaces WHERE id IN (SELECT workspace_id FROM support_memberships WHERE user_id IN (SELECT id FROM users WHERE email=ANY(%s)))", (emails,))
        cursor.execute("DELETE FROM users WHERE email=ANY(%s)", (emails,))`,
    emails,
  );
}
