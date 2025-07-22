# 🧠 Universal Content Summarizer API

The **Universal Content Summarizer API** allows you to extract and summarize content from various sources — including YouTube videos, playlists, articles, podcasts (via RSS), audio files, and uploaded documents. It uses **OpenAI Whisper** for transcription and **Mistral** for natural language summarization.

This API is ideal for developers, researchers, and content platforms looking to quickly digest long-form content into concise summaries.

---

## ✨ Features

- 🔊 **YouTube Video & Playlist Summarization**  
  Automatically transcribes and summarizes videos or entire playlists using Whisper + Mistral.

- 📰 **Article Summarization**  
  Extracts readable text from Medium articles, blogs, news sites, etc., and summarizes it.

- 🎙️ **Podcast Summarization**  
  Parses RSS feeds, downloads the latest episode, transcribes, and summarizes the audio.

- 📁 **Document Summarization**  
  Supports `.txt`, `.pdf`, and `.docx` files via upload.

- 🎧 **Audio File Summarization**  
  Upload your own `.mp3` files to get instant summaries.

- 📏 Adjustable summary `depth`: `"short"`, `"medium"`, or `"detailed"`.

---

## 🛠 Endpoints

### `POST /summarize-url`
Summarizes a single YouTube video or article.  
**Request body:**
```json
{
  "url": "https://example.com",
  "depth": "medium"
}
```

### `POST /summarize-playlist`
Summarizes each video in a YouTube playlist.
**Request body:**
```json
{
  "url": "https://www.youtube.com/playlist?list=...",
  "depth": "short"
}
```
### `POST /summarize-podcast` coming soon
Summarizes the latest episode of a podcast from an RSS feed.
**Request body:**
```json
{
  "rss_url": "https://feeds.example.com/podcast",
  "depth": "detailed"
}
```

### `POST /summarize-audio`
Upload an *.mp3* file and get a summary of the audio.
**Form-data:**
   *file*: (binary .mp3 file)

   *depth*: short | medium | detailed

### `POST /summarize-file`
Upload a document (*.pdf*, *.docx*, or *.txt*) and get a summary.
**Form-data:**
   *file*: (binary)

   *depth*: short | medium | detailed

## 🧪 Coming Soon
- **TikTok Shorts summarization**

- **Podcast feed history support**

- **Tweet threads summarization**
