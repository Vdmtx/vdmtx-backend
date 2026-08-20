from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import whisper
import os
import uuid

app = FastAPI()

# Permite CORS para o GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carrega o modelo Whisper (use 'base' para economizar RAM, 'small' para melhor precisão)
model = whisper.load_model("base")

def process_download(url, format_type):
    ydl_opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
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
def download(url: str, format: str = "mp4"):
    try:
        filepath, title = process_download(url, format)
        return FileResponse(filepath, filename=f"{title}.{format}", media_type='application/octet-stream')
    except Exception as e:
        return {"error": str(e)}

@app.get("/transcribe")
def transcribe(url: str):
    try:
        ydl_opts = {'format': 'bestaudio', 'outtmpl': f'{uuid.uuid4()}.%(ext)s'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
        
        result = model.transcribe(filepath)
        os.remove(filepath)
        return {"text": result["text"]}
    except Exception as e:
        return {"error": str(e)}
