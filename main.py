from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import uuid
from groq import Groq
import re

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def get_ydl_opts(format_type='mp4', cookies=None):
    opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios', 'mweb'],
                'player_skip': ['webpage'],
            }
        },
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'socket_timeout': 90,
        'retries': 5,
        'quiet': True,
        'no_warnings': True,
    }
    
    if cookies and len(cookies) > 100:
        cookie_file = f'/tmp/cookies_{uuid.uuid4()}.txt'
        with open(cookie_file, 'w') as f:
            f.write(cookies)
        opts['cookiefile'] = cookie_file
    
    if format_type == 'mp3':
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    
    return opts

def download_video(url, format_type, cookies=None):
    opts = get_ydl_opts(format_type, cookies)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if format_type == 'mp3':
            filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename, info.get('title', 'video')

def format_transcription(text):
    text = re.sub(r'\[\d{2}:\d{2}(:\d{2})?\]', '', text)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = []
    for i in range(0, len(sentences), 4):
        paragraphs.append(' '.join(sentences[i:i+4]).strip())
    return '\n\n'.join(paragraphs)

@app.get("/download")
async def download(url: str, format: str = "mp4", cookies: str = None):
    try:
        filepath, title = download_video(url, format, cookies)
        return FileResponse(filepath, filename=f"{title}.{format}", media_type='application/octet-stream')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcribe")
async def transcribe(url: str, cookies: str = None):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    try:
        filepath, title = download_video(url, 'mp3', cookies)
        with open(filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filepath, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        os.remove(filepath)
        return {"text": transcription, "formatted": format_transcription(transcription), "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-transcription")
async def download_transcription(url: str, cookies: str = None):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    try:
        filepath, title = download_video(url, 'mp3', cookies)
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
        return FileResponse(txt_path, filename=f"{title.replace(' ', '_')}_transcricao.txt", media_type='text/plain')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
