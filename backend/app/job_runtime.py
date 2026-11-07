"""One-process local queue controls. Only PIDs created by this service are terminated."""
import os,signal,subprocess,threading
LOCK=threading.RLock()
PROCESSES={}
CANCELLED=set()

class Cancelled(Exception):pass

def terminate_tree(process):
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

def run_worker(job_id,command,log,directory,timeout=120,on_started=None):
    with LOCK:
        if job_id in CANCELLED:raise Cancelled()
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=directory,env={**{k:v for k,v in os.environ.items() if not k.startswith('LLM_') and not k.endswith('_API_KEY') and k not in ('FORMA_SESSION_TOKEN','AI3D_WORKER_TOKEN','HF_TOKEN','HUGGING_FACE_HUB_TOKEN')},'PYTHONNOUSERSITE':'1'},start_new_session=os.name!='nt',creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW) if os.name=='nt' else 0)
        PROCESSES[job_id]=process
        if on_started:
            try:on_started(process)
            except Exception:
                terminate_tree(process);PROCESSES.pop(job_id,None);raise
    try:
        try:result=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:terminate_tree(process);raise
        if job_id in CANCELLED:raise Cancelled()
        return result
    finally:
        with LOCK:PROCESSES.pop(job_id,None)

def cancel(job_id):
    with LOCK:
        CANCELLED.add(job_id)
        process=PROCESSES.get(job_id)
        if process:terminate_tree(process)
