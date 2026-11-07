import { useEffect, useState } from "react";
import { api } from "../api";
import { useStudio } from "../store";
import { getExportModel, exportGLTF } from "../services/export";
import { previewPNG } from "../services/assetLoading";
type Entry = { id:string; description:string; provider:string; created:string; favorite:boolean; is_mock:boolean; protected:boolean; bytes:number; thumbnail:string; stats:{triangles:number;vertices:number;texture_status:string};metadata:Record<string,unknown> };
const bridge = () => (window as unknown as { chrome?: { webview?: { postMessage: (value:string) => void } } }).chrome?.webview;
async function currentSnapshot() {
  const binary = new Uint8Array(await exportGLTF(true,getExportModel(),true) as ArrayBuffer);
  let text = "";for(let i=0;i<binary.length;i+=32768)text+=String.fromCharCode(...binary.subarray(i,i+32768));
  return api<{id:string}>("/models/snapshot","POST",{scene:useStudio.getState().scene,glb:btoa(text)});
}
export function AssetLibrary({onInsert,onError}:{onInsert:(id:string)=>Promise<void>;onError:(s:string)=>void}) {
  const [items,setItems]=useState<Entry[]>([]),[query,setQuery]=useState(""),[favorite,setFavorite]=useState(false),[busy,setBusy]=useState(false),[description,setDescription]=useState("");
  const refresh=()=>api<Entry[]>("/library?q="+encodeURIComponent(query)+"&favorite="+favorite).then(setItems);
  useEffect(()=>{refresh().catch(e=>onError(String(e)));},[query,favorite]);
  async function action(work:()=>Promise<void>) {setBusy(true);try{await work();await refresh();}catch(e){onError(String(e));}finally{setBusy(false);}}
  async function thumbnail(id:string) {const data=await previewPNG(`/api/models/${id}/download?format=glb`);await api(`/library/${id}/thumbnail`,"PUT",{data});}
  return <section><div className="section-title">3D ASSET LIBRARY</div><h2>我的本地资产</h2>
    <p className="tiny muted">模型保存在独立资产目录。项目引用的资产禁止删除；任何预览与处理均在本地进行。</p>
    <input aria-label="资产描述" placeholder="当前模型的资产描述" value={description} onChange={e=>setDescription(e.target.value)} />
    <button disabled={busy} onClick={()=>action(async()=>{const source=await currentSnapshot();const item=await api<{id:string}>("/library","POST",{model_id:source.id,description:description||useStudio.getState().scene.name});try{await thumbnail(item.id);}catch{/* Keep valid GLB even when thumbnail GPU rendering is unavailable. */}})}>将当前模型加入资产库</button>
    <input aria-label="搜索资产" placeholder="搜索描述或 Provider" value={query} onChange={e=>setQuery(e.target.value)} />
    <label><input type="checkbox" checked={favorite} onChange={e=>setFavorite(e.target.checked)} />仅收藏</label>
    <button onClick={()=>action(refresh)}>刷新资产库</button>
    {items.map(item=><article className="library-card" key={item.id}>
      <img alt={item.description+" 缩略图"} src={item.thumbnail+"?v="+item.bytes} width={256} height={192} />
      <strong>{item.description}</strong><p className="tiny">{item.is_mock?"Mock · 非 AI":item.provider==="meshy"||item.provider==="hunyuan3d-2.1"?"AI 生成来源":"本地 / 导入"} · {item.provider}<br/>{item.created}<br/>{item.stats.triangles?.toLocaleString()} 面 / {item.stats.vertices?.toLocaleString()} 顶点 · {(item.bytes/1048576).toFixed(2)} MB<br/>{item.stats.texture_status}</p>
      {item.stats.triangles>250000&&<p className="warning">高面数资产，加载与导出可能较慢。</p>}
      <div className="row"><button disabled={busy} onClick={()=>action(()=>onInsert(item.id))}>导入当前项目</button><button disabled={busy} onClick={()=>action(async()=>{await api(`/library/${item.id}`,"PATCH",{favorite:!item.favorite});})}>{item.favorite?"取消收藏":"收藏"}</button></div>
      <a href={`/api/models/${item.id}/download?format=glb`} download>导出资产 GLB</a>
      <button disabled={busy} onClick={()=>action(()=>thumbnail(item.id))}>重新生成缩略图</button>
      <button disabled={busy} onClick={()=>{if(confirm("创建独立的 20000 面简化副本？原模型保留；带纹理模型将拒绝简化。"))action(async()=>{await api(`/library/${item.id}/simplify`,"POST",{target_faces:20000,confirmed:true});});}}>创建简化副本</button>
      <button disabled={busy||item.protected} onClick={()=>{if(confirm("删除此资产库条目及其文件？"))action(async()=>{await api(`/library/${item.id}`,"DELETE");});}}>{item.protected?"项目引用中，不能删除":"删除资产"}</button>
      <details><summary>来源、许可证和 Mesh 信息</summary><pre className="diagnostics">{JSON.stringify({metadata:item.metadata,stats:item.stats},null,2)}</pre></details>
    </article>)}
    {!items.length&&<p className="muted">资产库为空，生成或导入模型后可保存到这里。</p>}
  </section>;
}
type Acceptance = {id:string;status:string;reason?:string;stage?:string;remote_id?:string;asset_id?:string;checks:Record<string,unknown>};
export function StudioSettings({onInsert,onError}:{onInsert:(id:string)=>Promise<void>;onError:(s:string)=>void}) {
  const [info,setInfo]=useState<Record<string,unknown>>({}),[key,setKey]=useState(false),[report,setReport]=useState<Acceptance|null>(null),[paid,setPaid]=useState(false),[account,setAccount]=useState<Record<string,unknown>|null>(null),[busy,setBusy]=useState(false),[log,setLog]=useState("");
  const refresh=async()=>{setInfo(await api("/desktop/info"));setKey((await api<{configured:boolean}>("/ai3d/engines/meshy/status")).configured);};
  useEffect(()=>{refresh().catch(e=>onError(String(e)));api<Acceptance[]>("/acceptance").then(rows=>setReport(rows[0]??null)).catch(()=>{});},[]);
  async function action(work:()=>Promise<void>) {setBusy(true);try{await work();}catch(e){onError(String(e));}finally{setBusy(false);}}
  return <section><div className="section-title">FORMA · 0.4</div><h2>设置与验收</h2>
    <p>本地 Native / Blender / Ollama 不上传描述或图片。Meshy 是需要本人 Key 的云端收费服务；Hunyuan 另需本地 CUDA 环境和权重。</p>
    <p>Meshy Key：{key?"已加密配置，云端权限待验证":"未配置"}</p>
    {bridge()?<><button onClick={()=>bridge()!.postMessage("configureMeshy")}>安全配置 Meshy Key</button><button onClick={()=>bridge()!.postMessage("deleteMeshyKey")}>删除本地 Meshy Key…</button><button onClick={()=>bridge()!.postMessage("configureBlender")}>选择 Blender 可执行文件</button><button onClick={()=>bridge()!.postMessage("startWorker")}>可选启动本地 AI Worker</button></>:<code>.\scripts\configure-meshy.ps1</code>}
    <button onClick={()=>action(refresh)}>刷新配置状态</button>
    <details><summary>版本、数据与日志目录、更新策略</summary><pre className="diagnostics">{JSON.stringify(info,null,2)}</pre></details>
    <button onClick={()=>action(async()=>{setLog((await api<{log:string}>("/desktop/logs")).log);})}>查看本地错误日志</button>
    {log&&<pre className="diagnostics">{log}</pre>}
    <h3>真实 Meshy API 验收</h3><p className="warning">只创建一次 meshy-6-lite preview 几何任务，预计 5 credits，无纹理；实际费用以 Meshy 为准。默认不调用收费 API，不会自动 refine。没有 Key 或授权时仅生成 Skipped 报告。</p>
    <a href="https://docs.meshy.ai/en/api/pricing" target="_blank" rel="noreferrer">官方费用与模型说明</a>
    <button disabled={!key||busy} onClick={()=>action(async()=>{setAccount(await api("/acceptance/meshy/account","POST"));})}>检查账户权限与余额（免费 API）</button>
    {account&&<pre className="diagnostics">{JSON.stringify(account,null,2)}</pre>}
    <label><input aria-label="授权真实付费测试" type="checkbox" checked={paid} onChange={e=>setPaid(e.target.checked)} />明确授权这一次真实付费测试，接受服务方实际费用</label>
    <button disabled={busy} onClick={()=>action(async()=>{setReport(await api<Acceptance>("/acceptance/meshy","POST",{id:crypto.randomUUID(),authorize_paid_test:paid}));setPaid(false);})}>{paid&&key?"创建一次真实付费验收任务":"仅生成未执行报告"}</button>
    <button disabled={busy} onClick={()=>{const note=prompt("验收当前模型的 GLB 兼容性。请填写 Provider、授权来源并确认有权使用此素材（此操作只在本地进行，不证明真实推理）：");if(note&&note.length>=3)action(async()=>{const source=await currentSnapshot();setReport(await api<Acceptance>("/acceptance/compatibility","POST",{model_id:source.id,provider:"用户提供的外部素材",license_note:note,rights_confirmed:true}));});}}>验收当前合法素材兼容性（本地）</button>
    {report&&<div className="ai-result"><strong>{report.status} · {report.stage}</strong><p>{report.reason}</p><p>远程 ID：{report.remote_id??"未创建"}</p>
      {report.remote_id&&<button disabled={busy} onClick={()=>action(async()=>{setReport(await api(`/acceptance/${report.id}/refresh`,"POST"));})}>查询状态 / 下载并验证真实 GLB</button>}
      {report.asset_id&&<button disabled={busy} onClick={()=>action(async()=>{await onInsert(report.asset_id!);setReport(await api(`/acceptance/${report.id}/evidence`,"POST",{viewer_loaded:true}));})}>在 Viewer 验证真实资产</button>}
      <pre className="diagnostics">{JSON.stringify(report.checks,null,2)}</pre><a href={`/api/acceptance/${report.id}/download`} download>打开 JSON 验证报告</a></div>}
    <h3>隐私与本地数据</h3><a href="/api/privacy/export" download>导出本地项目与资产（不含 Key）</a>
    <button onClick={()=>action(async()=>{const result=await api("/storage/cleanup","POST",{older_than_days:30});setLog(JSON.stringify(result));})}>清理 30 天未引用缓存</button>
    <button onClick={()=>{const confirmation=prompt("删除所有本地项目、资产和历史。请输入 DELETE ALL LOCAL DATA；云端资产和本地密钥不在此操作中删除。");if(confirmation==="DELETE ALL LOCAL DATA")action(async()=>{await api("/privacy/delete","POST",{confirmation});location.reload();});}}>删除全部本地数据…</button>
    <details><summary>第三方许可</summary><p>应用代码 MIT；Hunyuan 权重为腾讯社区许可并有地域/用途限制。Meshy 输出受本人账户方案及服务条款约束。WebView2、.NET、Python 与各依赖按其许可证使用。安装包不包含 Blender、Ollama 模型或 Hunyuan 权重。</p></details>
  </section>;
}
export function FirstRun() {
  const [open,setOpen]=useState(()=>!localStorage.getItem("forma-onboarding-v4"));
  if(!open || !bridge())return null;
  return <div className="onboarding" role="dialog" aria-label="初次启动向导"><h2>欢迎使用 FORMA</h2><p>先用 Native 本地建模，无需 GPU 或云端账户。Blender 与 Ollama 使用你已安装的程序；Hunyuan 需要额外 CUDA 环境。</p><p>云端 Meshy 需要本人密钥和费用确认；未点击生成不会上传描述或图片。密钥可在设置中通过 Windows 安全对话框配置。</p><button onClick={()=>{localStorage.setItem("forma-onboarding-v4","done");setOpen(false);}}>开始本地创作</button></div>;
}
