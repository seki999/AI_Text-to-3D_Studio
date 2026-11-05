import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
test("Native works without Blender and GLB roundtrips live transform and PBR", async ({
  page,
}, info) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { blender_available: false } }),
  );
  let blenderRequests = 0;
  await page.route("**/api/generate-model", (r) => {
    blenderRequests++;
    return r.abort();
  });
  await page.goto("/");
  await page.getByLabel("文字描述").fill("生成一个红色立方体，边长2米。");
  await page.getByRole("button", { name: /① 解析/ }).click();
  await page.getByLabel("建模引擎").selectOption("native");
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await page.getByLabel("position-X").fill("3");
  await page.getByLabel("rotation-Y").fill("30");
  await page.getByLabel("scale-Z").fill("1.5");
  await page.getByLabel("材质预设").selectOption("Glass");
  await page.getByLabel("material-roughness").fill("0.15");
  const readBounds = () =>
    page.evaluate(async () => {
      const load = new Function("p", "return import(p)");
      const { getExportModel } = await load("/src/services/export.ts");
      const { Box3, Vector3 } = await load("/node_modules/.vite/deps/three.js");
      const box = new Box3().setFromObject(getExportModel());
      return { min: box.min.toArray(), max: box.max.toArray() };
    });
  const before = await readBounds();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ GLB", exact: true }).click();
  const download = await downloading;
  const path = info.outputPath("edited.glb");
  await download.saveAs(path);
  const bytes = await readFile(path);
  expect(bytes.toString("ascii", 0, 4)).toBe("glTF");
  const json = JSON.parse(
    bytes.toString("utf8", 20, 20 + bytes.readUInt32LE(12)),
  );
  const obj = json.nodes.find((n: { name: string }) => n.name === "cube_0_0");
  expect(obj.translation[0]).toBeCloseTo(3);
  expect(obj.scale[2]).toBeCloseTo(1.5);
  expect(obj.rotation[1]).toBeCloseTo(Math.sin(Math.PI / 12));
  expect(
    json.materials[0].pbrMetallicRoughness.baseColorFactor[0],
  ).toBeGreaterThan(0.7);
  expect(json.materials[0].alphaMode).toBe("BLEND");
  expect(json.materials[0].pbrMetallicRoughness.roughnessFactor).toBeCloseTo(
    0.15,
  );
  expect(blenderRequests).toBe(0);
  expect(
    json.nodes.some((n: { name: string }) =>
      /grid|axes|helper|transformcontrols/i.test(n.name),
    ),
  ).toBe(false);
  await page.locator("input[type=file]").setInputFiles(path);
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  const after = await readBounds();
  for (let i = 0; i < 3; i++) {
    expect(after.min[i]).toBeCloseTo(before.min[i], 4);
    expect(after.max[i]).toBeCloseTo(before.max[i], 4);
  }
  await page.screenshot({ path: info.outputPath("native-edited.png") });
});
test("actual mouse gizmo drag synchronizes state and has one undo step", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("文字描述").fill("红色立方体边长2米");
  await page.getByRole("button", { name: /① 解析/ }).click();
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByLabel("position-X")).toHaveValue("0");
  await page.waitForTimeout(1000);
  const points = await page.evaluate(async () => {
    const load = new Function("path", "return import(path)");
    const { getViewerCamera } = await load("/src/viewer/runtime.ts");
    const { getExportModel } = await load("/src/services/export.ts");
    const camera = getViewerCamera(),
      root = getExportModel(),
      node = root.children[0];
    const { Box3, Vector3 } = await load("/node_modules/.vite/deps/three.js");
    const center = new Box3().setFromObject(node).getCenter(new Vector3());
    const factor =
      center.distanceTo(camera.position) *
      Math.min(
        (1.9 * Math.tan((Math.PI * camera.fov) / 360)) / camera.zoom,
        7,
      ) *
      0.25;
    const canvas = document.querySelector("canvas")!,
      rect = canvas.getBoundingClientRect();
    const project = (x: number) => {
      const p = center.clone();
      p.x += factor * x;
      p.project(camera);
      return {
        x: rect.left + ((p.x + 1) * rect.width) / 2,
        y: rect.top + ((1 - p.y) * rect.height) / 2,
      };
    };
    return { start: project(0.5), end: project(1.25) };
  });
  await page.mouse.move(points.start.x, points.start.y);
  await page.mouse.down();
  await page.mouse.move(points.end.x, points.end.y, { steps: 20 });
  await page.mouse.up();
  await expect(page.getByLabel("position-X")).not.toHaveValue("0");
  const moved = Number(await page.getByLabel("position-X").inputValue());
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ GLB", exact: true }).click();
  const file = await (await downloading).path();
  const bytes = await readFile(file!),
    gltf = JSON.parse(bytes.toString("utf8", 20, 20 + bytes.readUInt32LE(12)));
  expect(
    gltf.nodes.find((n: { name: string }) => n.name === "cube_0_0")
      .translation[0],
  ).toBeCloseTo(moved);
  await page.locator("canvas").click({ position: { x: 10, y: 10 } });
  await page.keyboard.press("Control+z");
  // Re-select using the object tree after clicking the empty viewport.
  await page.locator(".tree button").first().click();
  await expect(page.getByLabel("position-X")).toHaveValue("0");
});
