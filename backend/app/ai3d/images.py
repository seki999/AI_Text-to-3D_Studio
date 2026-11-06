"""Decode actual bytes, not extensions; strip EXIF and re-encode canonical PNG."""
import base64,io,warnings
from PIL import Image,ImageOps,UnidentifiedImageError

MAX_BYTES=10*1024*1024
MAX_PIXELS=16_000_000
Image.MAX_IMAGE_PIXELS=32*1024*1024  # Header guard; inputs have the stricter manual limit below.

def decode_image(data:str|bytes)->tuple[bytes,dict]:
    try:
        content=base64.b64decode(data,validate=True) if isinstance(data,str) else data
        if not content or len(content)>MAX_BYTES:raise ValueError('图片大小必须在 10 MB 以内')
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            image=Image.open(io.BytesIO(content))
            if image.format not in ('PNG','JPEG','WEBP'):raise ValueError('仅支持实际内容为 PNG / JPEG / WebP 的图片')
            if getattr(image,'n_frames',1)!=1:raise ValueError('不支持动画图片，请上传单帧参考图')
            w,h=image.size
            if w<16 or h<16 or w*h>MAX_PIXELS:raise ValueError('图片每边至少 16 像素，总像素不超过 1600 万')
            image.load();image=ImageOps.exif_transpose(image);w,h=image.size;mode='RGBA' if 'A' in image.getbands() else 'RGB'
            output=io.BytesIO();image.convert(mode).save(output,format='PNG')
            if output.tell()>MAX_BYTES:raise ValueError('规范化后的图片超出 10 MB')
            return output.getvalue(),{'width':w,'height':h,'format':'PNG','bytes':output.tell(),'alpha':mode=='RGBA'}
    except (UnidentifiedImageError,OSError,SyntaxError,Image.DecompressionBombWarning,Image.DecompressionBombError) as exc:
        raise ValueError('图片无法安全解码，文件损坏或像素过多') from exc
