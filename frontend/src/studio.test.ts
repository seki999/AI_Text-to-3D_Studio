import { describe, it, expect, vi, afterEach } from "vitest";
import { api } from "./api";
import { useStudio, empty } from "./store";
describe("scene editing", () => {
  it("supports history, parameter editing and redo", () => {
    useStudio.getState().setScene({ ...empty, name: "house" });
    useStudio.getState().setScene({ ...empty, name: "updated" });
    useStudio.getState().undo();
    expect(useStudio.getState().scene.name).toBe("house");
    useStudio.getState().redo();
    expect(useStudio.getState().scene.name).toBe("updated");
  });
});
describe("API", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("sends text and provider to parser", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ scene: empty }) });
    vi.stubGlobal("fetch", fetch);
    await api("/parse-text", "POST", { text: "红色立方体", provider: "rule" });
    expect(JSON.parse(fetch.mock.calls[0][1].body).text).toBe("红色立方体");
  });
  it("surfaces server errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ detail: "未找到 Blender" }),
      }),
    );
    await expect(api("/generate-model", "POST", empty)).rejects.toThrow(
      "未找到 Blender",
    );
  });
});
