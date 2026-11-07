import { test, expect } from "@playwright/test";

test("V04 local asset library persists independent GLB and protects project references", async ({page}, info) => {
  await page.goto("/");
  await page.getByLabel("文字描述").fill("红色立方体边长2米");
  await page.getByRole("button",{name:/① 解析/}).click();await page.getByRole("button",{name:/② 生成/}).click();
  await expect(page.getByText("模型已加载 · 拖动旋转查看")).toBeVisible();
  await page.getByRole("button",{name:"资产库",exact:true}).click();
  const description="V04 library "+Date.now();await page.getByLabel("资产描述").fill(description);
  await page.getByRole("button",{name:"将当前模型加入资产库"}).click();
  await page.getByLabel("搜索资产").fill(description);
  const card=page.locator(".library-card").filter({hasText:description});await expect(card).toHaveCount(1,{timeout:20000});
  await expect(card.getByRole("img")).toBeVisible();
  await card.getByRole("button",{name:"收藏",exact:true}).click();await expect(card.getByRole("button",{name:"取消收藏"})).toBeVisible();
  await card.getByRole("button",{name:"导入当前项目"}).click();await expect(page.locator(".tree button")).toHaveCount(2,{timeout:15000});
  await page.getByLabel("position-X").fill("4");
  const project="V04 persisted "+Date.now();await page.getByLabel("项目名称").fill(project);await page.getByRole("button",{name:"保存",exact:true}).click();
  await expect(page.getByText("项目已保存到 SQLite")).toBeVisible();
  await page.getByRole("button",{name:"刷新资产库"}).click();await expect(card.getByRole("button",{name:"项目引用中，不能删除"})).toBeDisabled();
  await page.reload();await page.getByRole("button",{name:"打开项目",exact:true}).click();await page.getByRole("button",{name:new RegExp(project)}).click();
  await expect(page.locator(".tree button")).toHaveCount(2,{timeout:15000});await page.locator(".tree button").nth(1).click();await expect(page.getByLabel("position-X")).toHaveValue("4");
  const download=page.waitForEvent("download");await page.getByRole("button",{name:"↓ GLB",exact:true}).click();await (await download).saveAs(info.outputPath("library-reopened.glb"));
});

test("V04 real acceptance stays Skipped without fee authorization", async ({page})=>{
  await page.goto("/");await page.getByRole("button",{name:"设置 / 验收",exact:true}).click();
  await page.getByRole("button",{name:"仅生成未执行报告",exact:true}).click();
  await expect(page.locator(".ai-result strong")).toContainText("skipped");await expect(page.locator(".ai-result")).toContainText("未创建");
});

test("V04 WebGL context loss retains Scene and recovers Native view",async({page})=>{
  await page.goto("/");await page.getByLabel("文字描述").fill("红色立方体边长2米");await page.getByRole("button",{name:/① 解析/}).click();await page.getByRole("button",{name:/② 生成/}).click();
  await expect(page.locator(".tree button")).toHaveCount(1);
  await page.evaluate(()=>{const canvas=document.querySelector("canvas")!;const gl=canvas.getContext("webgl2")??canvas.getContext("webgl");gl?.getExtension("WEBGL_lose_context")?.loseContext();});
  await expect(page.getByText(/WebGL 上下文已丢失/)).toBeVisible();await expect(page.locator(".tree button")).toHaveCount(1);
  await page.getByRole("button",{name:"重新创建视图"}).click();await expect(page.getByText(/WebGL 上下文已丢失/)).toHaveCount(0);
  await expect(page.getByRole("button",{name:"↓ GLB",exact:true})).toBeEnabled();
});
