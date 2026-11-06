import { describe, it, expect, vi, afterEach } from "vitest";
import { api } from "./api";
import { useStudio, empty } from "./store";
import type { AssetMetadata, Object3DData } from "./types";
describe("scene editing", () => {
  it("keeps generated asset identity and license through copy, edit and undo", () => {
    const asset: AssetMetadata = {
      asset_id: "00000000-0000-0000-0000-000000000001",
      generator: "mock",
      model_version: "test-1",
      source_prompt: "test only",
      source_image: null,
      generated_at: "2026-11-06T00:00:00Z",
      geometry_format: "GLB",
      texture_assets: [],
      license_metadata: { name: "MIT test fixture" },
      provenance: { kind: "mock" },
    };
    const object: Object3DData = {
      id: "asset_test",
      name: "Mock fixture",
      type: "imported",
      asset,
      parent: null,
      visible: true,
      position: [0, 0, 0],
      rotation: [0, 0, 0],
      scale: [1, 1, 1],
      parameters: {},
    };
    const s = useStudio.getState();
    s.setScene({ ...empty, objects: [object] });
    s.select(object.id);
    s.duplicate();
    const copy = useStudio.getState().scene.objects[1];
    expect(copy.id).not.toBe(object.id);
    expect(copy.asset).toEqual(asset);
    s.edit(copy.id, { visible: false, position: [4, 0, 0] });
    s.undo();
    expect(useStudio.getState().scene.objects[1].visible).toBe(true);
    expect(useStudio.getState().scene.objects[0].asset?.provenance.kind).toBe(
      "mock",
    );
  });
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
