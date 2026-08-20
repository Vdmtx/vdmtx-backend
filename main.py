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

# A chave será injetada pelas variáveis de ambiente do Render
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcribe")
def transcribe(url: str):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada no servidor.")
    try:
        # Baixa apenas o áudio para economizar RAM
        ydl_opts = {'format': 'bestaudio', 'outtmpl': f'{uuid.uuid4()}.%(ext)s'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        # Envia para a API da Groq transcrever (Grátis e rápido)
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
