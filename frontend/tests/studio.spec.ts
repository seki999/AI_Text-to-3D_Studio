import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
test("text → Scene → Blender → real GLB → viewer → download", async ({
  page,
  request,
}) => {
  const health = await request
    .get("http://127.0.0.1:8000/api/health")
    .catch(() => null);
  test.skip(
    !health || !(await health.json()).blender_available,
    "Running backend and installed Blender are required",
  );
  await page.goto("/");
  await page.getByLabel("文字描述").fill("生成一个红色立方体，边长2米。");
  await page.getByRole("button", { name: /① 解析/ }).click();
  await expect(page.getByText("解析完成 · 请检查参数后生成")).toBeVisible();
  await page.getByLabel("建模引擎").selectOption("blender");
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible({
    timeout: 120000,
  });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ GLB", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("model.glb");
});
test("parser errors are displayed", async ({ page }) => {
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { blender_available: false } }),
  );
  await page.route("**/api/projects", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/jobs", (r) => r.fulfill({ json: [] }));
  await page.route("**/api/parse-text", (r) =>
    r.fulfill({ status: 422, json: { detail: "无法识别描述" } }),
  );
  await page.goto("/");
  await page.getByLabel("文字描述").fill("不存在的类型");
  await page.getByRole("button", { name: /① 解析/ }).click();
  await expect(page.getByRole("alert")).toContainText("无法识别描述");
  await expect(
    page.getByRole("button", { name: "↓ GLB", exact: true }),
  ).toBeDisabled();
});

test("Japanese house, screenshot and GLB re-import", async ({
  page,
  request,
}, testInfo) => {
  const health = await request
    .get("http://127.0.0.1:8000/api/health")
    .catch(() => null);
  test.skip(
    !health || !(await health.json()).blender_available,
    "Running backend and installed Blender are required",
  );
  await page.goto("/");
  await page.getByRole("button", { name: "日式住宅", exact: true }).click();
  await page.getByRole("button", { name: /① 解析/ }).click();
  await expect(page.getByLabel("roof_color")).toBeVisible();
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible({
    timeout: 120000,
  });
  await page.waitForTimeout(1200); // Let Bounds camera interpolation and WebGL drawing settle.
  const visiblePixels = await page.locator("canvas").evaluate((canvas) => {
    const gl = (canvas as HTMLCanvasElement).getContext("webgl2")!;
    const pixels = new Uint8Array(
      gl.drawingBufferWidth * gl.drawingBufferHeight * 4,
    );
    gl.readPixels(
      0,
      0,
      gl.drawingBufferWidth,
      gl.drawingBufferHeight,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      pixels,
    );
    let bright = 0;
    for (let i = 0; i < pixels.length; i += 4)
      if (pixels[i] > 150 && pixels[i + 1] > 150 && pixels[i + 2] > 150)
        bright++;
    return bright;
  });
  expect(visiblePixels).toBeGreaterThan(10000); // Mesh must actually render, not just finish loading.
  await page.screenshot({
    path: "../docs/screenshots/house.png",
    fullPage: true,
  });
  const projectName = "E2E house " + Date.now();
  await page.getByLabel("项目名称").fill(projectName);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("项目已保存到 SQLite")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "打开项目", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(projectName) }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  const downloading = page.waitForEvent("download");
  await page.locator(".tree button").first().click();
  await page.getByLabel("rotation-Y").fill("45");
  await page.getByLabel("材质预设").selectOption("Metal");
  await page.getByRole("button", { name: "↓ GLB", exact: true }).click();
  const download = await downloading;
  const path = testInfo.outputPath("house.glb");
  await download.saveAs(path);
  const bytes = await readFile(path),
    json = JSON.parse(bytes.toString("utf8", 20, 20 + bytes.readUInt32LE(12)));
  const house = json.nodes.find(
    (n: { name: string }) => n.name === "house_0_0",
  );
  expect(house.rotation[1]).toBeCloseTo(Math.sin(Math.PI / 8));
  expect(
    json.materials.every(
      (m: { pbrMetallicRoughness: { metallicFactor: number } }) =>
        m.pbrMetallicRoughness.metallicFactor === 1,
    ),
  ).toBe(true);
  await page.locator("input[type=file]").setInputFiles(path);
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
});
