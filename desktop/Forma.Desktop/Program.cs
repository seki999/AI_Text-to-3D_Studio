using System.Diagnostics;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Forma;
static class Program {
    [STAThread] static void Main(string[] args) {
        ApplicationConfiguration.Initialize();
        using var mutex = new Mutex(true, "Local\\FORMAStudio-" + Environment.UserName, out bool first);
        if (!first) { MessageBox.Show("FORMA 已在运行。请使用现有窗口。", "FORMA"); return; }
        Application.Run(new StudioWindow(args));
    }
}
sealed class StudioWindow : Form {
    readonly WebView2 web = new() { Dock = DockStyle.Fill };
    readonly string home = Environment.GetEnvironmentVariable("FORMA_TEST_HOME") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FORMAStudio");
    readonly string token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    readonly HttpClient client = new() { Timeout = TimeSpan.FromSeconds(10) };
    readonly ProcessJob processJob = new();
    readonly List<Process> managed = [];
    readonly string[] args;
    readonly object logLock=new();
    string origin = "";
    string workerOrigin = "";
    bool exiting;
    bool workerStarted;
    readonly string workerToken = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    public StudioWindow(string[] arguments) {
        args = arguments; Text = "FORMA AI 3D Studio 0.4"; Width = 1500; Height = 950;
        Controls.Add(web);
        Shown += async (_,_) => { try { await Start(); } catch(Exception e) { Log(e.GetType().Name + ": startup failed"); MessageBox.Show("启动失败。请查看日志目录：\n"+Path.Combine(home,"logs")+"\n"+e.Message,"FORMA"); Close(); } };
        FormClosing += async (_,e) => {
            if(exiting)return; e.Cancel=true; exiting=true;
            try { if(origin!="")await Native("/api/desktop/shutdown",new{}); } catch { }
            if(workerOrigin!="") { try { using var workerClient=new HttpClient{Timeout=TimeSpan.FromSeconds(3)}; workerClient.DefaultRequestHeaders.Add("X-Worker-Token",workerToken); await workerClient.PostAsync(workerOrigin+"/shutdown",null); } catch { } }
            web.Dispose();
            foreach(var process in managed) { try { if(!process.WaitForExit(4000))process.Kill(true); } catch { } process.Dispose(); }
            processJob.Dispose(); client.Dispose(); Close();
        };
    }
    void Log(string message) { lock(logLock) {try {Directory.CreateDirectory(Path.Combine(home,"logs"));File.AppendAllText(Path.Combine(home,"logs","desktop.log"),DateTimeOffset.Now.ToString("O")+" "+message+Environment.NewLine);} catch(IOException) { } } }
    async Task<(Process process,int port)> Sidecar(bool worker=false) {
        var path=Path.Combine(AppContext.BaseDirectory,"backend","FormaBackend.exe");
        if(!File.Exists(path))throw new FileNotFoundException("安装包缺少本地引擎。",path);
        var start=new ProcessStartInfo(path) { UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=AppContext.BaseDirectory };
        if(worker)start.ArgumentList.Add("--worker");
        start.Environment["AI3D_WORKER_TOKEN"]=workerToken;
        start.Environment["AI3D_WORKER_DATA"]=Path.Combine(home,"worker");
        start.Environment["FORMA_SESSION_TOKEN"]=token;
        start.Environment["FORMA_PARENT_PID"]=Environment.ProcessId.ToString();
        start.Environment["STUDIO_DATA"]=Path.Combine(home,"data");
        start.Environment["FORMA_LOG_DIR"]=Path.Combine(home,"logs");
        start.Environment["AI3D_ENABLE_MOCK"]="0";
        start.Environment["PYTHONUTF8"]="1";
        var process=Process.Start(start)??throw new InvalidOperationException("无法启动本地引擎");
        managed.Add(process);processJob.Add(process);
        process.ErrorDataReceived+=(_,e)=>{ if(e.Data!=null)Log(e.Data); };process.BeginErrorReadLine();
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(60));
        while(true) {
            string? line=await process.StandardOutput.ReadLineAsync(timeout.Token);
            if(line==null)throw new InvalidOperationException("本地引擎提前退出");
            if(line.StartsWith("{\"ready\"")) { using var json=JsonDocument.Parse(line); return(process,json.RootElement.GetProperty("port").GetInt32()); }
        }
    }
    async Task Start() {
        Directory.CreateDirectory(home);
        var (_,port)=await Sidecar();origin="http://127.0.0.1:"+port;
        client.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",token);
        using var health=await client.GetAsync(origin+"/api/health");health.EnsureSuccessStatusCode();
        var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(home,"webview"));
        await web.EnsureCoreWebView2Async(environment);
        web.CoreWebView2.Settings.AreDevToolsEnabled=false;
        web.CoreWebView2.Settings.AreDefaultContextMenusEnabled=false;
        web.CoreWebView2.Settings.IsStatusBarEnabled=false;
        var cookie=web.CoreWebView2.CookieManager.CreateCookie("forma_session",token,"127.0.0.1","/");
        cookie.IsHttpOnly=true;cookie.SameSite=CoreWebView2CookieSameSiteKind.Strict;cookie.IsSecure=false;
        web.CoreWebView2.CookieManager.AddOrUpdateCookie(cookie);
        web.CoreWebView2.NavigationStarting+=(_,e)=> { if(!Local(e.Uri))e.Cancel=true; };
        web.CoreWebView2.NewWindowRequested+=(_,e)=>{e.Handled=true;if(Uri.TryCreate(e.Uri,UriKind.Absolute,out var destination)&&destination.Scheme=="https"&&new[]{"docs.meshy.ai","www.meshy.ai","github.com","learn.microsoft.com"}.Contains(destination.Host))Process.Start(new ProcessStartInfo(e.Uri){UseShellExecute=true});};
        web.CoreWebView2.PermissionRequested+=(_,e)=>e.State=CoreWebView2PermissionState.Deny;
        web.CoreWebView2.WebMessageReceived+=async (_,e)=> {
            if(!Local(e.Source))return;
            try {
                string command=e.TryGetWebMessageAsString();
                if(command=="configureMeshy")await ConfigureKey();
                else if(command=="deleteMeshyKey" && MessageBox.Show("删除本地加密密钥？云端账户及任务不会删除。","FORMA",MessageBoxButtons.YesNo)==DialogResult.Yes)await Native("/api/desktop/meshy-key/delete",new{});
                else if(command=="startWorker" && !workerStarted) { var (_,workerPort)=await Sidecar(true); await Native("/api/desktop/worker-connection",new{port=workerPort,token=workerToken});workerOrigin="http://127.0.0.1:"+workerPort;workerStarted=true;MessageBox.Show("本地 Worker 已启动。真实 Hunyuan 仍需独立 CUDA 环境与权重，安装包不包含大型模型。","FORMA"); }
                else if(command=="openLogs")Process.Start(new ProcessStartInfo("explorer.exe",Path.Combine(home,"logs")){UseShellExecute=true});
                else if(command=="configureBlender") {
                    using var dialog=new OpenFileDialog{Filter="Blender executable|blender.exe",CheckFileExists=true};
                    if(dialog.ShowDialog(this)==DialogResult.OK)await Native("/api/desktop/blender",new{path=dialog.FileName});
                }
            } catch { MessageBox.Show("操作失败，请查看本地日志或重新配置。","FORMA"); }
        };
        if(args.Contains("--smoke-worker")) { var (_,workerPort)=await Sidecar(true); workerOrigin="http://127.0.0.1:"+workerPort; await Native("/api/desktop/worker-connection",new{port=workerPort,token=workerToken}); workerStarted=true; }
        web.Source=new Uri(origin);
        if(args.Contains("--smoke-test")) {
            web.CoreWebView2.NavigationCompleted+=async (_,e)=> {
                if(!e.IsSuccess)return;
                await Task.Delay(1000);
                await web.CoreWebView2.ExecuteScriptAsync("(()=>{[...document.querySelectorAll('button')].find(b=>b.textContent==='开始本地创作')?.click();const input=document.querySelector('[aria-label=文字描述]');if(input){Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(input,'红色立方体边长2米');input.dispatchEvent(new Event('input',{bubbles:true}));}[...document.querySelectorAll('button')].find(b=>b.textContent?.includes('① 解析'))?.click();})()");
                for(int i=0;i<30;i++){await Task.Delay(200);if(await web.CoreWebView2.ExecuteScriptAsync("document.querySelectorAll('.tree button').length>0")=="true")break;}
                await web.CoreWebView2.ExecuteScriptAsync("[...document.querySelectorAll('button')].find(b=>b.textContent?.includes('② 生成'))?.click()");
                for(int i=0;i<30;i++){await Task.Delay(200);if(await web.CoreWebView2.ExecuteScriptAsync("document.body.innerText.includes('模型已加载')")=="true")break;}
                using(var screenshot=File.Create(Path.Combine(home,"desktop-native.png")))await web.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,screenshot);
                var result=await web.CoreWebView2.ExecuteScriptAsync("JSON.stringify({title:document.title,canvas:!!document.querySelector('canvas'),body:document.body.innerText.includes('FORMA'),native_model_loaded:document.body.innerText.includes('模型已加载'),object_count:document.querySelectorAll('.tree button').length})");
                using var unauth=new HttpClient();
                var forbidden=await unauth.GetAsync(origin+"/api/projects");
                var browserPid=web.CoreWebView2.BrowserProcessId;
                File.WriteAllText(Path.Combine(home,"desktop-smoke.json"),JsonSerializer.Serialize(new{browser=result,unauthenticated_status=(int)forbidden.StatusCode,backend_pids=managed.Select(p=>p.Id).ToArray(),browser_pid=browserPid,origin}));
                Close();
            };
        }
    }
    bool Local(string address)=>Uri.TryCreate(address,UriKind.Absolute,out var uri)&&uri.GetLeftPart(UriPartial.Authority)==origin;
    async Task Native(string path,object body) { using var response=await client.PostAsync(origin+path,new StringContent(JsonSerializer.Serialize(body),Encoding.UTF8,"application/json"));response.EnsureSuccessStatusCode(); }
    async Task ConfigureKey() {
        using var dialog=new Form {Text="Meshy API Key · Windows DPAPI",Width=500,Height=190,StartPosition=FormStartPosition.CenterParent};
        var input=new TextBox{UseSystemPasswordChar=true,Dock=DockStyle.Top};
        var label=new Label{Text="密钥仅在本机加密保存。不会显示在网页、日志或 Git 中。",Dock=DockStyle.Top,Height=40};
        var save=new Button{Text="加密保存",Dock=DockStyle.Bottom,DialogResult=DialogResult.OK};
        dialog.Controls.Add(input);dialog.Controls.Add(label);dialog.Controls.Add(save);dialog.AcceptButton=save;
        if(dialog.ShowDialog(this)==DialogResult.OK) { await Native("/api/desktop/meshy-key",new{key=input.Text}); input.Clear(); MessageBox.Show("已保存。请刷新界面中的配置状态。","FORMA"); }
    }
}
