# ZeroCloud Notes

**Clip Xiaohongshu & Douyin to local notes — 100% offline, zero API cost.**

ZeroCloud Notes is the second plugin in the ZeroCloud family, built entirely with vibe coding — from a battle-tested Claude workflow to a polished Obsidian plugin. It brings your favorite social-media content into your vault as clean, structured notes, with everything running locally on your machine. No cloud APIs, no tokens, no cost.

## Features

- 📄 **Image-text notes (Xiaohongshu):** title, body, tags, and full-resolution images — saved as one tidy Markdown note
- 🎬 **Video notes:** local download + narration-only subtitles — background music is separated out automatically (skipped entirely when there's no voice)
- ✍️ **Natural sentence segmentation:** subtitles break where the speaker actually pauses, with single-point timestamps
- 🔒 **Zero-cloud guarantee:** yt-dlp, whisper, and local VAD models only — your data never leaves your Mac

## How it works

```
Paste a Xiaohongshu link → 
  ├─ Image-text note → title + body + tags + full-res images → Markdown note
  └─ Video note → local download → silero VAD voice detection
       ├─ Pure BGM (voice ratio < threshold) → note with video only, no transcription
       └─ With narration → whisper transcription → natural sentence segmentation → subtitle note
```

Everything runs locally: [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloads, [whisper.cpp](https://github.com/ggerganov/whisper.cpp) (large-v3-turbo) for transcription, [silero-vad](https://github.com/snakers4/silero-vad) for voice detection, ffmpeg for audio processing.

## Requirements

- macOS (Apple Silicon recommended)
- Obsidian 1.7.2+
- Python 3, `yt-dlp`, `ffmpeg`, `whisper-cli` (install via `brew install yt-dlp ffmpeg whisper-cpp`)
- `silero-vad` (optional but recommended): `pip3 install --user --break-system-packages silero-vad onnxruntime`

Run the environment self-check in plugin settings to verify everything is ready.

## Usage

- **Command palette → "小红书剪藏"**: paste a Xiaohongshu link (`xhslink.cn` short link or `xiaohongshu.com` note page)
- Notes are saved to `小红书剪藏/笔记/` (configurable), videos/images to `小红书剪藏/下载/`
- Task panel shows live progress; completion opens the note automatically

## License

MIT
