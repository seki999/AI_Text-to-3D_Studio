"""Windows current-user DPAPI secret storage. Never expose keys through HTTP."""
import ctypes
import getpass
import os
import sys
from pathlib import Path
from ctypes import wintypes


def secret_path():
    if os.name != 'nt':
        raise ValueError('安全凭证配置目前仅支持 Windows DPAPI；其他系统尚未配置凭证存储')
    return Path(os.environ['LOCALAPPDATA'])/'AITextTo3DStudio'/'secrets'/'meshy.dpapi'


def crypt(data: bytes, decrypt=False):
    if os.name != 'nt':
        raise ValueError('需要 Windows 当前用户 DPAPI')
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    output=Blob()
    library=ctypes.windll.crypt32
    # CRYPTPROTECT_UI_FORBIDDEN; no machine-wide scope, bound to current Windows user.
    if decrypt:
        success=library.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output))
    else:
        success=library.CryptProtectData(ctypes.byref(source),'AI Text-to-3D Meshy',None,None,None,1,ctypes.byref(output))
    if not success:raise ValueError('Windows DPAPI 无法访问本地凭证')
    try:return ctypes.string_at(output.data,output.size)
    finally:ctypes.windll.kernel32.LocalFree(output.data)


def save_key(key: str):
    key=key.strip()
    if not 16<=len(key)<=512 or any(c.isspace() or ord(c)<33 or ord(c)>126 for c in key):
        raise ValueError('API Key 格式无效；请从 Meshy 账户复制完整密钥')
    path=secret_path();path.parent.mkdir(parents=True,exist_ok=True)
    encrypted=crypt(key.encode('utf-8'))
    temporary=path.with_suffix('.tmp');temporary.write_bytes(encrypted);temporary.replace(path)


def get_key():
    try:
        path=secret_path()
        if not path.is_file():raise ValueError('尚未配置 Meshy API Key')
        return crypt(path.read_bytes(),decrypt=True).decode('utf-8')
    except (OSError,UnicodeError) as exc:raise ValueError('无法读取本地 Meshy 凭证，请重新配置') from exc


if __name__=='__main__':
    try:
        action=sys.argv[1] if len(sys.argv)>1 else 'status'
        if action=='set':save_key(getpass.getpass('Meshy API Key (hidden): '));print('已加密保存；密钥不会发送到前端。')
        elif action=='delete':secret_path().unlink(missing_ok=True);print('本地凭证已删除。')
        elif action=='status':get_key();print('已配置（未向云端发送请求，密钥有效性未验证）。')
        else:raise ValueError('仅支持 set / delete / status')
    except ValueError as exc:print(str(exc));sys.exit(1)
