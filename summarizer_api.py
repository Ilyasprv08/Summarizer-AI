# summarizer_api.py
from fastapi import FastAPI, Form, Query, HTTPException, UploadFile, File, Request, Depends
from pydantic import BaseModel
import feedparser
import urllib.request
import requests
import subprocess
import os
import tempfile
import yt_dlp
from faster_whisper import WhisperModel
import whisper
from bs4 import BeautifulSoup
import re
import certifi
import ssl
import fitz 
import uuid
import json
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import docx
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file
API_KEY = os.environ.get("MISTRAL_API_KEY")
COOKIE_FILE = "youtube_cookies.txt"

app = FastAPI(title="Universal Content Summarizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SummarizeRequest(BaseModel):
    url: str
    depth: str = "medium"  # options: "short", "medium", "detailed"
    #session_id: str = None  # For YouTube login session tracking

class PodcastRequest(BaseModel):
    rss_url: str
    depth: str = "medium"  # options: "short", "medium", "detailed"

@app.get("/ping")
def ping():
    return {"status":"ok"}

@app.post("/upload-cookies", summary="Upload YouTube cookies", description="Uploads a file containing YouTube cookies for authenticated access.")
async def upload_cookies(file: UploadFile = File(...)):
   if not file.filename.endswith(".txt"):
         raise HTTPException(status_code=400, detail="Invalid file type. Please upload a .txt file.")
   with open(COOKIE_FILE, "wb") as f:
       content = await file.read()
       f.write(content)
   return {"status": "success", "message": "Cookies uploaded successfully"}

@app.post("/summarize-url", summary="Summarize a webpage or YouTube video", description="Takes a YouTube or article URL and returns a summary.")
def summarize_url(request: SummarizeRequest):
    url = request.url
    depth = request.depth
    #session_id = request.session_id

    if "youtube.com" in url or "youtu.be" in url:
        try:
            text = transcribe_youtube(url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"YouTube transcription failed: {str(e)}")
        source_type = "YouTube"

    elif re.match(r'^https?://', url):
        try:
            text = extract_article_text(url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Article extraction failed: {str(e)}")
        source_type = "Article"

    else:
        raise HTTPException(status_code=400, detail="Unsupported URL")

    summary = summarize_text(text, depth)

    return {
        "source": source_type,
        "url": url,
        "depth": depth,
        "summary": summary
    }

def parse_feed_with_headers(url):
    return feedparser.parse(url, request_headers={
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })

#@app.post("/summarize-podcast", summary="Summarize a podcast episode from RSS feed", description="Takes a podcast RSS feed URL and returns a summary of the latest episode.")
def summarize_podcast(request: PodcastRequest):
    rss_url = request.rss_url
    depth = request.depth

    try:
        feed = parse_feed_with_headers(rss_url)
        if not feed.entries:
            raise HTTPException(status_code=404, detail="No podcast episodes found in RSS feed")
        
        latest_entry = feed.entries[0]
        audio_url = None
        if "enclosures" in latest_entry and latest_entry.enclosures:
            audio_url = latest_entry.enclosures[0].href

        if not audio_url:
            for link in latest_entry.get("links", []):
               if link.get("type", "").startswith("audio"):
                  audio_url = link.get("href")
                  break

        if not audio_url:
            raise Exception("No audio URL found in RSS feed")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_audio:
            urllib.request.urlretrieve(audio_url, tmp_audio.name)
            audio_file_path = tmp_audio.name

        model = whisper.load_model("base")
        result = model.transcribe(audio_file_path)
        #model = WhisperModel("base", device="cpu")
        #segments, _ = model.transcribe(audio_file_path)
        #text = " ".join([segment.text for segment in segments])
        text = result['text']

        summary = summarize_text(text, depth)

        return {
            "source": "Podcast RSS",
            "episode_title": latest_entry.title,
            "episode_url": latest_entry.link,
            "depth": depth,
            "summary": summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Podcast processing failed: {str(e)}")
    
@app.post("/summarize-file", summary="Summarize an uploaded file", description="Uploads a file (.txt, .pdf, .docx) and returns a summary.")
async def summarize_file(depth: str = "medium", file: UploadFile = File(...)):
    filename = file.filename.lower()

    if filename.endswith(".txt"):
        content = (await file.read()).decode("utf-8")

    elif filename.endswith(".pdf"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        doc = fitz.open(tmp_path)
        content = " ".join(page.get_text() for page in doc)
        doc.close()

    elif filename.endswith(".docx"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        doc = docx.Document(tmp_path)
        content = " ".join([p.text for p in doc.paragraphs])

    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload .txt, .pdf, or .docx")

    summary = summarize_text(content, depth)

    return {
        "source": "Uploaded File",
        "filename": file.filename,
        "depth": depth,
        "summary": summary
    }

@app.post("/summarize-playlist", summary="Summarize a YouTube playlist", description="Takes a YouTube playlist URL and returns summaries of each video.")
def summarize_playlist(request: SummarizeRequest):
    url = request.url
    depth = request.depth

    if "youtube.com/playlist" not in url:
        raise HTTPException(status_code=400, detail="Invalid YouTube playlist URL")

    try:
        video_urls = extract_playlist_video_urls(url)
        if not video_urls:
            raise Exception("No videos found in playlist")
        
        summaries = []
        for video_url in video_urls:
            try:
                text = transcribe_youtube(video_url)
                summary = summarize_text(text, depth)
                summaries.append({
                    "video_url": video_url,
                    "summary": summary
                })
            except Exception as e:
                summaries.append({
                    "video_url": video_url,
                    "error": str(e)
                })

        return {
            "source": "YouTube Playlist",
            "playlist_url": url,
            "depth": depth,
            "video_count": len(video_urls),
            "summaries": summaries
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playlist summarization failed: {str(e)}")
    

@app.post("/summarize-audio", summary="Summarize an uploaded audio file", description="Uploads an audio file (.mp3, .wav) and returns a summary.")
async def summarize_audio(file: UploadFile = File(...), depth: str = "medium"):
   try:
       with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_audio:
           tmp_audio.write(await file.read())
           audio_file_path = tmp_audio.name

           model = whisper.load_model("base")
           result = model.transcribe(audio_file_path)
           text = result['text']

           summary = summarize_text(text, depth)
           return {
               "source": "Uploaded Audio",
               "filename": file.filename,
               "depth": depth,
               "summary": summary
           }
   except Exception as e:
       raise HTTPException(status_code=500, detail=f"Audio processing failed: {str(e)}")

def extract_playlist_video_urls(playlist_url):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
        'force_generic_extractor': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(playlist_url, download=False)
        if 'entries' in result:
            return [entry['url'] for entry in result['entries']]
        else:
            return []
        
def transcribe_youtube(video_url):
     def try_transcribe(ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
            for file in os.listdir(tmpdir):
                if file.endswith((".webm", ".m4a", ".mp3", ".opus")):
                    return os.path.join(tmpdir, file)
            raise Exception("No audio file downloaded")
        
     with tempfile.TemporaryDirectory() as tmpdir:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        import urllib.request
        https_handler = urllib.request.HTTPSHandler(context=ssl_context)
        opener = urllib.request.build_opener(https_handler)
        urllib.request.install_opener(opener)

        cookie_path = os.path.join(os.path.dirname(__file__), COOKIE_FILE) 
        use_cookies = os.path.exists(cookie_path)
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tmpdir, 'audio.%(ext)s'),
            'quiet': True,
            'nocheckcertificate': False
            }
        if use_cookies:
            ydl_opts['cookiefile'] = cookie_path

        try:
            downloaded_file = try_transcribe(ydl_opts)
        except Exception as public_error:
            raise Exception(f"Failed to download audio: {public_error}")
        
      #   try:
      #       downloaded_file = try_transcribe(ydl_opts)
      #   except Exception as public_error:
      #       try:
      #           cookie_path = os.path.join(os.path.dirname(__file__), 'youtube_cookies.txt')
      #           ydl_opts['cookiefile'] = cookie_path
      #           downloaded_file = try_transcribe(ydl_opts)
      #       except Exception as private_error:
      #           raise Exception(f"Failed to download audio: {public_error} | With cookies: {private_error}")

      #   with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      #       info = ydl.extract_info(video_url, download=True)
      #       downloaded_file = None
      #       for file in os.listdir(tmpdir):
      #          if file.endswith(".webm") or file.endswith(".m4a") or file.endswith(".mp3") or file.endswith(".opus"):
      #               downloaded_file = os.path.join(tmpdir, file)
      #               break
      #       if not downloaded_file:
      #             raise Exception("No audio file downloaded from YouTube")
            
        model = whisper.load_model("base")
        result = model.transcribe(downloaded_file)
        return result['text']

def extract_article_text(article_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ContentSummarizer/1.0)"
    }
    response = requests.get(article_url, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # Remove script and style
    for tag in soup(['script', 'style', "noscript", "iframe", "footer", "header", "nav", "form", "aside"]):
        tag.decompose()

    article_tag = soup.find('article')
    if article_tag:
        text = article_tag.get_text(separator=' ', strip=True)
    else:
        # Fallback: collect largest visible <div> or <p> text block
        candidates = sorted(
            soup.find_all(['div', 'p']),
            key=lambda tag: len(tag.get_text(strip=True)),
            reverse=True
        )
        text = ' '.join([c.get_text(separator=' ', strip=True) for c in candidates[:5]])

    # Cleanup excessive whitespace
    return re.sub(r'\s+', ' ', text).strip()

def summarize_text(text, depth):
    prompt = f"""
    You are a multilingual summarization expert.
Summarize the following content at a {depth} level. Only return the summary. No commentary.

Content:
{text}  # limit to first 3000 characters for safety
"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",  # your Mistral API key
        "Content-Type": "application/json"
    }

    data = {
        "model": "open-mixtral-8x7b",  # or your preferred model
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 800
    }

    response = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=data)

    if response.status_code == 200:
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    else:
        raise Exception(f"Mistral API error: {response.status_code} - {response.text}")
