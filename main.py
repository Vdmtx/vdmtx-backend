from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os
import uuid
from groq import Groq
import re
import tempfile

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp4"
    cookies: str = None

def download_with_cookies(url, format_type, cookies_text):
    """Baixa vídeo COM cookies do YouTube"""
    
    # Cria arquivo temporário para cookies
    cookie_file = None
    if cookies_text and len(cookies_text) > 100:
        cookie_file = f'/tmp/cookies_{uuid.uuid4()}.txt'
        with open(cookie_file, 'w', encoding='utf-8') as f:
            f.write(cookies_text)
    
    try:
        opts = {
            'outtmpl': f'{uuid.uuid4()}.%(ext)s',
            'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],
                    'player_skip': ['webpage'],
                }
            },
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'socket_timeout': 120,
            'retries': 5,
            'quiet': True,
            'no_warnings': True,
            'prefer_free_formats': False,
        }
        
        # ADICIONA COOKIES SE EXISTIR
        if cookie_file:
            opts['cookiefile'] = cookie_file
            print(f"Usando cookies de: {cookie_file}")
        
        if format_type == 'mp3':
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            
            return filename, info.get('title', 'video')
    
    finally:
        # Limpa arquivo de cookies
        if cookie_file and os.path.exists(cookie_file):
            try:
                os.remove(cookie_file)
            except:
                pass

def format_transcription(text):
    text = re.sub(r'\[\d{2}:\d{2}(:\d{2})?\]', '', text)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = []
    for i in range(0, len(sentences), 4):
        paragraphs.append(' '.join(sentences[i:i+4]).strip())
    return '\n\n'.join(paragraphs)

@app.post("/download")
async def download(request: DownloadRequest):
    try:
        filepath, title = download_with_cookies(request.url, request.format, request.cookies)
        return FileResponse(
            filepath, 
            filename=f"{title}.{request.format}", 
            media_type='application/octet-stream'
        )
    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm" in error_msg:
            raise HTTPException(status_code=400, detail="Cookies inválidos ou expirados. Exporte novos cookies do YouTube.")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/transcribe")
async def transcribe(request: DownloadRequest):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    
    try:
        filepath, title = download_with_cookies(request.url, 'mp3', request.cookies)
        
        with open(filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filepath, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        
        os.remove(filepath)
        
        return {
            "text": transcription,
            "formatted": format_transcription(transcription),
            "title": title
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/download-transcription")
async def download_transcription(request: DownloadRequest):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    
    try:
        filepath, title = download_with_cookies(request.url, 'mp3', request.cookies)
        
        with open(filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filepath, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        
        os.remove(filepath)
        formatted = format_transcription(transcription)
        
        txt_path = f"{uuid.uuid4()}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(formatted)
        
        return FileResponse(
            txt_path, 
            filename=f"{title.replace(' ', '_')}_transcricao.txt", 
            media_type='text/plain'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "groq": client is not None}
