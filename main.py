from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import httpx
from groq import Groq
import re

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

INVIDIOUS_INSTANCES = [
    "https://invidious.io.lol",
    "https://invidious.fdn.fr",
    "https://yt.artemislena.eu",
]

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp4"
    cookies: str = None

async def download_via_invidious(url: str, is_audio: bool = False):
    video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1].split("?")[0]
    
    for instance in INVIDIOUS_INSTANCES:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.get(f"{instance}/api/v1/videos/{video_id}", timeout=10)
                if resp.status_code != 200:
                    continue
                
                data = resp.json()
                title = data.get('title', 'video')
                
                if is_audio:
                    formats = [f for f in data.get('formatStreams', []) if 'audio' in str(f)]
                    if formats:
                        return formats[0]['url'], title
                else:
                    formats = [f for f in data.get('formatStreams', []) if 'video' in str(f)]
                    if formats:
                        return formats[0]['url'], title
        except:
            continue
    
    return None, None

def download_with_cookies(url, format_type, cookies_text):
    cookie_file = None
    if cookies_text and len(cookies_text) > 500:
        cookie_file = f'/tmp/cookies_{uuid.uuid4()}.txt'
        with open(cookie_file, 'w') as f:
            f.write(cookies_text)
    
    try:
        opts = {
            'outtmpl': f'{uuid.uuid4()}.%(ext)s',
            'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
            'extractor_args': {'youtube': {'player_client': ['web', 'android']}},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'socket_timeout': 120,
            'retries': 3,
            'quiet': True,
            'no_warnings': True,
        }
        
        if cookie_file:
            opts['cookiefile'] = cookie_file
        
        if format_type == 'mp3':
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return filename, info.get('title', 'video')
    finally:
        if cookie_file and os.path.exists(cookie_file):
            os.remove(cookie_file)

def format_text(text):
    text = re.sub(r'\[\d{2}:\d{2}(:\d{2})?\]', '', text)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = [' '.join(sentences[i:i+4]).strip() for i in range(0, len(sentences), 4)]
    return '\n\n'.join(paragraphs)

@app.post("/download")
async def download(request: DownloadRequest):
    # Tenta Invidious primeiro
    url, title = await download_via_invidious(request.url, request.format == 'mp3')
    if url and title:
        return RedirectResponse(url=url, status_code=302)
    
    # Fallback: cookies
    if request.cookies and len(request.cookies) > 500:
        try:
            filepath, title = download_with_cookies(request.url, request.format, request.cookies)
            return FileResponse(filepath, filename=f"{title}.{request.format}", media_type='application/octet-stream')
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    raise HTTPException(status_code=500, detail="YouTube bloqueou. Adicione cookies válidos.")

@app.post("/transcribe")
async def transcribe(request: DownloadRequest):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    
    url, title = await download_via_invidious(request.url, True)
    
    if not url:
        if request.cookies and len(request.cookies) > 500:
            filepath, title = download_with_cookies(request.url, 'mp3', request.cookies)
        else:
            raise HTTPException(status_code=500, detail="Não foi possível baixar")
    else:
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.get(url)
            filepath = f"{uuid.uuid4()}.mp3"
            with open(filepath, "wb") as f:
                f.write(resp.content)
    
    try:
        with open(filepath, "rb") as f:
            text = client.audio.transcriptions.create(file=(filepath, f.read()), model="whisper-large-v3", response_format="text")
        os.remove(filepath)
        return {"text": text, "formatted": format_text(text), "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/download-transcription")
async def download_transcription(request: DownloadRequest):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    
    url, title = await download_via_invidious(request.url, True)
    
    if not url:
        if request.cookies and len(request.cookies) > 500:
            filepath, title = download_with_cookies(request.url, 'mp3', request.cookies)
        else:
            raise HTTPException(status_code=500, detail="Erro")
    else:
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.get(url)
            filepath = f"{uuid.uuid4()}.mp3"
            with open(filepath, "wb") as f:
                f.write(resp.content)
    
    with open(filepath, "rb") as f:
        text = client.audio.transcriptions.create(file=(filepath, f.read()), model="whisper-large-v3", response_format="text")
    
    os.remove(filepath)
    formatted = format_text(text)
    
    txt_path = f"{uuid.uuid4()}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(formatted)
    
    return FileResponse(txt_path, filename=f"{title.replace(' ', '_')}.txt", media_type='text/plain')

@app.get("/health")
def health():
    return {"status": "ok"}
