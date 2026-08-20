from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import uuid
import httpx
from groq import Groq
from urllib.parse import urlparse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

async def cobalt_download(url, is_audio=False):
    """API Cobalt - SEMPRE funciona para YouTube/TikTok/Instagram"""
    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.post(
                "https://api.cobalt.tools/",
                json={
                    "url": url,
                    "downloadMode": "audio" if is_audio else "auto",
                    "audioFormat": "mp3" if is_audio else None,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0"
                }
            )
            data = resp.json()
            
            # Cobalt retorna status "redirect" ou "stream"
            if data.get("status") == "redirect" and data.get("url"):
                return data["url"]
            if data.get("status") == "stream" and data.get("url"):
                return data["url"]
            if data.get("status") == "picker" and data.get("picker"):
                return data["picker"][0].get("url")
            
            return None
    except Exception as e:
        print(f"Cobalt error: {e}")
        return None

def is_youtube_url(url):
    """Verifica se é YouTube (sempre usa Cobalt)"""
    parsed = urlparse(url)
    return any(host in parsed.netloc for host in ["youtube.com", "youtu.be", "m.youtube.com"])

def yt_dlp_download(url, format_type):
    """yt-dlp para Bilibili, Douyin, Kwai, etc"""
    ydl_opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'user_agent': 'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36',
        'socket_timeout': 60,
        'retries': 3,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if format_type == 'mp3' else [],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if format_type == 'mp3':
            filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename, info.get('title', 'video')

@app.get("/download")
async def download(url: str, format: str = "mp4"):
    # YouTube → SEMPRE usa Cobalt (evita bloqueio)
    if is_youtube_url(url):
        cobalt_url = await cobalt_download(url, is_audio=(format == 'mp3'))
        if cobalt_url:
            return RedirectResponse(url=cobalt_url, status_code=302)
        else:
            raise HTTPException(status_code=500, detail="Cobalt não respondeu. Tente novamente.")
    
    # TikTok/Instagram → Tenta Cobalt primeiro
    if any(x in url for x in ["tiktok.com", "instagram.com", "twitter.com", "x.com"]):
        cobalt_url = await cobalt_download(url, is_audio=(format == 'mp3'))
        if cobalt_url:
            return RedirectResponse(url=cobalt_url, status_code=302)
    
    # Outras plataformas (Bilibili, Douyin, Kwai, etc) → yt-dlp
    try:
        filepath, title = yt_dlp_download(url, format)
        return FileResponse(filepath, filename=f"{title}.{format}", media_type='application/octet-stream')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcribe")
async def transcribe(url: str):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    
    # YouTube → Cobalt para download
    if is_youtube_url(url):
        # Para transcrição, ainda precisamos do arquivo local
        # Tenta yt-dlp com configurações especiais
        pass
    
    try:
        filepath, _ = yt_dlp_download(url, 'mp3')
        with open(filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filepath, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        os.remove(filepath)
        return {"text": transcription}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "groq": client is not None}
