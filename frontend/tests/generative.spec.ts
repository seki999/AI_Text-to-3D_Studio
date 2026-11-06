import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("unavailable neural engine leaves parametric Native editor working", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("文字描述").fill("红色立方体边长2米");
  await page.getByRole("button", { name: /① 解析/ }).click();
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await page
    .getByRole("button", { name: "Generative AI", exact: true })
    .click();
  await page.getByRole("button", { name: "Text-to-3D", exact: true }).click();
  await expect(page.getByText(/未配置 Text-to-Image Provider/)).toBeVisible({
    timeout: 15000,
  });
  await expect(
    page.getByRole("button", { name: "生成 / 重新生成参考图" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "GPU / CUDA / 模型诊断" }).click();
  await expect(page.locator(".generative-panel .diagnostics")).toBeVisible({
    timeout: 20000,
  });
  await expect(
    page.getByRole("button", { name: "↓ GLB", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".tree button")).toHaveCount(1);
  await page.getByRole("button", { name: "参数化建模", exact: true }).click();
  await expect(page.getByLabel("文字描述")).toBeVisible();
});

test("Integration Mock Passed: image → Worker → Mesh → append → edit → save → GLB roundtrip", async ({
  page,
  request,
}, info) => {
  const status = await request
    .get("http://127.0.0.1:8000/api/ai3d/engines/mock/status")
    .catch(() => null);
  test.skip(
    !status || !(await status.json()).available,
    "Explicitly enabled Mock API + Worker required; this is not real AI inference",
  );
  await page.goto("/");
  await page.getByLabel("文字描述").fill("红色立方体边长2米");
  await page.getByRole("button", { name: /① 解析/ }).click();
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await page
    .getByRole("button", { name: "Generative AI", exact: true })
    .click();
  await page.getByLabel("AI 3D 引擎").selectOption("mock");
  await expect(
    page.getByText("测试模式：仅生成测试几何，非 AI 神经网络推理。"),
  ).toBeVisible();
  await expect(
    page.getByText("Mock 测试 Worker 可用（非 AI）", { exact: true }),
  ).toBeVisible({ timeout: 20000 });
  const image = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 32;
    c.height = 32;
    const ctx = c.getContext("2d")!;
    ctx.fillStyle = "red";
    ctx.fillRect(0, 0, 32, 32);
    return c.toDataURL("image/png").split(",")[1];
  });
  const uploaded = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/ai3d/images") && r.request().method() === "POST",
  );
  await page.getByLabel("AI 参考图片", { exact: true }).setInputFiles({
    name: "reference.png",
    mimeType: "image/png",
    buffer: Buffer.from(image, "base64"),
  });
  expect((await uploaded).status()).toBe(201);
  await expect(page.getByAltText("AI 参考图片预览")).toBeVisible({
    timeout: 15000,
  });
  await page.getByLabel("确认参考图").check();
  await page.getByLabel("确认 Mock 测试模式").check();
  await page
    .getByRole("button", { name: "生成 Mock 测试 Mesh", exact: true })
    .click();
  await expect(page.locator(".ai-result strong")).toContainText("completed", {
    timeout: 120000,
  });
  await expect(page.locator(".ai-result")).toContainText("未生成纹理");
  await page.getByRole("button", { name: "预览 / 插入当前场景" }).click();
  await expect(page.locator(".tree button")).toHaveCount(2);
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await expect(page.getByText("Mock 测试资产 · 非真实 AI 结果")).toBeVisible();
  await page.getByLabel("position-X").fill("4");
  await page.getByLabel("rotation-Y").fill("30");
  await page.getByLabel("material-roughness").fill("0.2");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "↓ GLB", exact: true }).click();
  const path = info.outputPath("mock-edited.glb");
  await (await download).saveAs(path);
  const bytes = await readFile(path),
    json = JSON.parse(bytes.toString("utf8", 20, 20 + bytes.readUInt32LE(12)));
  expect(json.meshes.length).toBeGreaterThanOrEqual(2);
  expect(json.nodes.some((n: { name: string }) => n.name === "cube_0_0")).toBe(
    true,
  );
  const node = json.nodes.find((n: { name: string }) =>
    n.name?.startsWith("asset_"),
  );
  expect(node.translation[0]).toBeCloseTo(4);
  expect(node.extras.asset_metadata.provenance.kind).toBe("mock");
  const name = "V03 Mock integration " + Date.now();
  await page.getByLabel("项目名称").fill(name);
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("项目已保存到 SQLite")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "打开项目", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await expect(page.locator(".tree button")).toHaveCount(2);
  await page.locator(".tree button").nth(1).click();
  await expect(page.getByLabel("position-X")).toHaveValue("4");
  await expect(page.getByText("Mock 测试资产 · 非真实 AI 结果")).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/v03-mock-integration.png",
  });
  await page
    .locator('input[type=file][accept=".json,.glb,.gltf,.obj"]')
    .setInputFiles(path);
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
});
