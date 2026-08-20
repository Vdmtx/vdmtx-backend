from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import uuid
import httpx
from groq import Groq
from urllib.parse import urlparse
import re

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ============ ESTRATÉGIAS DE DOWNLOAD ============

async def strategy_cobalt(url, is_audio=False):
    """Estratégia 1: API Cobalt"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                "https://api.cobalt.tools/",
                json={"url": url, "downloadMode": "audio" if is_audio else "auto"},
                headers={"Accept": "application/json", "Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    if data.get("url"):
                        return data["url"]
                    if data.get("picker"):
                        return data["picker"][0].get("url")
    except:
        pass
    return None

def strategy_ytdlp_android(url, format_type):
    """Estratégia 2: yt-dlp com client Android"""
    opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'extractor_args': {'youtube': {'player_client': ['android']}},
        'user_agent': 'com.google.android.youtube/15.37.36 (Linux; U; Android 11) gzip',
        'socket_timeout': 60, 'retries': 3, 'quiet': True, 'no_warnings': True,
    }
    if format_type == 'mp3':
        opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if format_type == 'mp3':
            filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename, info.get('title', 'video')

def strategy_ytdlp_ios(url, format_type):
    """Estratégia 3: yt-dlp com client iOS"""
    opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'extractor_args': {'youtube': {'player_client': ['ios']}},
        'user_agent': 'com.google.ios.youtube/17.31.4 (iPhone; CPU iPhone OS 14_7_1)',
        'socket_timeout': 60, 'retries': 3, 'quiet': True, 'no_warnings': True,
    }
    if format_type == 'mp3':
        opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if format_type == 'mp3':
            filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename, info.get('title', 'video')

def strategy_ytdlp_mweb(url, format_type):
    """Estratégia 4: yt-dlp com mobile web"""
    opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'extractor_args': {'youtube': {'player_client': ['mweb']}},
        'user_agent': 'Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36',
        'socket_timeout': 60, 'retries': 3, 'quiet': True, 'no_warnings': True,
    }
    if format_type == 'mp3':
        opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if format_type == 'mp3':
            filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename, info.get('title', 'video')

def strategy_ytdlp_default(url, format_type):
    """Estratégia 5: yt-dlp padrão (Bilibili, Douyin, Kwai, etc)"""
    opts = {
        'outtmpl': f'{uuid.uuid4()}.%(ext)s',
        'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio/best',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'socket_timeout': 60, 'retries': 3, 'quiet': True, 'no_warnings': True,
    }
    if format_type == 'mp3':
        opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if format_type == 'mp3':
            filename = filename.rsplit('.', 1)[0] + '.mp3'
        return filename, info.get('title', 'video')

# ============ FUNÇÕES PRINCIPAIS ============

async def download_with_fallback(url, format_type):
    """Tenta todas as estratégias em ordem"""
    parsed = urlparse(url)
    is_youtube = any(host in parsed.netloc for host in ["youtube.com", "youtu.be"])
    is_social = any(x in parsed.netloc for x in ["tiktok.com", "instagram.com", "twitter.com", "x.com"])
    
    # Estratégia 1: Cobalt (para YouTube e sociais)
    if is_youtube or is_social:
        cobalt_url = await strategy_cobalt(url, is_audio=(format_type == 'mp3'))
        if cobalt_url:
            return {"type": "redirect", "url": cobalt_url}
    
    # Estratégias 2-5: yt-dlp com diferentes clients
    strategies = [
        strategy_ytdlp_android,
        strategy_ytdlp_ios,
        strategy_ytdlp_mweb,
        strategy_ytdlp_default,
    ]
    
    last_error = None
    for strategy in strategies:
        try:
            filepath, title = strategy(url, format_type)
            return {"type": "file", "filepath": filepath, "title": title}
        except Exception as e:
            last_error = str(e)
            continue
    
    raise Exception(last_error or "Todas as estratégias falharam")

def format_transcription_paragraphs(text):
    """Organiza transcrição em parágrafos"""
    # Remove timestamps se houver
    text = re.sub(r'\[\d{2}:\d{2}(:\d{2})?\]', '', text)
    # Divide em frases por pontuação
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    # Agrupa em parágrafos de 3-4 frases
    paragraphs = []
    for i in range(0, len(sentences), 4):
        paragraph = ' '.join(sentences[i:i+4])
        paragraphs.append(paragraph.strip())
    return '\n\n'.join(paragraphs)

# ============ ENDPOINTS ============

@app.get("/download")
async def download(url: str, format: str = "mp4"):
    try:
        result = await download_with_fallback(url, format)
        if result["type"] == "redirect":
            return RedirectResponse(url=result["url"], status_code=302)
        return FileResponse(
            result["filepath"],
            filename=f"{result['title']}.{format}",
            media_type='application/octet-stream'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcribe")
async def transcribe(url: str):
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    
    try:
        # Baixa áudio com fallback
        result = await download_with_fallback(url, 'mp3')
        
        if result["type"] == "redirect":
            # Se Cobalt retornou URL, baixa o arquivo
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.get(result["url"])
                filepath = f"{uuid.uuid4()}.mp3"
                with open(filepath, "wb") as f:
                    f.write(resp.content)
        else:
            filepath = result["filepath"]
        
        # Transcreve com Groq Whisper
        with open(filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filepath, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        
        os.remove(filepath)
        
        # Organiza em parágrafos
        formatted = format_transcription_paragraphs(transcription)
        
        return {
            "text": transcription,
            "formatted": formatted,
            "title": result.get("title", "transcricao")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-transcription")
async def download_transcription(url: str):
    """Baixa a transcrição como arquivo .txt"""
    if not client:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada")
    
    try:
        result = await download_with_fallback(url, 'mp3')
        
        if result["type"] == "redirect":
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.get(result["url"])
                filepath = f"{uuid.uuid4()}.mp3"
                with open(filepath, "wb") as f:
                    f.write(resp.content)
        else:
            filepath = result["filepath"]
        
        with open(filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(filepath, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        
        os.remove(filepath)
        formatted = format_transcription_paragraphs(transcription)
        
        # Cria arquivo TXT
        txt_path = f"{uuid.uuid4()}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(formatted)
        
        title = result.get("title", "transcricao").replace(" ", "_")
        return FileResponse(
            txt_path,
            filename=f"{title}_transcricao.txt",
            media_type='text/plain'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok", "groq": client is not None}
