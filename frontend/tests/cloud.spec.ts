import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";

test("Cloud: missing key blocks generation and never sends a task", async ({
  page,
}) => {
  let submissions = 0;
  await page.route("**/api/ai3d/engines/meshy/status", (r) =>
    r.fulfill({
      json: {
        available: false,
        configured: false,
        errors: ["尚未配置 Meshy API Key"],
      },
    }),
  );
  await page.route("**/api/ai3d/jobs/cloud", (r) => {
    submissions++;
    return r.fulfill({ status: 503, json: { detail: "No key" } });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Generative AI", exact: true })
    .click();
  await page.getByLabel("AI 3D 引擎").selectOption("meshy");
  await expect(
    page.getByText("尚未配置 Meshy API Key", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("云端推理 · 可能产生费用", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("确认云端费用和上传").check();
  await page.getByLabel("确认云端服务条款").check();
  await expect(
    page.getByRole("button", { name: "生成云端 3D（可能收费）", exact: true }),
  ).toBeDisabled();
  expect(submissions).toBe(0);
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
});

test("API Contract only: explicit cloud submit → fixture Mesh → edit → save → reopen → GLB", async ({
  page,
  request,
}, info) => {
  const id = randomUUID(),
    source = randomUUID();
  const metadata = {
    asset_id: source,
    generator: "meshy",
    model_version: "fixture",
    source_prompt: "API Contract only",
    source_image: null,
    generated_at: new Date().toISOString(),
    geometry_format: "GLB",
    texture_assets: [],
    license_metadata: {
      name: "local MIT fixture",
      restrictions: ["not a real API generated model"],
    },
    provenance: { kind: "mock" },
  };
  const bytes = await readFile("../examples/cube.glb");
  const scene = {
    version: "1.0",
    name: "Cloud API Contract fixture",
    units: "meters",
    environment: { ground: true, background: "#171a22" },
    objects: [
      {
        id: "asset_" + source,
        name: "API Contract 测试素材（非真实 AI）",
        type: "imported",
        position: [0, 0, 0],
        rotation: [0, 0, 0],
        scale: [1, 1, 1],
        parameters: {},
        asset: metadata,
      },
    ],
  };
  const saved = await request.post(
    "http://127.0.0.1:8000/api/models/snapshot",
    { data: { scene, glb: bytes.toString("base64") } },
  );
  expect(saved.ok()).toBeTruthy();
  const assetId = (await saved.json()).id;
  let submitted = 0,
    polled = 0;
  const result = {
    id,
    engine: "meshy",
    is_mock: true,
    status: "completed",
    stage: "API Contract fixture completed",
    remote_id: "text:" + id,
    progress: null,
    progress_kind: "stage",
    error: null,
    asset_id: assetId,
    model_url: `/api/models/${assetId}/download?format=glb`,
    original_available: false,
    stats: {
      meshes: 1,
      vertices: 8,
      triangles: 12,
      texture_status: "未生成纹理",
    },
    metadata,
    created: new Date().toISOString(),
  };
  await page.route("**/api/ai3d/engines/meshy/status", (r) =>
    r.fulfill({ json: { available: true, configured: true } }),
  );
  await page.route("**/api/ai3d/jobs", (r) =>
    r.fulfill({ json: submitted ? [result] : [] }),
  );
  await page.route("**/api/ai3d/jobs/cloud", async (r) => {
    submitted++;
    const body = r.request().postDataJSON();
    expect(body.prompt).toBe("生成一条红色、有翅膀的幻想龙。");
    expect(body.cloud_consent && body.license_acknowledged).toBe(true);
    await r.fulfill({
      status: 202,
      json: {
        ...result,
        status: "pending",
        asset_id: null,
        stage: "API Contract pending",
      },
    });
  });
  await page.route("**/api/ai3d/jobs/" + id, (r) => {
    polled++;
    return r.fulfill({ json: result });
  });
  await page.goto("/");
  await page.getByLabel("文字描述").fill("红色立方体边长2米");
  await page.getByRole("button", { name: /① 解析/ }).click();
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await page
    .getByRole("button", { name: "Generative AI", exact: true })
    .click();
  await page.getByLabel("AI 3D 引擎").selectOption("meshy");
  await expect(page.getByLabel("云端生成描述")).toHaveValue(
    "生成一条红色、有翅膀的幻想龙。",
  );
  expect(submitted).toBe(0);
  await page.getByLabel("确认云端费用和上传").check();
  await page.getByLabel("确认云端服务条款").check();
  await page
    .getByRole("button", { name: "生成云端 3D（可能收费）", exact: true })
    .click();
  await expect(page.locator(".ai-result strong")).toContainText("completed");
  expect(submitted).toBe(1);
  expect(polled).toBeGreaterThan(0);
  await page.getByRole("button", { name: "预览 / 插入当前场景" }).click();
  await expect(page.locator(".tree button")).toHaveCount(2);
  await page.getByLabel("position-X").fill("4");
  await page.getByLabel("rotation-Y").fill("30");
  await page.getByLabel("scale-X").fill("1.5");
  await page.getByLabel("material-roughness").fill("0.2");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ GLB", exact: true }).click();
  const exportPath = info.outputPath("cloud-contract-edited.glb");
  await (await download).saveAs(exportPath);
  const exported = await readFile(exportPath);
  const gltf = JSON.parse(
    exported.toString("utf8", 20, 20 + exported.readUInt32LE(12)),
  );
  const node = gltf.nodes.find(
    (n: { name: string }) => n.name === "asset_" + source,
  );
  expect(node.translation[0]).toBeCloseTo(4);
  expect(node.scale[0]).toBeCloseTo(1.5);
  expect(node.extras.asset_metadata.provenance.kind).toBe("mock");
  expect(
    gltf.nodes.some(
      (n: { extras?: { provider_gltf_asset?: { version: string } } }) =>
        n.extras?.provider_gltf_asset?.version === "2.0",
    ),
  ).toBe(true);
  const name = "Cloud contract NOT real AI " + Date.now();
  await page.getByLabel("项目名称").fill(name);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("项目已保存到 SQLite")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "打开项目", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.locator(".tree button")).toHaveCount(2);
  await page.locator(".tree button").nth(1).click();
  await expect(page.getByLabel("position-X")).toHaveValue("4");
  await expect(page.getByLabel("scale-X")).toHaveValue("1.5");
  await page.screenshot({ path: "../docs/screenshots/cloud-api-contract.png" });
  await page
    .locator('input[type=file][accept=".json,.glb,.gltf,.obj"]')
    .setInputFiles(exportPath);
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
});
