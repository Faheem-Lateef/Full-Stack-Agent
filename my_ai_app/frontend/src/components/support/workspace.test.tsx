import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DraftEditor } from "./workspace";

const mocks = vi.hoisted(() => ({ patch: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api-client", () => ({ apiClient: { patch: mocks.patch, post: mocks.post } }));
const draft = {
  id: "draft-1",
  reply: "Original reply",
  outcome: "answerable",
  version: 1,
  citations: [],
  history: [],
};
beforeEach(() => vi.clearAllMocks());

describe("support draft review", () => {
  it("keeps unsaved changes and the original version when another teammate saves", async () => {
    const action = vi.fn(async (work: () => Promise<unknown>) => {
      try {
        await work();
      } catch {
        /* Parent displays the error. */
      }
    });
    mocks.patch.mockRejectedValue(new Error("Conflict"));
    const view = render(
      <DraftEditor draft={draft} base="/workspaces/test" busy={false} action={action} />,
    );
    fireEvent.change(screen.getByLabelText("Reply draft"), {
      target: { value: "My unsaved reply" },
    });
    view.rerender(
      <DraftEditor
        draft={{ ...draft, version: 2, reply: "Teammate reply" }}
        base="/workspaces/test"
        busy={false}
        action={action}
      />,
    );
    expect(screen.getByLabelText("Reply draft")).toHaveValue("My unsaved reply");
    expect(screen.getByRole("alert")).toHaveTextContent("newer revision");
    fireEvent.click(screen.getByRole("button", { name: "Save revision" }));
    await waitFor(() =>
      expect(mocks.patch).toHaveBeenCalledWith("/workspaces/test/support/drafts/draft-1", {
        reply: "My unsaved reply",
        version: 1,
      }),
    );
    expect(screen.getByLabelText("Reply draft")).toHaveValue("My unsaved reply");
    expect(screen.getByRole("button", { name: "Approve draft" })).toBeDisabled();
  });

  it("requires saving edits before approval or copying", () => {
    render(
      <DraftEditor
        draft={{ ...draft, approved_by: "reviewer" }}
        base="/workspaces/test"
        busy={false}
        action={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Copy approved reply" })).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Reply draft"), { target: { value: "Changed claim" } });
    expect(screen.getByRole("button", { name: "Copy approved reply" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Approve draft" })).toBeDisabled();
  });

  it("updates the revision only after a successful save", async () => {
    mocks.patch.mockResolvedValue({ ...draft, reply: "Revised reply", version: 2 });
    render(
      <DraftEditor
        draft={draft}
        base="/workspaces/test"
        busy={false}
        action={async (work) => {
          await work();
        }}
      />,
    );
    fireEvent.change(screen.getByLabelText("Reply draft"), { target: { value: "Revised reply" } });
    fireEvent.click(screen.getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(mocks.patch).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByLabelText("Reply draft")).toHaveValue("Revised reply"));
  });
});
