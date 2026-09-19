"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Workspace = { id: string; name: string; role: string; tone: string; escalation: string };
type Document = {
  id: string;
  title: string;
  state: string;
  error?: string;
  embedding_model?: string;
};
type Source = { id: string; document_id: string; title: string; page: number; text?: string };
type Case = { id: string; question: string };
type Draft = {
  id: string;
  reply: string;
  outcome: string;
  version: number;
  approved_by?: string;
  citations: Source[];
  history: { version: number; reply: string }[];
};
type Job = { id: string; target_id: string; kind: string; state: string; error?: string };
type Member = { user_id: string; email: string; role: string };
type Invite = { id: string; email: string; role: string; consumed: boolean; expires_at: string };
type Usage = {
  generations_this_month: number;
  generation_limit: number;
  documents: number;
  storage_bytes: number;
  active_jobs: number;
  provider_configured: boolean;
  search_mode: string;
};
type View = "support" | "knowledge" | "team" | "workspace" | "usage";
const tabs: { view: View; href: string; label: string }[] = [
  { view: "support", href: "/support", label: "Reply workspace" },
  { view: "knowledge", href: "/knowledge", label: "Company knowledge" },
  { view: "team", href: "/settings/team", label: "Team" },
  { view: "workspace", href: "/settings/workspace", label: "Workspace settings" },
  { view: "usage", href: "/settings/usage", label: "Usage" },
];
const panel = "rounded-xl border bg-card p-5 space-y-4";

export function SupportWorkspace({ view = "support" }: { view?: View }) {
  const user = useAuthStore((s) => s.user);
  const cache = useQueryClient();
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const workspaces = useQuery({
    queryKey: ["support", user?.id, "workspaces"],
    queryFn: () => apiClient.get<Workspace[]>("/workspaces"),
    enabled: !!user,
  });
  useEffect(() => {
    setChosen(user ? localStorage.getItem(`support-workspace-${user.id}`) || "" : "");
  }, [user]);
  const current = workspaces.data?.find((w) => w.id === chosen) || workspaces.data?.[0];
  const wid = current?.id;
  const base = `/workspaces/${wid}`;
  const key = ["support", user?.id, wid];
  const usage = useQuery({
    queryKey: [...key, "usage"],
    queryFn: () => apiClient.get<Usage>(`${base}/usage`),
    enabled: !!wid,
    refetchInterval: 5000,
  });
  const jobs = useQuery({
    queryKey: [...key, "jobs"],
    queryFn: () => apiClient.get<Job[]>(`${base}/jobs`),
    enabled: !!wid,
    refetchInterval: 3000,
  });
  const documents = useQuery({
    queryKey: [...key, "knowledge"],
    queryFn: () => apiClient.get<Document[]>(`${base}/knowledge`),
    enabled: !!wid,
    refetchInterval: view === "knowledge" ? 3000 : false,
  });
  async function action(work: () => Promise<unknown>, success = "Saved") {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      setNotice(success);
      await cache.invalidateQueries({ queryKey: ["support", user?.id] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed. Please retry.");
    } finally {
      setBusy(false);
    }
  }
  function selectWorkspace(id: string) {
    if (!window.dispatchEvent(new Event("support:leave", { cancelable: true }))) return;
    setChosen(id);
    setError("");
    setNotice("");
    if (user) localStorage.setItem(`support-workspace-${user.id}`, id);
  }
  const queryError = workspaces.error || usage.error || jobs.error || documents.error;
  if (queryError)
    return (
      <div className={panel}>
        <h1 className="text-2xl font-semibold">Support workspace unavailable</h1>
        <p role="alert">{queryError.message}</p>
        <p>The operator must enable support, or your workspace membership may have changed.</p>
        <Button
          onClick={() => {
            selectWorkspace("");
            void cache.invalidateQueries({ queryKey: ["support"] });
          }}
        >
          Reload workspaces
        </Button>
      </div>
    );
  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-muted-foreground text-sm">AgentHarbor Support</p>
          <h1 className="text-3xl font-semibold">{tabs.find((t) => t.view === view)?.label}</h1>
          <p className="text-muted-foreground mt-2">
            Answers from your company knowledge. Reviewed by your team.
          </p>
        </div>
        {!!workspaces.data?.length && (
          <label>
            Company workspace
            <select
              aria-label="Company workspace"
              value={wid}
              onChange={(e) => selectWorkspace(e.target.value)}
              className="bg-background mt-1 block rounded-md border p-2"
            >
              {workspaces.data.map((w) => (
                <option value={w.id} key={w.id}>
                  {w.name} · {w.role}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>
      {error && (
        <p role="alert" className="rounded-md border border-red-400 p-3">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm">
          {notice}
        </p>
      )}
      {workspaces.isLoading && <p role="status">Loading workspaces...</p>}
      <details open={!workspaces.data?.length} className={panel}>
        <summary className="cursor-pointer font-medium">Create or join a workspace</summary>
        <div className="grid gap-6 md:grid-cols-2">
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                const w = await apiClient.post<Workspace>("/workspaces", { name });
                selectWorkspace(w.id);
                setName("");
              }, "Workspace created");
            }}
          >
            <label htmlFor="workspace-name">Workspace name</label>
            <Input
              id="workspace-name"
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button disabled={busy}>Create workspace</Button>
          </form>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                const w = await apiClient.post<{ workspace_id: string }>(
                  "/workspaces/accept-invitation",
                  { token },
                );
                selectWorkspace(w.workspace_id);
                setToken("");
              }, "Invitation accepted");
            }}
          >
            <label htmlFor="invite-token">Invitation token</label>
            <Input
              id="invite-token"
              required
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="off"
            />
            <p className="text-muted-foreground text-xs">
              Sign in with the email address your team invited.
            </p>
            <Button variant="outline" disabled={busy}>
              Join workspace
            </Button>
          </form>
        </div>
      </details>
      {current && (
        <>
          <nav aria-label="Support navigation" className="flex flex-wrap gap-2">
            {tabs.map((t) => (
              <Link
                key={t.view}
                href={t.href}
                aria-current={view === t.view ? "page" : undefined}
                className={`rounded-md border px-3 py-2 text-sm ${view === t.view ? "bg-secondary font-semibold" : ""}`}
              >
                {t.label}
              </Link>
            ))}
          </nav>
          {usage.data && !usage.data.provider_configured && (
            <p className="rounded-lg border p-3 text-sm">
              Drafting needs the operator’s OpenAI key. You can create workspaces, upload documents
              and search knowledge now.
            </p>
          )}
          <div key={`${user?.id}-${wid}`}>
            {view === "knowledge" && (
              <Knowledge
                base={base}
                documents={documents.data || []}
                manage={current.role !== "agent"}
                busy={busy}
                action={action}
                mode={usage.data?.search_mode || "keyword"}
              />
            )}
            {view === "support" && (
              <ReplyWorkspace
                base={base}
                queryKey={key}
                jobs={jobs.data || []}
                busy={busy}
                action={action}
                configured={!!usage.data?.provider_configured}
              />
            )}
            {view === "team" && (
              <Team
                base={base}
                queryKey={key}
                manage={current.role !== "agent"}
                owner={current.role === "owner"}
                action={action}
                busy={busy}
              />
            )}
            {view === "workspace" && (
              <WorkspaceSettings workspace={current} base={base} busy={busy} action={action} />
            )}
            {view === "usage" && usage.data && (
              <div className={panel}>
                <h2 className="text-lg font-semibold">Pilot allowance</h2>
                <p>
                  Draft requests this month: {usage.data.generations_this_month} /{" "}
                  {usage.data.generation_limit}
                </p>
                <p>Documents: {usage.data.documents} / 100</p>
                <p>
                  Stored originals: {(usage.data.storage_bytes / 1024 / 1024).toFixed(2)} / 50 MB
                </p>
                <p>Active jobs: {usage.data.active_jobs}</p>
                <p>Search: {usage.data.search_mode}</p>
                <p className="text-muted-foreground text-sm">
                  Failed or cancelled generations still count toward the request allowance. Provider
                  charges may apply to work already started. This is not a billing statement.
                </p>
              </div>
            )}
          </div>
          {!!jobs.data?.some((j) => ["queued", "processing", "failed"].includes(j.state)) && (
            <details className={panel}>
              <summary>Processing activity</summary>
              {jobs.data
                .filter((j) => ["queued", "processing", "failed"].includes(j.state))
                .slice(0, 15)
                .map((j) => (
                  <div className="flex flex-wrap items-center gap-3 border-b py-2" key={j.id}>
                    <span>
                      {j.kind === "ingest" ? "Document processing" : "Reply generation"}: {j.state}
                    </span>
                    {j.error && <span className="text-sm">{j.error}</span>}
                    {["queued", "processing"].includes(j.state) && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          void action(
                            () => apiClient.post(`${base}/jobs/${j.id}/cancel`, {}),
                            "Cancellation requested",
                          )
                        }
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                ))}
            </details>
          )}
        </>
      )}
    </div>
  );
}

type Actions = {
  busy: boolean;
  action: (work: () => Promise<unknown>, success?: string) => Promise<void>;
};

function Knowledge({
  base,
  documents,
  manage,
  busy,
  action,
  mode,
}: Actions & { base: string; documents: Document[]; manage: boolean; mode: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [replacement, setReplacement] = useState("");
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [searched, setSearched] = useState(false);
  return (
    <div className="space-y-5">
      {manage && (
        <form
          className={panel}
          onSubmit={(e) => {
            e.preventDefault();
            if (!file) return;
            void action(async () => {
              if (file.size > 10 * 1024 * 1024) throw new Error("Maximum size is 10 MB");
              const body = new FormData();
              body.append("file", file);
              const r = await fetch(
                `/api${base}/knowledge${replacement ? `?replaces=${replacement}` : ""}`,
                { method: "POST", body },
              );
              if (!r.ok) {
                const data = await r.json();
                throw new Error(data.detail || data.message || "Upload failed");
              }
            }, "Document queued for processing");
          }}
        >
          <h2 className="text-lg font-semibold">Add approved company knowledge</h2>
          <label htmlFor="knowledge-file">TXT, Markdown or text PDF · maximum 10 MB</label>
          <Input
            id="knowledge-file"
            type="file"
            accept=".txt,.md,.pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <label htmlFor="replacement">Document version</label>
          <select
            id="replacement"
            className="bg-background block rounded border p-2"
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
          >
            <option value="">Add new document</option>
            {documents
              .filter((d) => d.state === "ready")
              .map((d) => (
                <option key={d.id} value={d.id}>
                  Replace {d.title}
                </option>
              ))}
          </select>
          <p className="text-muted-foreground text-sm">
            Previous knowledge stays active until its replacement is ready. Scanned PDFs require OCR
            before upload.
          </p>
          <Button disabled={busy || !file}>{busy ? "Uploading..." : "Upload document"}</Button>
        </form>
      )}
      <section className={panel}>
        <h2 className="text-lg font-semibold">Knowledge library</h2>
        {!documents.length && <p>Upload your first FAQ, guide or policy to get started.</p>}
        {documents.map((d) => (
          <div
            key={d.id}
            className="flex flex-wrap items-center justify-between gap-3 border-b py-3"
          >
            <div>
              <p className="font-medium">{d.title}</p>
              <p className="text-muted-foreground text-sm">
                {d.state}
                {d.error ? ` · ${d.error}` : ""}
              </p>
            </div>
            {manage && (
              <div className="flex flex-wrap gap-2">
                {d.state === "failed" && (
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      void action(
                        () => apiClient.post(`${base}/knowledge/${d.id}/retry`, {}),
                        "Processing queued",
                      )
                    }
                  >
                    Retry
                  </Button>
                )}
                {d.state === "ready" && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      void action(
                        () => apiClient.delete(`${base}/knowledge/${d.id}?archive=true`),
                        "Document archived",
                      )
                    }
                  >
                    Archive
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`Delete ${d.title} and its indexed content?`))
                      void action(
                        () => apiClient.delete(`${base}/knowledge/${d.id}`),
                        "Document deleted",
                      );
                  }}
                >
                  Delete
                </Button>
              </div>
            )}
          </div>
        ))}
      </section>
      <form
        className={panel}
        onSubmit={(e) => {
          e.preventDefault();
          void action(async () => {
            const result = await apiClient.get<{ sources: Source[] }>(
              `${base}/knowledge/search?q=${encodeURIComponent(query)}`,
            );
            setSources(result.sources);
            setSearched(true);
          }, "Search complete");
        }}
      >
        <h2 className="text-lg font-semibold">Test your knowledge</h2>
        <label htmlFor="knowledge-search">Question or keywords</label>
        <Input
          id="knowledge-search"
          minLength={2}
          maxLength={2000}
          required
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <p className="text-muted-foreground text-sm">
          Current search mode: {mode}. Results come only from ready documents in this workspace.
        </p>
        <Button variant="outline" disabled={busy}>
          Search knowledge
        </Button>
        {searched && !sources.length && (
          <p>No matching source found. Add relevant knowledge or try more specific wording.</p>
        )}
        {sources.map((s) => (
          <blockquote key={s.id} className="rounded border p-4">
            <p className="mb-2 font-medium">
              {s.title} · page {s.page}
            </p>
            <p className="text-sm whitespace-pre-wrap">{s.text}</p>
          </blockquote>
        ))}
      </form>
    </div>
  );
}

function ReplyWorkspace({
  base,
  queryKey,
  jobs,
  configured,
  busy,
  action,
}: Actions & { base: string; queryKey: (string | undefined)[]; jobs: Job[]; configured: boolean }) {
  const [question, setQuestion] = useState("");
  const [caseSearch, setCaseSearch] = useState("");
  const [selected, setSelected] = useState("");
  const cases = useQuery({
    queryKey: [...queryKey, "cases", caseSearch],
    queryFn: () =>
      apiClient.get<Case[]>(`${base}/support/cases?q=${encodeURIComponent(caseSearch)}`),
  });
  const detail = useQuery({
    queryKey: [...queryKey, "case", selected],
    queryFn: () =>
      apiClient.get<{ case: Case; drafts: Draft[] }>(`${base}/support/cases/${selected}`),
    enabled: !!selected,
    refetchInterval: 3000,
  });
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const running = jobs.some(
    (j) => j.target_id === selected && ["queued", "processing"].includes(j.state),
  );
  if (cases.error || detail.error)
    return <p role="alert">{cases.error?.message || detail.error?.message}</p>;
  return (
    <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
      <aside className={panel}>
        <h2 className="font-semibold">Saved support cases</h2>
        <Input
          aria-label="Search support cases"
          placeholder="Search customer questions"
          maxLength={200}
          value={caseSearch}
          onChange={(e) => setCaseSearch(e.target.value)}
        />
        {!cases.data?.length && (
          <p className="text-sm">Your first customer question will appear here.</p>
        )}
        {cases.data?.map((c) => (
          <button
            data-support-navigation
            type="button"
            aria-pressed={selected === c.id}
            className={`block w-full rounded border p-3 text-left text-sm ${selected === c.id ? "bg-secondary" : ""}`}
            key={c.id}
            onClick={() => {
              setSelected(c.id);
              setRequestKey(null);
            }}
          >
            {c.question.slice(0, 100)}
          </button>
        ))}
      </aside>
      <div className="space-y-5">
        <form
          className={panel}
          onSubmit={(e) => {
            e.preventDefault();
            void action(async () => {
              const c = await apiClient.post<Case>(`${base}/support/cases`, { question });
              setSelected(c.id);
              setQuestion("");
              setRequestKey(null);
            }, "Case created");
          }}
        >
          <label htmlFor="customer-question" className="text-lg font-semibold">
            Customer question
          </label>
          <Textarea
            id="customer-question"
            required
            minLength={5}
            maxLength={10000}
            rows={5}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Paste the question your customer asked..."
          />
          <p className="text-muted-foreground text-sm">
            Avoid unnecessary personal or payment information.
          </p>
          <Button disabled={busy}>Create support case</Button>
        </form>
        {detail.data && (
          <section className={panel}>
            <h2 className="text-lg font-semibold">Reply review</h2>
            <p className="whitespace-pre-wrap">{detail.data.case.question}</p>
            <Button
              disabled={busy || running || !configured}
              onClick={() => {
                const id = requestKey || crypto.randomUUID();
                setRequestKey(id);
                void action(async () => {
                  await apiClient.post(`${base}/support/cases/${selected}/generations`, {
                    request_key: id,
                  });
                  setRequestKey(null);
                }, "Draft queued. Processing progress appears below.");
              }}
            >
              {running ? "Preparing draft..." : "Draft reply"}
            </Button>
            <p className="text-muted-foreground text-sm">
              Check the evidence before approving. This assistant never sends replies to customers.
            </p>
            {detail.data.drafts.map((draft) => (
              <DraftEditor key={draft.id} draft={draft} base={base} busy={busy} action={action} />
            ))}
          </section>
        )}
      </div>
    </div>
  );
}

export function DraftEditor({
  draft,
  base,
  busy,
  action,
}: Actions & { draft: Draft; base: string }) {
  const [snapshot, setSnapshot] = useState(draft);
  const [text, setText] = useState(draft.reply);
  const [source, setSource] = useState<Source | null>(null);
  const [feedback, setFeedback] = useState("");
  const dirty = text !== snapshot.reply;
  const changed = draft.version > snapshot.version;
  useEffect(() => {
    if (!dirty && draft.version >= snapshot.version) {
      setSnapshot(draft);
      setText(draft.reply);
    }
  }, [draft, dirty, snapshot.version]);
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("beforeunload", guard);
    const leave = (e: Event) => {
      if (dirty && !window.confirm("You have unsaved reply changes. Leave without saving?"))
        e.preventDefault();
    };
    const click = (e: MouseEvent) => {
      if (!dirty || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
      if ((e.target as HTMLElement).closest("a[href], [data-support-navigation]")) {
        leave(e);
        if (e.defaultPrevented) e.stopPropagation();
      }
    };
    window.addEventListener("support:leave", leave);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", guard);
      window.removeEventListener("support:leave", leave);
      document.removeEventListener("click", click, true);
    };
  }, [dirty]);
  return (
    <article className="space-y-3 border-t pt-5">
      <p className="font-medium">
        {draft.outcome.replaceAll("_", " ")} · revision {draft.version}
        {draft.approved_by ? " · Approved" : " · Review needed"}
      </p>
      <label htmlFor={`draft-${draft.id}`}>Reply draft</label>
      <Textarea
        id={`draft-${draft.id}`}
        rows={8}
        value={text}
        maxLength={15000}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={busy || !dirty || !text.trim()}
          onClick={() =>
            void action(async () => {
              const saved = await apiClient.patch<Draft>(`${base}/support/drafts/${draft.id}`, {
                reply: text,
                version: snapshot.version,
              });
              setSnapshot(saved);
              setText(saved.reply);
            }, "Revision saved; review it before approving")
          }
        >
          Save revision
        </Button>
        <Button
          disabled={busy || dirty || changed || !!draft.approved_by}
          onClick={() =>
            void action(
              () =>
                apiClient.post(`${base}/support/drafts/${draft.id}/approve`, {
                  version: draft.version,
                }),
              "Draft approved",
            )
          }
        >
          Approve draft
        </Button>
        <Button
          variant="outline"
          disabled={busy || dirty || changed || !draft.approved_by}
          onClick={() =>
            void action(async () => {
              await apiClient.post(`${base}/support/drafts/${draft.id}/approve`, {
                version: draft.version,
              });
              await navigator.clipboard.writeText(text);
              await apiClient.post(`${base}/support/drafts/${draft.id}/copied`, {
                version: draft.version,
              });
            }, "Reply copied. Paste it into your helpdesk when ready.")
          }
        >
          Copy approved reply
        </Button>
      </div>
      {dirty && (
        <p className="text-sm">
          Unsaved changes. Saving removes previous approval; review edited claims against the
          sources.
        </p>
      )}
      {changed && (
        <p role="alert">
          Another teammate saved a newer revision. Your text has been kept. Copy your changes before{" "}
          <button
            type="button"
            className="underline"
            onClick={() => {
              if (window.confirm("Discard your unsaved text and load the latest revision?")) {
                setSnapshot(draft);
                setText(draft.reply);
              }
            }}
          >
            loading the latest revision
          </button>
          .
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {draft.citations.map((s) => (
          <Button
            size="sm"
            variant="outline"
            key={s.id}
            onClick={() =>
              void action(
                async () =>
                  setSource(await apiClient.get<Source>(`${base}/knowledge/chunks/${s.id}`)),
                "Source opened",
              )
            }
          >
            {s.title} · page {s.page}
          </Button>
        ))}
      </div>
      {source && (
        <blockquote className="bg-secondary rounded p-4 text-sm">
          <p className="font-medium">
            {source.title} · page {source.page}
          </p>
          <p className="mt-2 whitespace-pre-wrap">{source.text}</p>
        </blockquote>
      )}
      {!!draft.history.length && (
        <details>
          <summary>Previous revisions</summary>
          {draft.history.map((h) => (
            <p key={h.version} className="my-3 rounded border p-3 text-sm whitespace-pre-wrap">
              Revision {h.version}: {h.reply}
            </p>
          ))}
        </details>
      )}
      <label htmlFor={`feedback-${draft.id}`}>Feedback for this draft</label>
      <Input
        id={`feedback-${draft.id}`}
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        maxLength={1000}
        placeholder="Was the reply useful? Report an incorrect claim or source."
      />
      <Button
        size="sm"
        variant="outline"
        disabled={busy || !feedback.trim()}
        onClick={() =>
          void action(
            () => apiClient.post(`${base}/support/drafts/${draft.id}/feedback`, { feedback }),
            "Feedback saved",
          )
        }
      >
        Save feedback
      </Button>
    </article>
  );
}

function Team({
  base,
  queryKey,
  manage,
  owner,
  busy,
  action,
}: Actions & { base: string; queryKey: (string | undefined)[]; manage: boolean; owner: boolean }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("agent");
  const [inviteToken, setInviteToken] = useState("");
  const members = useQuery({
    queryKey: [...queryKey, "members"],
    queryFn: () => apiClient.get<Member[]>(`${base}/members`),
  });
  const invitations = useQuery({
    queryKey: [...queryKey, "invitations"],
    queryFn: () => apiClient.get<Invite[]>(`${base}/invitations`),
    enabled: manage,
  });
  return (
    <div className="space-y-5">
      <section className={panel}>
        <h2 className="text-lg font-semibold">Workspace members</h2>
        {members.error && <p role="alert">{members.error.message}</p>}
        {members.data?.map((m) => (
          <div className="flex flex-wrap items-center gap-3 border-b py-3" key={m.user_id}>
            <span>{m.email}</span>
            <span className="text-sm">{m.role}</span>
            {manage && (owner || m.role !== "owner") && (
              <>
                <select
                  aria-label={`Role for ${m.email}`}
                  className="bg-background rounded border p-2"
                  value={m.role}
                  disabled={busy}
                  onChange={(e) =>
                    void action(() =>
                      apiClient.patch(`${base}/members/${m.user_id}`, { role: e.target.value }),
                    )
                  }
                >
                  {owner && <option value="owner">Owner</option>}
                  <option value="admin">Admin</option>
                  <option value="agent">Agent</option>
                </select>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`Remove ${m.email} from this workspace?`))
                      void action(() => apiClient.delete(`${base}/members/${m.user_id}`));
                  }}
                >
                  Remove
                </Button>
              </>
            )}
          </div>
        ))}
      </section>
      {manage && (
        <form
          className={panel}
          onSubmit={(e) => {
            e.preventDefault();
            void action(async () => {
              const result = await apiClient.post<{ token: string }>(`${base}/invitations`, {
                email,
                role,
              });
              setInviteToken(result.token);
              setEmail("");
            }, "Invitation created");
          }}
        >
          <h2 className="text-lg font-semibold">Invite a teammate</h2>
          <label htmlFor="teammate-email">Email address</label>
          <Input
            id="teammate-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <label htmlFor="invite-role">Role</label>
          <select
            id="invite-role"
            className="bg-background block rounded border p-2"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option value="agent">Agent</option>
            <option value="admin">Admin</option>
          </select>
          <Button disabled={busy}>Create invitation</Button>
          {inviteToken && (
            <div>
              <p>
                Share this token privately with the invited teammate. It expires in 3 days and is
                shown only now.
              </p>
              <Input readOnly aria-label="New invitation token" value={inviteToken} />
            </div>
          )}
          {invitations.data
            ?.filter((i) => !i.consumed)
            .map((i) => (
              <div className="flex items-center gap-3" key={i.id}>
                <span>
                  {i.email} · expires {new Date(i.expires_at).toLocaleDateString()}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    void action(
                      () => apiClient.delete(`${base}/invitations/${i.id}`),
                      "Invitation revoked",
                    )
                  }
                >
                  Revoke
                </Button>
              </div>
            ))}
        </form>
      )}
    </div>
  );
}

function WorkspaceSettings({
  workspace,
  base,
  busy,
  action,
}: Actions & { workspace: Workspace; base: string }) {
  const [name, setName] = useState(workspace.name);
  const [tone, setTone] = useState(workspace.tone);
  const [escalation, setEscalation] = useState(workspace.escalation);
  return (
    <form
      className={panel}
      onSubmit={(e) => {
        e.preventDefault();
        void action(() => apiClient.patch(base, { name, tone, escalation }));
      }}
    >
      <label htmlFor="settings-name">Company name</label>
      <Input
        id="settings-name"
        value={name}
        required
        maxLength={120}
        onChange={(e) => setName(e.target.value)}
      />
      <label htmlFor="settings-tone">Reply tone</label>
      <Input
        id="settings-tone"
        value={tone}
        maxLength={500}
        onChange={(e) => setTone(e.target.value)}
      />
      <label htmlFor="settings-escalation">Escalation guidance</label>
      <Textarea
        id="settings-escalation"
        value={escalation}
        maxLength={1000}
        onChange={(e) => setEscalation(e.target.value)}
      />
      <Button disabled={busy || workspace.role === "agent"}>Save settings</Button>
      <p className="text-muted-foreground text-sm">
        Every workspace member can read its approved documents and support cases.
      </p>
      {workspace.role === "owner" && (
        <Button
          type="button"
          variant="destructive"
          disabled={busy}
          onClick={() => {
            const confirmation = window.prompt(
              `Permanently delete this workspace, its documents and support history? Type ${workspace.name} to confirm.`,
            );
            if (confirmation === workspace.name)
              void action(
                () => apiClient.delete(base, { body: { name: confirmation } }),
                "Workspace deleted",
              );
          }}
        >
          Delete workspace
        </Button>
      )}
    </form>
  );
}
