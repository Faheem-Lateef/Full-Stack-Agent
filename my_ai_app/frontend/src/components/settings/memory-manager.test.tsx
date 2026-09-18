import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError } from "@/lib/api-client";
import { MemoryManager } from "./memory-manager";

const mocks = vi.hoisted(() => ({ save: vi.fn(), refresh: vi.fn() }));
vi.mock("@/hooks", () => ({ useMemoryFiles: () => ({
  files: [], truncated: false, disabled: false, isLoading: false, error: null,
  save: mocks.save, refresh: mocks.refresh, remove: vi.fn(),
}) }));
vi.mock("@/components/chat", () => ({ MarkdownContent: () => null }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

beforeEach(() => { vi.clearAllMocks(); });
function fillDraft() {
  render(<MemoryManager />);
  fireEvent.click(screen.getByRole("button", { name: "New file" }));
  fireEvent.change(screen.getByLabelText("File name"), { target: { value: "preferences" } });
  fireEvent.change(screen.getByLabelText("Content"), { target: { value: "Keep this draft" } });
}

describe("memory editor", () => {
  it.each([
    new Error("Network unavailable"),
    new ApiError(409, "Conflict", { code: "MEMORY_VERSION_CONFLICT" }),
  ])("keeps the draft after a failed save: %s", async (error) => {
    mocks.save.mockRejectedValue(error);
    fillDraft();
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(mocks.refresh).toHaveBeenCalled());
    expect(screen.getByLabelText("Content")).toHaveValue("Keep this draft");
    expect(screen.getByRole("dialog")).toBeVisible();
  });
  it("normalizes the file name and closes only after a successful save", async () => {
    mocks.save.mockResolvedValue({ path: "preferences.md", version: "1" });
    fillDraft();
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mocks.save).toHaveBeenCalledWith("preferences.md", { content: "Keep this draft", version: null });
  });
});
