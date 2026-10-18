# Omarchy Transcribe Studio (`omarchy-transcribe`)

A native **GTK4 + Libadwaita** desktop application and CLI for local, hardware-accelerated speech-to-text transcription of **Video & Audio** files powered by `whisper.cpp` (`whisper-cli`) and `FFmpeg`.

Designed to work out-of-the-box on **every type of machine** — automatically detecting and accelerating on **NVIDIA GPUs (CUDA / Vulkan)**, **AMD Radeon GPUs (ROCm / Vulkan)**, **Intel Arc & Integrated GPUs (Vulkan / OpenVINO)**, **Apple Silicon (Metal)**, and **Multi-Core CPUs**.

---

## 🚀 Quick Install (1-Liner for Any Machine)

Anyone can install it directly from the repository link with a single command:

```bash
curl -fsSL https://raw.githubusercontent.com/cjoy72/omarchy-transcribe/main/install.sh | bash
```

Or clone and install manually:

```bash
git clone https://github.com/cjoy72/omarchy-transcribe.git ~/Documents/Projects/omarchy-transcribe-gui
cd ~/Documents/Projects/omarchy-transcribe-gui
./install.sh
```

The installer automatically detects your hardware (NVIDIA, AMD, Intel, or CPU) and configures the appropriate `ggml` acceleration backend (`ggml-cuda` / `ggml-vulkan`).

---

## 🖥️ Universal Hardware Support

At startup, **Omarchy Transcribe Studio** automatically probes your system's compute backends and adapts to your machine:

| Hardware Type | Backend Used | Arch / Omarchy Package |
| :--- | :--- | :--- |
| **NVIDIA GeForce / RTX** | **CUDA (`libggml-cuda`)** or **Vulkan (`libggml-vulkan`)** | `whisper-cpp` + `ggml-cuda` / `ggml-vulkan` |
| **AMD Radeon (RX / APU)** | **Vulkan (`libggml-vulkan`)** or **ROCm (`libggml-hip`)** | `whisper-cpp` + `ggml-vulkan` / `ggml-hip` |
| **Intel Arc / Iris Xe / UHD** | **Vulkan (`libggml-vulkan`)** or **OpenVINO / SYCL** | `whisper-cpp` + `ggml-vulkan` |
| **CPU-Only / Laptop / VM** | **AVX2 / ZEN4 / SSE4.2 Multi-Thread CPU** | `whisper-cpp` (`ggml`) |

---

## ✨ Features

- 🎬 **Video & Audio Support**: Browse your PC or drag & drop any video (`MP4`, `MKV`, `WEBM`, `MOV`, `AVI`, `FLV`, `M4V`, `TS`) or audio (`MP3`, `WAV`, `FLAC`, `M4A`, `OGG`, `OPUS`, `AAC`, `WMA`) file. Automatically inspects streams via `ffprobe` and extracts 16 kHz mono PCM via `ffmpeg`.
- 🎙️ **Live Microphone Recording**: Record voice notes directly from your microphone (`PipeWire` / `ALSA` / `PulseAudio`) and immediately transcribe them.
- 🧠 **Built-in Whisper Model Manager & Downloader**:
  - Uses the shared global models directory (`~/.local/share/whisper-cpp/models` or `$WHISPER_MODELS_DIR`).
  - Displays installed status (`✓`) and file sizes for `Large v3 Turbo (Q5_0)`, `Large v3 Turbo`, `Large v3`, `Medium`, `Small`, `Base`, `Tiny`, and English-only models.
  - **1-Click HuggingFace Downloader**: Download any missing model with live progress (`MB` & `%`) directly inside the app—or click **Download Model & Transcribe** to automatically fetch a missing model and immediately start transcribing.
- 🌐 **30+ Languages & Auto-Detect**: Choose **Auto-Detect** or lock in any spoken language (English, Italian, Spanish, French, German, Portuguese, Chinese, Japanese, Arabic, Hindi, etc.), plus one-click **Translate to English** (`-tr`).
- ⚡ **Silero VAD Hallucination Prevention**: Automatically uses `ggml-silero-v6.2.0.bin` (and auto-downloads it if missing) to skip silence and eliminate Whisper hallucinations.
- 📝 **Live Streaming Transcript Studio & Multi-Format Export**:
  - Watch timestamped segments stream in real time as Whisper decodes your file.
  - Filter segments with live search, toggle timestamps on/off dynamically, copy to clipboard (Wayland & X11 compatible), or export to:
    - **Plain Text (`.txt`)**
    - **SubRip Subtitles (`.srt`)**
    - **WebVTT Subtitles (`.vtt`)**
    - **Synced Lyrics (`.lrc`)**
    - **Structured JSON (`.json`)**

---

## 🛠️ Usage

### GUI Mode

Launch from your application launcher (**Transcribe Studio**), Omarchy Menu (**Transcribe**), or terminal:

```bash
transcribe
# or open with a video/audio file pre-loaded:
transcribe ~/Videos/lecture.mp4
```

### Headless CLI Mode

Run directly in the terminal without opening a GUI window:

```bash
transcribe --cli ~/Videos/interview.mp4 -m large-v3-turbo-q5_0 -l auto
```

Options:
- `--cli`: Run in terminal CLI mode
- `-m, --model <id>`: Model ID (`large-v3-turbo-q5_0`, `large-v3-turbo`, `large-v3`, `medium`, `small`, `base`, `tiny`)
- `-l, --language <code>`: Language code (`auto`, `en`, `it`, `es`, `fr`, `de`, etc.)
- `-tr, --translate`: Translate speech to English

---

## 📄 License

MIT License © [cjoy72](https://github.com/cjoy72)
