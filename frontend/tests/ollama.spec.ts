import { test, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
test("live local Ollama Qwen creates independent colored objects and Native meshes", async ({
  page,
}) => {
  test.skip(
    process.env.STUDIO_LIVE_OLLAMA !== "1",
    "Explicit live local inference opt-in required",
  );
  await page.goto("/");
  await page.getByLabel("解析引擎").selectOption("ollama");
  await page.getByRole("button", { name: "检查连接 / 刷新模型" }).click();
  await expect(page.getByText("连接成功，请选择已安装模型")).toBeVisible();
  await page
    .getByLabel("Ollama 模型")
    .selectOption(process.env.STUDIO_LIVE_MODEL ?? "qwen3-coder:30b");
  await page.getByLabel("timeout", { exact: true }).fill("180");
  await page.getByLabel("num_ctx").fill("4096");
  await page
    .getByLabel("文字描述")
    .fill("创建一张桌子，在桌子左边放一把红色椅子，右边放一个蓝色柜子。");
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/parse-text") && r.request().method() === "POST",
    { timeout: 180000 },
  );
  await page.getByRole("button", { name: /① 解析/ }).click();
  const result = await (await response).json();
  expect(result.scene).toBeTruthy();
  expect(result.scene.objects).toHaveLength(3);
  const table = result.scene.objects.find(
      (o: { type: string }) => o.type === "table",
    ),
    chair = result.scene.objects.find(
      (o: { type: string }) => o.type === "chair",
    ),
    cabinet = result.scene.objects.find(
      (o: { type: string }) => o.type === "cabinet",
    );
  expect(chair.parameters.color).toBe("#e34b4b");
  expect(cabinet.parameters.color).toBe("#3985ed");
  expect(chair.position[0]).toBeLessThan(table.position[0]);
  expect(cabinet.position[0]).toBeGreaterThan(table.position[0]);
  await page.getByRole("button", { name: /② 生成/ }).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await expect(page.locator(".tree button")).toHaveCount(3);
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "../docs/screenshots/ollama-room.png" });
  await writeFile(
    "../examples/ollama-room.json",
    JSON.stringify(result.scene, null, 2),
  );
});
