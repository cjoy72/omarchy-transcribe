#!/usr/bin/env python3
"""
Omarchy Transcribe Studio — Modern Whisper AI Speech-to-Text Application
Supports Audio & Video files, Microphone Recording, Model Manager & Downloader,
Multi-Language Transcription, Translation to English, Silero VAD, GPU Acceleration,
and multiple export formats (TXT, SRT, VTT, JSON, LRC).
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

# Global Paths (Adhering to Global Whisper Models Directory Rule)
MODELS_DIR = Path(
    os.environ.get(
        "WHISPER_MODELS_DIR",
        os.path.expanduser("~/.local/share/whisper-cpp/models"),
    )
)
CONFIG_DIR = Path(os.path.expanduser("~/.config/omarchy-transcribe"))
CONFIG_FILE = CONFIG_DIR / "settings.json"
HISTORY_FILE = CONFIG_DIR / "history.json"
HF_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
VAD_HF_URL = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin"


@dataclass
class WhisperModelInfo:
    id: str
    name: str
    filename: str
    size_label: str
    speed_desc: str
    quality_desc: str
    recommended: bool = False
    url: str = ""

    def __post_init__(self):
        if not self.url:
            self.url = f"{HF_BASE_URL}/{self.filename}"

    @property
    def path(self) -> Path:
        return MODELS_DIR / self.filename

    @property
    def is_downloaded(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 1_000_000

    @property
    def disk_size_str(self) -> str:
        if not self.is_downloaded:
            return self.size_label
        size = self.path.stat().st_size
        if size >= 1024**3:
            return f"{size / (1024**3):.2f} GB"
        return f"{size / (1024**2):.0f} MB"


MODEL_CATALOG: List[WhisperModelInfo] = [
    WhisperModelInfo(
        id="large-v3-turbo-q5_0",
        name="Large v3 Turbo (Q5_0)",
        filename="ggml-large-v3-turbo-q5_0.bin",
        size_label="548 MB",
        speed_desc="Ultra Fast",
        quality_desc="Near-Max Accuracy (Quantized)",
        recommended=True,
    ),
    WhisperModelInfo(
        id="large-v3-turbo",
        name="Large v3 Turbo",
        filename="ggml-large-v3-turbo.bin",
        size_label="1.6 GB",
        speed_desc="Very Fast",
        quality_desc="High Accuracy (Full FP16)",
        recommended=True,
    ),
    WhisperModelInfo(
        id="large-v3",
        name="Large v3",
        filename="ggml-large-v3.bin",
        size_label="2.9 GB",
        speed_desc="Moderate",
        quality_desc="Maximum Studio Accuracy",
    ),
    WhisperModelInfo(
        id="medium",
        name="Medium",
        filename="ggml-medium.bin",
        size_label="1.5 GB",
        speed_desc="Fast",
        quality_desc="Balanced Multilingual",
    ),
    WhisperModelInfo(
        id="small",
        name="Small",
        filename="ggml-small.bin",
        size_label="466 MB",
        speed_desc="Very Fast",
        quality_desc="Good Everyday Accuracy",
    ),
    WhisperModelInfo(
        id="base",
        name="Base",
        filename="ggml-base.bin",
        size_label="142 MB",
        speed_desc="Instant",
        quality_desc="Lightweight / Quick Drafts",
    ),
    WhisperModelInfo(
        id="tiny",
        name="Tiny",
        filename="ggml-tiny.bin",
        size_label="75 MB",
        speed_desc="Extreme Speed",
        quality_desc="Basic Speech Detection",
    ),
    WhisperModelInfo(
        id="medium.en",
        name="Medium (English-Only)",
        filename="ggml-medium.en.bin",
        size_label="1.5 GB",
        speed_desc="Fast",
        quality_desc="Optimized for English",
    ),
    WhisperModelInfo(
        id="small.en",
        name="Small (English-Only)",
        filename="ggml-small.en.bin",
        size_label="466 MB",
        speed_desc="Very Fast",
        quality_desc="Optimized for English",
    ),
    WhisperModelInfo(
        id="base.en",
        name="Base (English-Only)",
        filename="ggml-base.en.bin",
        size_label="142 MB",
        speed_desc="Instant",
        quality_desc="Optimized for English",
    ),
]

LANGUAGES: List[Tuple[str, str]] = [
    ("auto", "🌐 Auto-Detect Language"),
    ("en", "🇬🇧 English (en)"),
    ("it", "🇮🇹 Italian / Italiano (it)"),
    ("es", "🇪🇸 Spanish / Español (es)"),
    ("fr", "🇫🇷 French / Français (fr)"),
    ("de", "🇩🇪 German / Deutsch (de)"),
    ("pt", "🇵🇹 Portuguese / Português (pt)"),
    ("nl", "🇳🇱 Dutch / Nederlands (nl)"),
    ("pl", "🇵🇱 Polish / Polski (pl)"),
    ("ru", "🇷🇺 Russian / Русский (ru)"),
    ("uk", "🇺🇦 Ukrainian / Українська (uk)"),
    ("zh", "🇨🇳 Chinese / 中文 (zh)"),
    ("ja", "🇯🇵 Japanese / 日本語 (ja)"),
    ("ko", "🇰🇷 Korean / 한국어 (ko)"),
    ("ar", "🇸🇦 Arabic / العربية (ar)"),
    ("hi", "🇮🇳 Hindi / हिन्दी (hi)"),
    ("tr", "🇹🇷 Turkish / Türkçe (tr)"),
    ("sv", "🇸🇪 Swedish / Svenska (sv)"),
    ("da", "🇩🇰 Danish / Dansk (da)"),
    ("fi", "🇫🇮 Finnish / Suomi (fi)"),
    ("no", "🇳🇴 Norwegian / Norsk (no)"),
    ("cs", "🇨🇿 Czech / Čeština (cs)"),
    ("ro", "🇷🇴 Romanian / Română (ro)"),
    ("el", "🇬🇷 Greek / Ελληνικά (el)"),
    ("hu", "🇭🇺 Hungarian / Magyar (hu)"),
    ("id", "🇮🇩 Indonesian / Bahasa (id)"),
    ("vi", "🇻🇳 Vietnamese / Tiếng Việt (vi)"),
    ("th", "🇹🇭 Thai / ไทย (th)"),
    ("he", "🇮🇱 Hebrew / עברית (he)"),
    ("ca", "🏴 Catalan / Català (ca)"),
]

MEDIA_EXTENSIONS = {
    # Audio
    ".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".amr",
    # Video
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv", ".m4v", ".ts", ".3gp", ".mpeg", ".mpg",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv", ".m4v", ".ts", ".3gp", ".mpeg", ".mpg",
}

CUSTOM_CSS = """
.drop-zone {
    background-color: alpha(@card_bg_color, 0.7);
    border: 2px dashed alpha(@accent_color, 0.45);
    border-radius: 16px;
    padding: 22px;
    transition: all 200ms ease;
}
.drop-zone:hover, .drop-zone.drag-hover {
    border-color: @accent_color;
    background-color: alpha(@accent_bg_color, 0.12);
}
.transcript-view {
    font-family: "JetBrainsMono Nerd Font", "Monospace", monospace;
    font-size: 11.5pt;
    line-height: 1.55;
    padding: 16px;
    background-color: @view_bg_color;
    color: @view_fg_color;
}
.badge-ready {
    background-color: alpha(@success_bg_color, 0.22);
    color: @success_color;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 9pt;
    font-weight: 700;
}
.badge-missing {
    background-color: alpha(@warning_bg_color, 0.22);
    color: @warning_color;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 9pt;
    font-weight: 700;
}
.badge-rec {
    background-color: alpha(@accent_bg_color, 0.25);
    color: @accent_color;
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 9pt;
    font-weight: 700;
}
.status-card {
    background-color: @card_bg_color;
    border-radius: 12px;
    padding: 14px 18px;
}
.recording-pulse {
    background-color: @error_bg_color;
    color: @error_fg_color;
    font-weight: bold;
}
"""


@dataclass
class Segment:
    start_ms: int
    end_ms: int
    start_str: str
    end_str: str
    text: str


def parse_timestamp_ms(ts: str) -> int:
    """Parse HH:MM:SS.mmm into milliseconds."""
    try:
        parts = ts.strip().replace(",", ".").split(":")
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split(".")
        s = int(s_parts[0])
        ms = int(s_parts[1].ljust(3, "0")[:3]) if len(s_parts) > 1 else 0
        return ((h * 3600) + (m * 60) + s) * 1000 + ms
    except Exception:
        return 0


def format_srt_ts(ms: int) -> str:
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{rem:03d}"


def format_vtt_ts(ms: int) -> str:
    return format_srt_ts(ms).replace(",", ".")


def format_lrc_ts(ms: int) -> str:
    m = ms // 60000
    rem = ms % 60000
    s = rem // 1000
    cs = (rem % 1000) // 10
    return f"{m:02d}:{s:02d}.{cs:02d}"


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0:00"
    total_sec = int(round(seconds))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def probe_media_info(filepath: Path) -> Dict[str, str]:
    """Use ffprobe to inspect duration, codec, channels, sample rate, and video resolution."""
    info = {
        "duration_sec": 0.0,
        "duration_str": "Unknown",
        "kind": "Video" if filepath.suffix.lower() in VIDEO_EXTENSIONS else "Audio",
        "details": filepath.suffix.upper().lstrip("."),
    }
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,codec_name,sample_rate,channels,width,height",
            "-of", "json",
            str(filepath),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            dur = float(data.get("format", {}).get("duration", 0.0))
            info["duration_sec"] = dur
            info["duration_str"] = format_duration(dur)

            streams = data.get("streams", [])
            has_video = any(s.get("codec_type") == "video" for s in streams)
            info["kind"] = "Video" if has_video else "Audio"

            parts = []
            for s in streams:
                if s.get("codec_type") == "video" and s.get("width"):
                    parts.append(f"{s.get('codec_name', 'video').upper()} {s['width']}x{s['height']}")
                elif s.get("codec_type") == "audio":
                    sr = s.get("sample_rate")
                    sr_str = f"{int(sr)//1000}kHz" if sr else ""
                    parts.append(f"{s.get('codec_name', 'audio').upper()} {sr_str}".strip())
            if parts:
                info["details"] = " • ".join(parts[:2])
    except Exception:
        pass
    return info


def detect_hardware_backend() -> Dict[str, object]:
    """
    Auto-detect available compute backends (NVIDIA CUDA, AMD ROCm/HIP, Vulkan, Intel SYCL/OpenVINO, Apple Metal, or CPU)
    by probing whisper-cli / ggml backends and system GPU utilities.
    Works across NVIDIA, AMD, Intel, Apple Silicon, and CPU-only machines.
    """
    hw = {
        "has_gpu": False,
        "backend": "CPU",
        "device_name": f"Multi-Core CPU ({os.cpu_count() or 4} threads)",
        "whisper_bin": shutil.which("whisper-cli") or shutil.which("whisper-cpp") or shutil.which("main") or "whisper-cli",
    }

    # 1. Inspect whisper-cli startup output for loaded ggml backends & GPU device names
    try:
        res = subprocess.run(
            [str(hw["whisper_bin"]), "--help"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        out = (res.stdout or "") + "\n" + (res.stderr or "")

        # Check CUDA / NVIDIA
        cuda_match = re.search(r"ggml_cuda.*?:\s*0\s*=\s*([^\n|]+)", out, re.IGNORECASE)
        if cuda_match or "libggml-cuda" in out.lower():
            hw["has_gpu"] = True
            hw["backend"] = "NVIDIA CUDA"
            hw["device_name"] = cuda_match.group(1).strip() if cuda_match else "NVIDIA GPU (CUDA)"
            return hw

        # Check ROCm / HIP
        hip_match = re.search(r"ggml_(?:hip|rocm).*?:\s*0\s*=\s*([^\n|]+)", out, re.IGNORECASE)
        if hip_match or "libggml-hip" in out.lower():
            hw["has_gpu"] = True
            hw["backend"] = "AMD ROCm"
            hw["device_name"] = hip_match.group(1).strip() if hip_match else "AMD GPU (ROCm/HIP)"
            return hw

        # Check Vulkan (works on NVIDIA, AMD, Intel)
        vk_match = re.search(r"ggml_vulkan:\s*0\s*=\s*([^\n|]+)", out, re.IGNORECASE)
        if vk_match or "libggml-vulkan" in out.lower():
            hw["has_gpu"] = True
            hw["backend"] = "Vulkan GPU"
            dev = vk_match.group(1).strip() if vk_match else "Vulkan-Compatible GPU"
            # Clean up trailing driver parentheticals if overly long
            hw["device_name"] = dev
            return hw

        # Check SYCL / OpenVINO (Intel Arc / iGPU)
        if "libggml-sycl" in out.lower() or "libggml-openvino" in out.lower():
            hw["has_gpu"] = True
            hw["backend"] = "Intel OneAPI / OpenVINO"
            hw["device_name"] = "Intel GPU / NPU"
            return hw

        # Check Metal (Apple Silicon)
        if "ggml_metal" in out.lower() or "libggml-metal" in out.lower():
            hw["has_gpu"] = True
            hw["backend"] = "Apple Metal"
            hw["device_name"] = "Apple Silicon GPU"
            return hw
    except Exception:
        pass

    # 2. Fallback check via nvidia-smi if whisper-cli didn't print backend on --help
    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                gpu_name = res.stdout.strip().splitlines()[0]
                if Path("/usr/lib/ggml/libggml-cuda.so").exists() or Path("/usr/lib/ggml/libggml-vulkan.so").exists():
                    hw["has_gpu"] = True
                    hw["backend"] = "NVIDIA CUDA" if Path("/usr/lib/ggml/libggml-cuda.so").exists() else "Vulkan GPU"
                    hw["device_name"] = gpu_name
        except Exception:
            pass

    return hw


class ModelManagerDialog(Adw.Window):
    """Dialog for inspecting, downloading, or deleting Whisper models in ~/.local/share/whisper-cpp/models/."""

    def __init__(self, parent_window: "TranscribeMainWindow"):
        super().__init__(
            transient_for=parent_window,
            modal=True,
            title="Whisper AI Model Manager",
            default_width=680,
            default_height=600,
        )
        self.parent_window = parent_window
        self.active_downloads: Dict[str, bool] = {}

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(16)
        content_box.set_margin_bottom(16)
        content_box.set_margin_start(18)
        content_box.set_margin_end(18)

        # Info banner about global models directory
        banner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        banner_box.add_css_class("status-card")
        title_lbl = Gtk.Label(
            label="Global Whisper Models Directory",
            xalign=0,
        )
        title_lbl.add_css_class("heading")
        path_lbl = Gtk.Label(
            label=f"📁 {MODELS_DIR}",
            xalign=0,
            selectable=True,
        )
        path_lbl.add_css_class("dim-label")
        sub_lbl = Gtk.Label(
            label="Models are shared across your system. Download any missing model directly from HuggingFace.",
            xalign=0,
            wrap=True,
        )
        sub_lbl.add_css_class("caption")
        banner_box.append(title_lbl)
        banner_box.append(path_lbl)
        banner_box.append(sub_lbl)
        content_box.append(banner_box)

        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        scrolled.set_child(self.list_box)
        content_box.append(scrolled)

        toolbar_view.set_content(content_box)
        self.set_content(toolbar_view)

        self.populate_models()

    def populate_models(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)

        for model in MODEL_CATALOG:
            row = Adw.ActionRow(
                title=model.name,
                subtitle=f"{model.disk_size_str}  •  ⚡ {model.speed_desc}  •  🎯 {model.quality_desc}",
            )

            suffix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            suffix_box.set_valign(Gtk.Align.CENTER)

            if model.recommended:
                rec_badge = Gtk.Label(label="★ Recommended")
                rec_badge.add_css_class("badge-rec")
                suffix_box.append(rec_badge)

            if model.is_downloaded:
                status_badge = Gtk.Label(label="✓ Installed")
                status_badge.add_css_class("badge-ready")
                suffix_box.append(status_badge)

                use_btn = Gtk.Button(label="Select")
                use_btn.add_css_class("suggested-action")
                use_btn.connect("clicked", self.on_select_model, model)
                suffix_box.append(use_btn)
            else:
                status_badge = Gtk.Label(label="⬇ Not Installed")
                status_badge.add_css_class("badge-missing")
                suffix_box.append(status_badge)

                dl_btn = Gtk.Button(label=f"Download ({model.size_label})")
                dl_btn.connect("clicked", self.on_download_clicked, model, row, suffix_box)
                suffix_box.append(dl_btn)

            row.add_suffix(suffix_box)
            self.list_box.append(row)

    def on_select_model(self, _btn, model: WhisperModelInfo):
        self.parent_window.select_model_by_id(model.id)
        self.close()

    def on_download_clicked(self, btn: Gtk.Button, model: WhisperModelInfo, row: Adw.ActionRow, suffix_box: Gtk.Box):
        btn.set_sensitive(False)
        btn.set_label("Starting...")
        self.parent_window.start_model_download(
            model,
            on_complete=lambda ok, msg: self.on_download_finished(ok, msg, model),
        )

    def on_download_finished(self, ok: bool, msg: str, model: WhisperModelInfo):
        self.populate_models()
        self.parent_window.refresh_model_dropdown()
        if ok:
            self.parent_window.select_model_by_id(model.id)


class TranscribeMainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, initial_file: Optional[str] = None):
        super().__init__(
            application=app,
            title="Omarchy Transcribe Studio",
            default_width=1020,
            default_height=740,
        )
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        self.hw_info = detect_hardware_backend()
        self.settings = self.load_settings()
        self.current_file: Optional[Path] = None
        self.segments: List[Segment] = []
        self.raw_text: str = ""
        self.is_transcribing: bool = False
        self.is_downloading: bool = False
        self.is_recording: bool = False
        self.active_process: Optional[subprocess.Popen] = None
        self.record_process: Optional[subprocess.Popen] = None
        self.record_start_time: float = 0.0
        self.record_temp_path: Optional[Path] = None
        self.cancel_requested: bool = False

        self.build_ui()

        if initial_file:
            p = Path(initial_file).expanduser().resolve()
            if p.exists():
                self.set_selected_file(p)

    def load_settings(self) -> dict:
        defaults = {
            "model_id": "large-v3-turbo-q5_0",
            "language": "auto",
            "translate_to_en": False,
            "use_vad": True,
            "use_gpu": bool(self.hw_info.get("has_gpu", True)),
            "show_timestamps": True,
            "threads": min(8, os.cpu_count() or 4),
        }
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text())
                defaults.update(data)
            except Exception:
                pass
        return defaults

    def save_settings(self):
        try:
            CONFIG_FILE.write_text(json.dumps(self.settings, indent=2))
        except Exception:
            pass

    def build_ui(self):
        self.toast_overlay = Adw.ToastOverlay()
        toolbar_view = Adw.ToolbarView()

        # Top HeaderBar
        header = Adw.HeaderBar()
        hw_label = f"{self.hw_info['backend']}: {self.hw_info['device_name']}"
        title_widget = Adw.WindowTitle(
            title="Omarchy Transcribe Studio",
            subtitle=f"Local Whisper.cpp Audio and Video Transcriber ({hw_label})",
        )
        header.set_title_widget(title_widget)

        # Header Left: Open File & Record Mic
        open_btn = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Choose Audio or Video File (Ctrl+O)")
        open_btn_content = Adw.ButtonContent(icon_name="folder-music-symbolic", label="Choose Media")
        open_btn.set_child(open_btn_content)
        open_btn.connect("clicked", self.on_choose_file_clicked)
        header.pack_start(open_btn)

        self.rec_btn = Gtk.Button(tooltip_text="Record Voice from Microphone")
        self.rec_btn_content = Adw.ButtonContent(icon_name="audio-input-microphone-symbolic", label="Record Mic")
        self.rec_btn.set_child(self.rec_btn_content)
        self.rec_btn.connect("clicked", self.on_record_mic_clicked)
        header.pack_start(self.rec_btn)

        # Header Right: Model Manager button
        models_btn = Gtk.Button(tooltip_text="Manage & Download Whisper Models")
        models_btn_content = Adw.ButtonContent(icon_name="folder-download-symbolic", label="Models")
        models_btn.set_child(models_btn_content)
        models_btn.connect("clicked", self.on_open_model_manager)
        header.pack_end(models_btn)

        toolbar_view.add_top_bar(header)

        # Main Horizontal Split Layout (Left Configuration Sidebar + Right Transcript Studio)
        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_paned.set_position(410)
        main_paned.set_shrink_start_child(False)
        main_paned.set_shrink_end_child(False)

        # ================= LEFT PANEL: CONTROLS =================
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left_scroll.set_size_request(380, -1)

        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        left_box.set_margin_top(16)
        left_box.set_margin_bottom(16)
        left_box.set_margin_start(16)
        left_box.set_margin_end(12)

        # 1. File Selection & Drag-and-Drop Card
        self.drop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.drop_box.add_css_class("drop-zone")

        self.media_icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        self.media_icon.set_pixel_size(42)
        self.drop_box.append(self.media_icon)

        self.file_title_lbl = Gtk.Label(
            label="Select or Drop Audio / Video File",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        self.file_title_lbl.add_css_class("title-4")
        self.drop_box.append(self.file_title_lbl)

        self.file_meta_lbl = Gtk.Label(
            label="Supports MP4, MKV, MOV, WEBM, MP3, WAV, FLAC, M4A, OGG, OPUS",
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        self.file_meta_lbl.add_css_class("caption")
        self.file_meta_lbl.add_css_class("dim-label")
        self.drop_box.append(self.file_meta_lbl)

        browse_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.CENTER)
        browse_row.set_margin_top(6)
        choose_btn = Gtk.Button(label="Browse PC (Video / Audio)...")
        choose_btn.add_css_class("pill")
        choose_btn.connect("clicked", self.on_choose_file_clicked)
        browse_row.append(choose_btn)
        self.drop_box.append(browse_row)

        # Drag and drop controller
        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect("enter", self.on_drag_enter)
        drop_target.connect("leave", self.on_drag_leave)
        drop_target.connect("drop", self.on_file_dropped)
        self.drop_box.add_controller(drop_target)

        left_box.append(self.drop_box)

        # 2. Whisper Model Group
        model_group = Adw.PreferencesGroup(
            title="1. Whisper AI Model",
            description="Choose a downloaded model or download a new one",
        )

        self.model_row = Adw.ComboRow(title="Model")
        self.model_string_list = Gtk.StringList()
        self.model_row.set_model(self.model_string_list)
        model_group.add(self.model_row)

        # Model status & quick download action row
        self.model_status_row = Adw.ActionRow(
            title="Model Status",
            subtitle="Ready on disk",
        )
        self.dl_quick_btn = Gtk.Button(label="Download Now", valign=Gtk.Align.CENTER)
        self.dl_quick_btn.add_css_class("suggested-action")
        self.dl_quick_btn.connect("clicked", self.on_quick_download_selected_model)
        self.model_status_row.add_suffix(self.dl_quick_btn)
        model_group.add(self.model_status_row)

        self.refresh_model_dropdown()
        self.model_row.connect("notify::selected", self.on_model_selection_changed)

        left_box.append(model_group)

        # 3. Language & Task Group
        lang_group = Adw.PreferencesGroup(
            title="2. Language and Translation",
            description="Select spoken language or auto-detect",
        )

        self.lang_row = Adw.ComboRow(title="Spoken Language")
        lang_strings = Gtk.StringList.new([label for _, label in LANGUAGES])
        self.lang_row.set_model(lang_strings)

        saved_lang = self.settings.get("language", "auto")
        lang_idx = next((i for i, (code, _) in enumerate(LANGUAGES) if code == saved_lang), 0)
        self.lang_row.set_selected(lang_idx)
        self.lang_row.connect("notify::selected", self.on_language_changed)
        lang_group.add(self.lang_row)

        self.translate_switch = Adw.SwitchRow(
            title="Translate to English",
            subtitle="Translate non-English speech directly into English",
            active=self.settings.get("translate_to_en", False),
        )
        self.translate_switch.connect("notify::active", self.on_settings_toggled)
        lang_group.add(self.translate_switch)

        left_box.append(lang_group)

        # 4. Engine & Output Options Group
        engine_group = Adw.PreferencesGroup(
            title="3. Processing Options",
        )

        self.vad_switch = Adw.SwitchRow(
            title="Silero Voice Activity Detection (VAD)",
            subtitle="Skip silence and prevent Whisper hallucinations",
            active=self.settings.get("use_vad", True),
        )
        self.vad_switch.connect("notify::active", self.on_settings_toggled)
        engine_group.add(self.vad_switch)

        if self.hw_info["has_gpu"]:
            gpu_title = f"GPU Acceleration ({self.hw_info['backend']})"
            gpu_sub = f"Detected: {self.hw_info['device_name']}"
        else:
            gpu_title = "GPU Acceleration (Fallback to Multi-Core CPU)"
            gpu_sub = f"No GPU backend detected — using {self.hw_info['device_name']}"

        self.gpu_switch = Adw.SwitchRow(
            title=gpu_title,
            subtitle=gpu_sub,
            active=self.settings.get("use_gpu", True) and bool(self.hw_info["has_gpu"]),
            sensitive=bool(self.hw_info["has_gpu"]),
        )
        self.gpu_switch.connect("notify::active", self.on_settings_toggled)
        engine_group.add(self.gpu_switch)

        self.ts_switch = Adw.SwitchRow(
            title="Include Timestamps in View",
            subtitle="Display [00:00.000 -> 00:05.000] markers",
            active=self.settings.get("show_timestamps", True),
        )
        self.ts_switch.connect("notify::active", self.on_timestamps_toggled)
        engine_group.add(self.ts_switch)

        left_box.append(engine_group)

        # 5. Primary Action Button & Progress Area
        action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        self.progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.progress_box.set_visible(False)

        self.progress_lbl = Gtk.Label(label="Preparing...", xalign=0)
        self.progress_lbl.add_css_class("caption")
        self.progress_box.append(self.progress_lbl)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_box.append(self.progress_bar)
        action_box.append(self.progress_box)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.transcribe_btn = Gtk.Button(hexpand=True)
        self.transcribe_btn.set_size_request(-1, 46)
        self.transcribe_btn.add_css_class("suggested-action")
        self.transcribe_btn.add_css_class("pill")
        self.transcribe_btn_content = Adw.ButtonContent(
            icon_name="media-playback-start-symbolic",
            label="Start Transcription",
        )
        self.transcribe_btn.set_child(self.transcribe_btn_content)
        self.transcribe_btn.connect("clicked", self.on_start_transcribe_clicked)
        btn_row.append(self.transcribe_btn)

        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.add_css_class("destructive-action")
        self.cancel_btn.add_css_class("pill")
        self.cancel_btn.set_visible(False)
        self.cancel_btn.connect("clicked", self.on_cancel_clicked)
        btn_row.append(self.cancel_btn)

        action_box.append(btn_row)
        left_box.append(action_box)

        left_scroll.set_child(left_box)
        main_paned.set_start_child(left_scroll)

        # ================= RIGHT PANEL: TRANSCRIPT STUDIO =================
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right_box.set_margin_top(16)
        right_box.set_margin_bottom(16)
        right_box.set_margin_start(12)
        right_box.set_margin_end(16)

        # Top Action Bar for Transcript
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.stats_lbl = Gtk.Label(label="Ready to transcribe", xalign=0, hexpand=True)
        self.stats_lbl.add_css_class("dim-label")
        top_bar.append(self.stats_lbl)

        # Search entry
        self.search_entry = Gtk.SearchEntry(placeholder_text="Filter transcript...")
        self.search_entry.connect("search-changed", self.on_search_changed)
        top_bar.append(self.search_entry)

        # Copy button
        copy_btn = Gtk.Button(tooltip_text="Copy Transcript to Clipboard")
        copy_btn_content = Adw.ButtonContent(icon_name="edit-copy-symbolic", label="Copy")
        copy_btn.set_child(copy_btn_content)
        copy_btn.connect("clicked", self.on_copy_clicked)
        top_bar.append(copy_btn)

        # Export MenuButton (TXT, SRT, VTT, JSON, LRC)
        export_menu = Gio.Menu()
        export_menu.append("Save Plain Text (.txt)", "win.export_txt")
        export_menu.append("Save Subtitles (.srt)", "win.export_srt")
        export_menu.append("Save WebVTT (.vtt)", "win.export_vtt")
        export_menu.append("Save Lyrics (.lrc)", "win.export_lrc")
        export_menu.append("Save Structured JSON (.json)", "win.export_json")

        export_btn = Gtk.MenuButton(menu_model=export_menu, tooltip_text="Save / Export Transcript")
        export_btn.add_css_class("suggested-action")
        export_btn_content = Adw.ButtonContent(icon_name="document-save-symbolic", label="Export")
        export_btn.set_child(export_btn_content)
        top_bar.append(export_btn)

        right_box.append(top_bar)

        # Transcript TextView inside ScrolledWindow + Frame
        frame = Gtk.Frame()
        text_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.text_view = Gtk.TextView(
            editable=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=16,
            right_margin=16,
            top_margin=16,
            bottom_margin=16,
        )
        self.text_view.add_css_class("transcript-view")
        self.text_buffer = self.text_view.get_buffer()
        self.text_buffer.set_text(
            "Welcome to Omarchy Transcribe Studio!\n\n"
            "1. Click 'Browse PC (Video / Audio)...' or drag & drop any video or audio file.\n"
            "   (Or click 'Record Mic' in the top bar to record live voice).\n"
            "2. Choose your Whisper AI Model (download new models anytime with 1 click).\n"
            "3. Choose your spoken language (or leave on Auto-Detect).\n"
            "4. Click 'Start Transcription' — live segments will stream right here!"
        )
        text_scroll.set_child(self.text_view)
        frame.set_child(text_scroll)
        right_box.append(frame)

        main_paned.set_end_child(right_box)
        toolbar_view.set_content(main_paned)
        self.toast_overlay.set_child(toolbar_view)
        self.set_content(self.toast_overlay)

        # Register Export Actions
        self.register_export_actions()
        self.update_model_status_ui()

    def register_export_actions(self):
        formats = [
            ("export_txt", ".txt"),
            ("export_srt", ".srt"),
            ("export_vtt", ".vtt"),
            ("export_lrc", ".lrc"),
            ("export_json", ".json"),
        ]
        for action_name, ext in formats:
            act = Gio.SimpleAction.new(action_name, None)
            act.connect("activate", lambda _a, _p, e=ext: self.export_transcript_dialog(e))
            self.add_action(act)

        # Keyboard shortcut Ctrl+O to open file
        open_act = Gio.SimpleAction.new("open_file", None)
        open_act.connect("activate", lambda _a, _p: self.on_choose_file_clicked(None))
        self.add_action(open_act)

    def show_toast(self, message: str):
        toast = Adw.Toast.new(message)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    # ================= MODEL SELECTION & DOWNLOADING =================
    def get_selected_model(self) -> WhisperModelInfo:
        idx = self.model_row.get_selected()
        if 0 <= idx < len(MODEL_CATALOG):
            return MODEL_CATALOG[idx]
        return MODEL_CATALOG[0]

    def refresh_model_dropdown(self):
        saved_id = self.settings.get("model_id", "large-v3-turbo-q5_0")
        current_idx = self.model_row.get_selected()
        if 0 <= current_idx < len(MODEL_CATALOG):
            saved_id = MODEL_CATALOG[current_idx].id

        items = []
        target_idx = 0
        for i, m in enumerate(MODEL_CATALOG):
            mark = "✓" if m.is_downloaded else "⬇"
            items.append(f"{mark} {m.name} ({m.disk_size_str})")
            if m.id == saved_id:
                target_idx = i

        self.model_string_list.splice(0, self.model_string_list.get_n_items(), items)
        self.model_row.set_selected(target_idx)
        self.update_model_status_ui()

    def select_model_by_id(self, model_id: str):
        for i, m in enumerate(MODEL_CATALOG):
            if m.id == model_id:
                self.model_row.set_selected(i)
                self.settings["model_id"] = model_id
                self.save_settings()
                self.update_model_status_ui()
                break

    def on_model_selection_changed(self, _row, _pspec):
        model = self.get_selected_model()
        self.settings["model_id"] = model.id
        self.save_settings()
        self.update_model_status_ui()

    def update_model_status_ui(self):
        if not hasattr(self, "model_status_row"):
            return
        model = self.get_selected_model()
        if model.is_downloaded:
            self.model_status_row.set_title(f"✓ {model.name} Installed")
            self.model_status_row.set_subtitle(f"⚡ {model.speed_desc} • 🎯 {model.quality_desc}")
            self.dl_quick_btn.set_visible(False)
            if hasattr(self, "transcribe_btn_content"):
                self.transcribe_btn_content.set_label("Start Transcription")
                self.transcribe_btn_content.set_icon_name("media-playback-start-symbolic")
        else:
            self.model_status_row.set_title(f"⬇ Not Downloaded ({model.size_label})")
            self.model_status_row.set_subtitle(f"Click Download or Start to fetch {model.filename}")
            self.dl_quick_btn.set_visible(True)
            self.dl_quick_btn.set_label(f"Download ({model.size_label})")
            if hasattr(self, "transcribe_btn_content"):
                self.transcribe_btn_content.set_label(f"Download Model & Transcribe")
                self.transcribe_btn_content.set_icon_name("folder-download-symbolic")

    def on_open_model_manager(self, _btn):
        dlg = ModelManagerDialog(self)
        dlg.present()

    def on_quick_download_selected_model(self, _btn):
        model = self.get_selected_model()
        if not model.is_downloaded:
            self.start_model_download(model)

    def start_model_download(self, model: WhisperModelInfo, on_complete=None):
        if self.is_downloading:
            self.show_toast("A model download is already in progress.")
            return

        self.is_downloading = True
        self.cancel_requested = False
        self.progress_box.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("0%")
        self.progress_lbl.set_label(f"Downloading {model.name} ({model.size_label})...")
        self.cancel_btn.set_visible(True)
        self.transcribe_btn.set_sensitive(False)
        self.dl_quick_btn.set_sensitive(False)

        def download_worker():
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            part_path = model.path.with_suffix(".bin.part")
            try:
                req = urllib.request.Request(
                    model.url,
                    headers={"User-Agent": "Omarchy-Transcribe-Studio/1.0"},
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    chunk_size = 256 * 1024
                    last_ui_update = 0.0

                    with open(part_path, "wb") as f:
                        while True:
                            if self.cancel_requested:
                                raise InterruptedError("Download cancelled by user")
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.monotonic()
                            if now - last_ui_update > 0.1:
                                last_ui_update = now
                                frac = (downloaded / total) if total > 0 else 0.0
                                mb_done = downloaded / (1024**2)
                                mb_total = total / (1024**2) if total > 0 else 0
                                GLib.idle_add(
                                    self.update_download_progress,
                                    frac,
                                    f"Downloading {model.name}: {mb_done:.1f} / {mb_total:.1f} MB ({frac*100:.0f}%)",
                                )

                part_path.rename(model.path)
                GLib.idle_add(self.finish_model_download, True, f"Downloaded {model.name}!", model, on_complete)
            except Exception as e:
                if part_path.exists():
                    try:
                        part_path.unlink()
                    except Exception:
                        pass
                GLib.idle_add(self.finish_model_download, False, str(e), model, on_complete)

        threading.Thread(target=download_worker, daemon=True).start()

    def update_download_progress(self, fraction: float, text: str):
        self.progress_bar.set_fraction(min(1.0, max(0.0, fraction)))
        self.progress_bar.set_text(f"{fraction * 100:.0f}%")
        self.progress_lbl.set_label(text)

    def finish_model_download(self, ok: bool, message: str, model: WhisperModelInfo, on_complete):
        self.is_downloading = False
        self.progress_box.set_visible(False)
        self.cancel_btn.set_visible(False)
        self.transcribe_btn.set_sensitive(True)
        self.dl_quick_btn.set_sensitive(True)
        self.refresh_model_dropdown()

        if ok:
            self.show_toast(f"✓ {model.name} downloaded to global models directory")
        else:
            self.show_toast(f"Download stopped: {message}")

        if on_complete:
            on_complete(ok, message)

    # ================= FILE SELECTION & MICROPHONE RECORDING =================
    def on_drag_enter(self, _target, _x, _y):
        self.drop_box.add_css_class("drag-hover")
        return Gdk.DragAction.COPY

    def on_drag_leave(self, _target):
        self.drop_box.remove_css_class("drag-hover")

    def on_file_dropped(self, _target, value, _x, _y):
        self.drop_box.remove_css_class("drag-hover")
        if isinstance(value, Gio.File):
            path_str = value.get_path()
            if path_str:
                self.set_selected_file(Path(path_str))
                return True
        return False

    def on_choose_file_clicked(self, _btn):
        dialog = Gtk.FileDialog(title="Select Video or Audio File to Transcribe")

        filters = Gio.ListStore.new(Gtk.FileFilter)

        all_media = Gtk.FileFilter()
        all_media.set_name("All Video & Audio Media")
        for ext in sorted(MEDIA_EXTENSIONS):
            all_media.add_suffix(ext.lstrip("."))
        filters.append(all_media)

        video_filter = Gtk.FileFilter()
        video_filter.set_name("Video Files (MP4, MKV, MOV, WEBM, AVI...)")
        for ext in sorted(VIDEO_EXTENSIONS):
            video_filter.add_suffix(ext.lstrip("."))
        filters.append(video_filter)

        audio_filter = Gtk.FileFilter()
        audio_filter.set_name("Audio Files (MP3, WAV, FLAC, M4A, OGG, OPUS...)")
        for ext in sorted(MEDIA_EXTENSIONS - VIDEO_EXTENSIONS):
            audio_filter.add_suffix(ext.lstrip("."))
        filters.append(audio_filter)

        any_filter = Gtk.FileFilter()
        any_filter.set_name("All Files (*)")
        any_filter.add_pattern("*")
        filters.append(any_filter)

        dialog.set_filters(filters)
        dialog.set_default_filter(all_media)
        dialog.open(self, None, self.on_file_dialog_response)

    def on_file_dialog_response(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult):
        try:
            gfile = dialog.open_finish(result)
            if gfile and gfile.get_path():
                self.set_selected_file(Path(gfile.get_path()))
        except GLib.Error:
            pass

    def set_selected_file(self, filepath: Path):
        if not filepath.exists():
            self.show_toast(f"File not found: {filepath}")
            return

        self.current_file = filepath
        info = probe_media_info(filepath)
        size_mb = filepath.stat().st_size / (1024**2)

        if info["kind"] == "Video":
            self.media_icon.set_from_icon_name("video-x-generic-symbolic")
        else:
            self.media_icon.set_from_icon_name("audio-x-generic-symbolic")

        self.file_title_lbl.set_label(filepath.name)
        self.file_meta_lbl.set_label(
            f"🎬 {info['kind']}  •  ⏱ {info['duration_str']}  •  📦 {size_mb:.1f} MB  •  {info['details']}"
        )
        self.stats_lbl.set_label(f"Loaded: {filepath.name} ({info['duration_str']})")
        self.show_toast(f"Selected {filepath.name}")

    def on_record_mic_clicked(self, _btn):
        if not self.is_recording:
            self.start_mic_recording()
        else:
            self.stop_mic_recording()

    def start_mic_recording(self):
        rec_dir = Path(tempfile.gettempdir()) / "omarchy-transcribe-recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.record_temp_path = rec_dir / f"mic_recording_{stamp}.wav"

        # Universal Linux / PipeWire / PulseAudio / ALSA / FFmpeg recording fallback
        if shutil.which("pw-record"):
            rec_cmd = [
                "pw-record",
                "--rate=16000",
                "--channels=1",
                "--format=s16",
                str(self.record_temp_path),
            ]
        elif shutil.which("arecord"):
            rec_cmd = [
                "arecord",
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                str(self.record_temp_path),
            ]
        else:
            rec_cmd = [
                "ffmpeg", "-y",
                "-f", "pulse",
                "-i", "default",
                "-ar", "16000",
                "-ac", "1",
                str(self.record_temp_path),
            ]

        try:
            self.record_process = subprocess.Popen(
                rec_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.is_recording = True
            self.record_start_time = time.monotonic()
            self.rec_btn.add_css_class("recording-pulse")
            self.rec_btn_content.set_icon_name("media-playback-stop-symbolic")
            self.rec_btn_content.set_label("Stop Recording (0:00)")
            GLib.timeout_add(500, self.update_record_timer)
            self.show_toast("🎙 Recording from microphone... Click Stop when done.")
        except Exception as e:
            self.show_toast(f"Could not start microphone recording: {e}")

    def update_record_timer(self) -> bool:
        if not self.is_recording:
            return False
        elapsed = time.monotonic() - self.record_start_time
        self.rec_btn_content.set_label(f"Stop Mic ({format_duration(elapsed)})")
        return True

    def stop_mic_recording(self):
        if self.record_process:
            try:
                self.record_process.send_signal(signal.SIGINT)
                self.record_process.wait(timeout=2)
            except Exception:
                self.record_process.kill()
            self.record_process = None

        self.is_recording = False
        self.rec_btn.remove_css_class("recording-pulse")
        self.rec_btn_content.set_icon_name("audio-input-microphone-symbolic")
        self.rec_btn_content.set_label("Record Mic")

        if self.record_temp_path and self.record_temp_path.exists():
            self.set_selected_file(self.record_temp_path)
            self.show_toast("🎙 Recording ready! Click Start Transcription.")

    # ================= SETTINGS & LANGUAGE HANDLERS =================
    def on_language_changed(self, _row, _pspec):
        idx = self.lang_row.get_selected()
        if 0 <= idx < len(LANGUAGES):
            self.settings["language"] = LANGUAGES[idx][0]
            self.save_settings()

    def on_settings_toggled(self, _row, _pspec):
        self.settings["translate_to_en"] = self.translate_switch.get_active()
        self.settings["use_vad"] = self.vad_switch.get_active()
        self.settings["use_gpu"] = self.gpu_switch.get_active()
        self.save_settings()

    def on_timestamps_toggled(self, _row, _pspec):
        self.settings["show_timestamps"] = self.ts_switch.get_active()
        self.save_settings()
        self.refresh_transcript_view()

    # ================= TRANSCRIPTION PIPELINE =================
    def on_start_transcribe_clicked(self, _btn):
        if self.is_transcribing or self.is_downloading:
            return

        if not self.current_file or not self.current_file.exists():
            self.show_toast("Please select a video or audio file first!")
            self.on_choose_file_clicked(None)
            return

        model = self.get_selected_model()
        if not model.is_downloaded:
            # Automatically download missing model and then start transcription
            self.start_model_download(
                model,
                on_complete=lambda ok, _msg: self.run_transcription_pipeline() if ok else None,
            )
            return

        self.run_transcription_pipeline()

    def on_cancel_clicked(self, _btn):
        self.cancel_requested = True
        if self.active_process:
            try:
                self.active_process.terminate()
            except Exception:
                pass

    def run_transcription_pipeline(self):
        if not self.current_file:
            return

        model = self.get_selected_model()
        lang_code = LANGUAGES[self.lang_row.get_selected()][0]
        translate = self.translate_switch.get_active()
        use_vad = self.vad_switch.get_active()
        use_gpu = self.gpu_switch.get_active() and bool(self.hw_info["has_gpu"])

        self.is_transcribing = True
        self.cancel_requested = False
        self.segments.clear()
        self.text_buffer.set_text("")

        self.progress_box.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("0%")
        self.progress_lbl.set_label("Extracting 16kHz audio stream with FFmpeg...")
        self.cancel_btn.set_visible(True)
        self.transcribe_btn.set_sensitive(False)
        self.stats_lbl.set_label(f"Transcribing {self.current_file.name} with {model.name}...")

        def worker():
            start_t = time.monotonic()
            tmp_wav = None
            try:
                # Step 1: Convert any audio/video to 16kHz mono PCM WAV via FFmpeg
                fd, tmp_wav_str = tempfile.mkstemp(prefix="omarchy_whisper_", suffix=".wav")
                os.close(fd)
                tmp_wav = Path(tmp_wav_str)

                ff_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(self.current_file),
                    "-vn",
                    "-ar", "16000",
                    "-ac", "1",
                    "-c:a", "pcm_s16le",
                    str(tmp_wav),
                ]
                self.active_process = subprocess.Popen(
                    ff_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                _, ff_err = self.active_process.communicate()
                if self.cancel_requested:
                    raise InterruptedError("Cancelled during audio extraction")
                if self.active_process.returncode != 0:
                    raise RuntimeError(f"FFmpeg could not extract audio:\n{ff_err[-300:]}")

                # Step 2: Ensure VAD model exists if VAD is enabled
                vad_model_path = MODELS_DIR / "ggml-silero-v6.2.0.bin"
                if use_vad and not vad_model_path.exists():
                    GLib.idle_add(self.update_download_progress, 0.05, "Downloading Silero VAD model (865 KB)...")
                    try:
                        urllib.request.urlretrieve(VAD_HF_URL, str(vad_model_path))
                    except Exception:
                        pass

                # Step 3: Run whisper-cli and stream segments + progress
                target_accel = str(self.hw_info["backend"]) if use_gpu else "Multi-Core CPU"
                GLib.idle_add(
                    self.update_download_progress,
                    0.05,
                    f"Loading {model.name} on {target_accel}...",
                )

                threads = str(self.settings.get("threads", min(8, os.cpu_count() or 4)))
                whisper_bin = str(self.hw_info.get("whisper_bin", "whisper-cli"))
                w_cmd = [
                    whisper_bin,
                    "-m", str(model.path),
                    "-f", str(tmp_wav),
                    "-l", lang_code,
                    "-t", threads,
                    "-pp",
                ]
                if translate:
                    w_cmd.append("-tr")
                if not use_gpu:
                    w_cmd.append("-ng")
                if use_vad and vad_model_path.exists():
                    w_cmd.extend(["--vad", "-vm", str(vad_model_path)])

                self.active_process = subprocess.Popen(
                    w_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                seg_regex = re.compile(r"^\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*)$")
                prog_regex = re.compile(r"progress\s*=\s*(\d+)%")
                lang_det_regex = re.compile(r"auto-detected language:\s*(\w+)")
                detected_lang = lang_code

                for raw_line in self.active_process.stdout:
                    if self.cancel_requested:
                        self.active_process.terminate()
                        raise InterruptedError("Transcription cancelled")

                    line = raw_line.strip()
                    if not line:
                        continue

                    # Check progress
                    pm = prog_regex.search(line)
                    if pm:
                        pct = int(pm.group(1))
                        GLib.idle_add(
                            self.update_download_progress,
                            pct / 100.0,
                            f"Transcribing with {model.name} ({detected_lang.upper()})... {pct}%",
                        )
                        continue

                    # Check auto-detected language
                    lm = lang_det_regex.search(line)
                    if lm:
                        detected_lang = lm.group(1)
                        GLib.idle_add(
                            self.progress_lbl.set_label,
                            f"Detected language: {detected_lang.upper()} — Transcribing...",
                        )
                        continue

                    # Check segment output
                    sm = seg_regex.match(line)
                    if sm:
                        start_s, end_s, text_s = sm.group(1), sm.group(2), sm.group(3).strip()
                        if text_s:
                            seg = Segment(
                                start_ms=parse_timestamp_ms(start_s),
                                end_ms=parse_timestamp_ms(end_s),
                                start_str=start_s,
                                end_str=end_s,
                                text=text_s,
                            )
                            GLib.idle_add(self.append_live_segment, seg)

                self.active_process.wait()
                if self.cancel_requested:
                    raise InterruptedError("Transcription cancelled")

                elapsed = time.monotonic() - start_t
                GLib.idle_add(self.finish_transcription, True, f"Completed in {elapsed:.1f}s", detected_lang)

            except InterruptedError as ie:
                GLib.idle_add(self.finish_transcription, False, str(ie), lang_code)
            except Exception as e:
                GLib.idle_add(self.finish_transcription, False, str(e), lang_code)
            finally:
                self.active_process = None
                if tmp_wav and tmp_wav.exists():
                    try:
                        tmp_wav.unlink()
                    except Exception:
                        pass

        threading.Thread(target=worker, daemon=True).start()

    def append_live_segment(self, seg: Segment):
        self.segments.append(seg)
        self.refresh_transcript_view(scroll_to_bottom=True)

    def refresh_transcript_view(self, scroll_to_bottom: bool = False):
        query = self.search_entry.get_text().strip().lower()
        show_ts = self.ts_switch.get_active()

        lines = []
        for s in self.segments:
            if query and query not in s.text.lower():
                continue
            if show_ts:
                lines.append(f"[{s.start_str} --> {s.end_str}]  {s.text}")
            else:
                lines.append(s.text)

        if show_ts:
            full_str = "\n".join(lines)
        else:
            full_str = "\n\n".join(lines)

        self.text_buffer.set_text(full_str)

        if scroll_to_bottom:
            end_iter = self.text_buffer.get_end_iter()
            self.text_view.scroll_to_iter(end_iter, 0.0, False, 0.0, 1.0)

    def finish_transcription(self, ok: bool, msg: str, detected_lang: str):
        self.is_transcribing = False
        self.progress_box.set_visible(False)
        self.cancel_btn.set_visible(False)
        self.transcribe_btn.set_sensitive(True)

        if ok:
            word_count = sum(len(s.text.split()) for s in self.segments)
            self.stats_lbl.set_label(
                f"✓ Done ({msg})  •  Language: {detected_lang.upper()}  •  {len(self.segments)} segments  •  {word_count} words"
            )
            if not self.segments:
                self.text_buffer.set_text("[No speech detected in the selected media file.]")
            self.show_toast(f"✓ Transcription complete ({word_count} words)")
            try:
                subprocess.Popen(
                    [
                        "notify-send",
                        "-a", "Omarchy Transcribe",
                        "-i", "audio-input-microphone",
                        "Transcription Complete",
                        f"{self.current_file.name if self.current_file else 'Media'}: {word_count} words ({msg})",
                    ]
                )
            except Exception:
                pass
        else:
            self.stats_lbl.set_label(f"⚠ {msg}")
            self.show_toast(msg)

    # ================= SEARCH, COPY & EXPORT =================
    def on_search_changed(self, _entry):
        if self.segments:
            self.refresh_transcript_view()

    def get_current_buffer_text(self) -> str:
        start = self.text_buffer.get_start_iter()
        end = self.text_buffer.get_end_iter()
        return self.text_buffer.get_text(start, end, False).strip()

    def on_copy_clicked(self, _btn):
        text = self.get_current_buffer_text()
        if not text:
            self.show_toast("Nothing to copy yet!")
            return

        # Copy via GDK4 clipboard + Wayland (wl-copy) / X11 (xclip/xsel) fallbacks
        clipboard = self.get_clipboard()
        clipboard.set(text)
        try:
            if shutil.which("wl-copy"):
                subprocess.run(["wl-copy"], input=text, text=True, timeout=2)
            elif shutil.which("xclip"):
                subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, timeout=2)
        except Exception:
            pass
        self.show_toast("✓ Transcript copied to clipboard!")

    def format_export_content(self, ext: str) -> str:
        if not self.segments:
            return self.get_current_buffer_text()

        if ext == ".txt":
            if self.ts_switch.get_active():
                return "\n".join(f"[{s.start_str} --> {s.end_str}]  {s.text}" for s in self.segments) + "\n"
            return "\n\n".join(s.text for s in self.segments) + "\n"

        if ext == ".srt":
            blocks = []
            for idx, s in enumerate(self.segments, 1):
                blocks.append(f"{idx}\n{format_srt_ts(s.start_ms)} --> {format_srt_ts(s.end_ms)}\n{s.text}")
            return "\n\n".join(blocks) + "\n"

        if ext == ".vtt":
            blocks = ["WEBVTT\n"]
            for s in self.segments:
                blocks.append(f"{format_vtt_ts(s.start_ms)} --> {format_vtt_ts(s.end_ms)}\n{s.text}")
            return "\n\n".join(blocks) + "\n"

        if ext == ".lrc":
            lines = [f"[{format_lrc_ts(s.start_ms)}]{s.text}" for s in self.segments]
            return "\n".join(lines) + "\n"

        if ext == ".json":
            payload = {
                "source_file": str(self.current_file) if self.current_file else None,
                "model": self.get_selected_model().id,
                "language": LANGUAGES[self.lang_row.get_selected()][0],
                "segments": [
                    {
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                        "start": s.start_str,
                        "end": s.end_str,
                        "text": s.text,
                    }
                    for s in self.segments
                ],
                "full_text": " ".join(s.text for s in self.segments),
            }
            return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

        return self.get_current_buffer_text()

    def export_transcript_dialog(self, ext: str):
        if not self.segments and not self.get_current_buffer_text():
            self.show_toast("No transcript to export yet!")
            return

        dialog = Gtk.FileDialog(title=f"Export Transcript ({ext.upper()})")
        base_name = self.current_file.stem if self.current_file else "transcript"
        dialog.set_initial_name(f"{base_name}{ext}")
        if self.current_file and self.current_file.parent.exists():
            dialog.set_initial_folder(Gio.File.new_for_path(str(self.current_file.parent)))

        dialog.save(self, None, lambda d, res: self.on_export_save_response(d, res, ext))

    def on_export_save_response(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult, ext: str):
        try:
            gfile = dialog.save_finish(result)
            if gfile and gfile.get_path():
                out_path = Path(gfile.get_path())
                content = self.format_export_content(ext)
                out_path.write_text(content, encoding="utf-8")
                self.show_toast(f"✓ Saved to {out_path.name}")
        except GLib.Error:
            pass
        except Exception as e:
            self.show_toast(f"Failed to save file: {e}")


class TranscribeApp(Adw.Application):
    def __init__(self, initial_file: Optional[str] = None):
        super().__init__(
            application_id="org.omarchy.transcribe",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        GLib.set_prgname("org.omarchy.transcribe")
        GLib.set_application_name("Omarchy Transcribe Studio")
        self.initial_file = initial_file
        self.win: Optional[TranscribeMainWindow] = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        style_mgr = Adw.StyleManager.get_default()
        style_mgr.set_color_scheme(Adw.ColorScheme.PREFER_DARK)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_string(CUSTOM_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self.set_accels_for_action("win.open_file", ["<Control>o"])

    def do_activate(self):
        if not self.win:
            self.win = TranscribeMainWindow(self, initial_file=self.initial_file)
        self.win.present()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        file_arg = next((a for a in args if not a.startswith("-")), None)
        if file_arg:
            self.initial_file = file_arg
            if self.win:
                p = Path(file_arg).expanduser().resolve()
                if p.exists():
                    self.win.set_selected_file(p)
        self.activate()
        return 0


def run_cli_mode(args: argparse.Namespace) -> int:
    """Headless CLI mode when invoked with --cli <file>."""
    filepath = Path(args.file).expanduser().resolve()
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        return 1

    model = next((m for m in MODEL_CATALOG if m.id == args.model or m.filename == args.model), MODEL_CATALOG[0])
    if not model.is_downloaded:
        print(f"Model '{model.name}' not found in {MODELS_DIR}. Downloading from HuggingFace...")
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(model.url, str(model.path))
        print(f"Downloaded {model.path}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = Path(tmp.name)

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(filepath), "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(tmp_wav)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cmd = [
            "whisper-cli",
            "-m", str(model.path),
            "-f", str(tmp_wav),
            "-l", args.language,
        ]
        if args.translate:
            cmd.append("-tr")
        vad_path = MODELS_DIR / "ggml-silero-v6.2.0.bin"
        if vad_path.exists():
            cmd.extend(["--vad", "-vm", str(vad_path)])
        return subprocess.call(cmd)
    finally:
        if tmp_wav.exists():
            tmp_wav.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Omarchy Transcribe Studio — GUI & CLI Whisper AI Transcriber",
        add_help=False,
    )
    parser.add_argument("file", nargs="?", help="Optional audio or video file to load")
    parser.add_argument("--cli", action="store_true", help="Run in terminal CLI mode without GUI")
    parser.add_argument("-m", "--model", default="large-v3-turbo-q5_0", help="Whisper model ID (default: large-v3-turbo-q5_0)")
    parser.add_argument("-l", "--language", default="auto", help="Language code (e.g., auto, en, it, es, fr)")
    parser.add_argument("-tr", "--translate", action="store_true", help="Translate speech to English")
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")

    parsed, unknown = parser.parse_known_args()
    if parsed.help:
        parser.print_help()
        sys.exit(0)

    if parsed.cli and parsed.file:
        sys.exit(run_cli_mode(parsed))

    app = TranscribeApp(initial_file=parsed.file)
    sys.exit(app.run([sys.argv[0]] + ([parsed.file] if parsed.file else [])))


if __name__ == "__main__":
    main()
