from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import uuid
from groq import Groq
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def get_ydl_opts(format_type='mp4', cookies=None):
    """Configurações avançadas para contornar bloqueios"""
    opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios', 'mweb'],
                'player_skip': ['webpage'],
            }
        },
        'socket_timeout': 60,
        'retries': 5,
        'fragment_retries': 3,
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
    }
    
    # Se tiver cookies, adiciona
    if cookies:
        opts['cookiefile'] = f'/tmp/cookies_{uuid.uuid4()}.txt'
        with open(opts['cookiefile'], 'w') as f:
            f.write(cookies)
    
    if format_type == 'mp3':
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    
    return opts

def extract_video_info(url):
    """Tenta extrair info do vídeo com múltiplas estratégias"""
    strategies = [
        # Estratégia 1: Android client
        {
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'user_agent': 'com.google.android.youtube/15.37.36 (Linux; U; Android 11) gzip'
        },
        # Estratégia 2: iOS client
        {
            'extractor_args': {'youtube': {'player_client': ['ios']}},
            'user_agent': 'com.google.ios.youtube/17.31.4 (iPhone; CPU iPhone OS 14_7_1)'
        },
        # Estratégia 3: Web embed
        {
            'extractor_args': {'youtube': {'player_client': ['web_embedded']}},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        # Estratégia 4: MWEB (mobile web)
        {
            'extractor_args': {'youtube': {'player_client': ['mweb']}},
            'user_agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36'
        },
    ]
    
    last_error = None
    
    for i, strategy in enumerate(strategies):
        try:
            opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'socket_timeout': 30,
            }
            opts.update(strategy)
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return info
        except Exception as e:
            last_error = e
            continue
    
    if last_error:
        raise last_error
    raise Exception("Todas as estratégias falharam")

@app.get("/download")
def download(url: str, format: str = "mp4", cookies: str = None):
    try:
        # Tenta extrair info primeiro
        info = extract_video_info(url)
        
        # Agora faz o download com as info já extraídas
        ydl_opts = get_ydl_opts(format, cookies)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Reutiliza a URL já validada
            ydl.download([url])
            filename = ydl.prepare_filename(info)
            if format == 'mp3':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            
        return FileResponse(filename, filename=f"{info.get('title', 'video')}.{format}", 
                          media_type='application/octet-stream')
    
    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            return JSONResponse(
                status_code=400,
                content={
                    "error": "YouTube bloqueou o acesso. Para contornar:",
                    "solution": "1. Instale a extensão 'Get cookies.txt' no Chrome/Firefox",
                    "solution2": "2. Acesse youtube.com e exporte os cookies",
                    "solution3": "3. Cole os cookies no campo abaixo (opcional)",
                    "hint": "Ou tente baixar vídeos mais curtos (< 10 min)"
                }
            )
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/transcribe")
def transcribe(url: str, cookies: str = None):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada.")
    
    try:
        # Extrai info primeiro
        info = extract_video_info(url)
        
        # Download do áudio
        ydl_opts = get_ydl_opts('mp3', cookies)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            filepath = ydl.prepare_filename(info)
        
        # Transcreve
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
    return {"status": "ok", "groq_configured": client is not None}
