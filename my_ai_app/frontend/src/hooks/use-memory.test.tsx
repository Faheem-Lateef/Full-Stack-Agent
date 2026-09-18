import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/lib/api-client";
import { useMemoryFiles } from "./use-memory";

const mocks = vi.hoisted(() => ({ list: vi.fn(), userId: "user-a" }));
vi.mock("@/stores", () => ({ useAuthStore: (select: (s: unknown) => unknown) => select({ user: { id: mocks.userId } }) }));
vi.mock("@/lib/memory-api", () => ({ listMemoryFiles: mocks.list, saveMemoryFile: vi.fn(), deleteMemoryFile: vi.fn() }));
beforeEach(() => { vi.clearAllMocks(); mocks.userId = "user-a"; });
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
let client: QueryClient;
beforeEach(() => { client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); });

describe("memory availability and cache scope", () => {
  it("shows a disabled state only for MEMORY_DISABLED", async () => {
    mocks.list.mockRejectedValue(new ApiError(503, "Disabled", { code: "MEMORY_DISABLED" }));
    const { result } = renderHook(() => useMemoryFiles(), { wrapper });
    await waitFor(() => expect(result.current.disabled).toBe(true));
    expect(result.current.error).toBeNull();
  });
  it("keeps database outages retryable", async () => {
    mocks.list.mockRejectedValue(new ApiError(503, "Temporarily unavailable", { code: "MEMORY_UNAVAILABLE" }));
    const { result } = renderHook(() => useMemoryFiles(), { wrapper });
    await waitFor(() => expect(result.current.error).toBe("Temporarily unavailable"));
    expect(result.current.disabled).toBe(false);
  });
  it("never shows one user's cached notes to the next user", async () => {
    mocks.list.mockResolvedValueOnce({ items: [{ path: "private.md", size_chars: 10, version: "1" }], total: 1, truncated: false });
    const { result, rerender } = renderHook(() => useMemoryFiles(), { wrapper });
    await waitFor(() => expect(result.current.files).toHaveLength(1));
    mocks.list.mockImplementation(() => new Promise(() => {}));
    mocks.userId = "user-b";
    rerender();
    expect(result.current.files).toEqual([]);
  });
});
