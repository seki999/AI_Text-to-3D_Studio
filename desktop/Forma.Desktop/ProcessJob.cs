using System.Diagnostics;
using System.Runtime.InteropServices;
namespace Forma;
sealed class ProcessJob : IDisposable {
    [DllImport("kernel32.dll")] static extern IntPtr CreateJobObject(IntPtr attributes,string? name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job,int kind,IntPtr info,uint length);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [StructLayout(LayoutKind.Sequential)] struct Basic {public long ProcessTime,JobTime;public uint Flags;public UIntPtr Min,Max;public uint Active;public UIntPtr Affinity;public uint Priority,Scheduling;}
    [StructLayout(LayoutKind.Sequential)] struct Io {public ulong ReadOps,WriteOps,OtherOps,ReadBytes,WriteBytes,OtherBytes;}
    [StructLayout(LayoutKind.Sequential)] struct Limits {public Basic Basic;public Io Io;public UIntPtr ProcessMemory,JobMemory,PeakProcess,PeakJob;}
    IntPtr handle=CreateJobObject(IntPtr.Zero,null);
    public ProcessJob() {var value=new Limits();value.Basic.Flags=0x2000;var size=Marshal.SizeOf<Limits>();var buffer=Marshal.AllocHGlobal(size);try{Marshal.StructureToPtr(value,buffer,false);if(!SetInformationJobObject(handle,9,buffer,(uint)size))throw new InvalidOperationException("无法配置本地进程清理");}finally{Marshal.FreeHGlobal(buffer);}}
    public void Add(Process process) {if(!AssignProcessToJobObject(handle,process.Handle)){process.Kill(true);throw new InvalidOperationException("无法管理本地进程");}}
    public void Dispose(){if(handle!=IntPtr.Zero){CloseHandle(handle);handle=IntPtr.Zero;}}
}
