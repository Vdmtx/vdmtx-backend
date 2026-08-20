from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import uuid
from groq import Groq

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def get_ydl_opts(format_type='mp4'):
    """Configurações otimizadas para evitar bloqueios"""
    return {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios'],
                'player_skip': ['webpage'],
            }
        },
        'socket_timeout': 30,
        'retries': 3,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if format_type == 'mp3' else [],
    }

def process_download(url, format_type):
    ydl_opts = get_ydl_opts(format_type)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            return filename, info.get('title', 'video')
    except Exception as e:
        raise Exception(f"Erro no download: {str(e)}")

@app.get("/download")
def download(url: str, format: str = "mp4"):
    try:
        filepath, title = process_download(url, format)
        return FileResponse(filepath, filename=f"{title}.{format}", media_type='application/octet-stream')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcribe")
def transcribe(url: str):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada no servidor.")
    try:
        ydl_opts = get_ydl_opts('mp3')
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

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
