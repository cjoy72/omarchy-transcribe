#!/usr/bin/env bash
# Universal Installer for Omarchy Transcribe Studio
# Supports NVIDIA (CUDA & Vulkan), AMD (ROCm & Vulkan), Intel (Vulkan & OpenVINO), and CPU-only systems.
# Can be run directly via:
#   curl -fsSL https://raw.githubusercontent.com/cjoy72/omarchy-transcribe/main/install.sh | bash
# or from a cloned repository:
#   ./install.sh

set -euo pipefail

REPO_URL="https://github.com/cjoy72/omarchy-transcribe.git"
SHARE_DIR="${HOME}/.local/share/omarchy-transcribe-gui"
BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"
MODELS_DIR="${WHISPER_MODELS_DIR:-${HOME}/.local/share/whisper-cpp/models}"

echo "==> Omarchy Transcribe Studio — Universal Installer"

# 1. Detect if running from a local git checkout or via curl | bash
SCRIPT_SOURCE="${BASH_SOURCE[0]:-}"
if [[ -n "$SCRIPT_SOURCE" && -f "$(dirname "$SCRIPT_SOURCE")/transcribe_app.py" ]]; then
    SOURCE_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"
else
    echo "==> Fetching repository into $SHARE_DIR..."
    if [[ -d "$SHARE_DIR/.git" ]]; then
        git -C "$SHARE_DIR" pull --ff-only
    else
        rm -rf "$SHARE_DIR"
        git clone "$REPO_URL" "$SHARE_DIR"
    fi
    SOURCE_DIR="$SHARE_DIR"
fi

# 2. Auto-detect GPU vendor (NVIDIA / AMD / Intel / Apple Silicon / CPU) & install missing packages if needed
detect_and_install_deps() {
    local arch="$(uname -m)"
    local gpu_vendor="cpu"

    if [[ "$arch" == "aarch64" || "$arch" == "arm64" ]]; then
        if grep -qi "apple" /proc/cpuinfo 2>/dev/null; then
            gpu_vendor="apple"
            echo "==> Detected Compute: Apple Silicon (NEON & ARM_FMA Optimized)"
        else
            echo "==> Detected Compute: ARM64 CPU"
        fi
    elif command -v nvidia-smi >/dev/null 2>&1 || (command -v lspci >/dev/null 2>&1 && lspci | grep -qi "nvidia"); then
        gpu_vendor="nvidia"
        echo "==> Detected GPU: NVIDIA"
    elif command -v lspci >/dev/null 2>&1 && lspci | grep -Eqi "amd|radeon|advanced micro devices"; then
        gpu_vendor="amd"
        echo "==> Detected GPU: AMD Radeon"
    elif command -v lspci >/dev/null 2>&1 && lspci | grep -qi "intel.*graphics\|intel.*arc\|intel.*vga"; then
        gpu_vendor="intel"
        echo "==> Detected GPU: Intel Graphics"
    else
        echo "==> Detected Compute: Multi-Core CPU"
    fi

    # Check if core runtime GUI and media tools are already present
    local need_sys_pkgs=0
    if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1 || \
       ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')" 2>/dev/null || \
       ! command -v wl-copy >/dev/null 2>&1 || ! command -v notify-send >/dev/null 2>&1; then
        need_sys_pkgs=1
    fi

    if (( need_sys_pkgs )); then
        echo "==> Installing missing system dependencies..."
        if command -v pacman >/dev/null 2>&1; then
            local candidate_pkgs=(ffmpeg python-gobject gtk4 libadwaita wl-clipboard libnotify)
            local to_install=()
            for pkg in "${candidate_pkgs[@]}"; do
                if pacman -Si "$pkg" >/dev/null 2>&1; then
                    to_install+=("$pkg")
                fi
            done
            # Only add whisper-cpp or ggml-vulkan if they exist in repos
            if pacman -Si whisper-cpp >/dev/null 2>&1; then
                to_install+=(whisper-cpp)
            fi
            if [[ "$gpu_vendor" != "cpu" && "$gpu_vendor" != "apple" ]] && pacman -Si ggml-vulkan >/dev/null 2>&1; then
                to_install+=(ggml-vulkan)
            fi
            if (( ${#to_install[@]} > 0 )); then
                sudo pacman -S --needed --noconfirm "${to_install[@]}" || true
            fi
        elif command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update || true
            sudo apt-get install -y ffmpeg python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 wl-clipboard xclip libnotify-bin || true
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y ffmpeg python3-gobject gtk4 libadwaita wl-clipboard xclip libnotify || true
        fi
    fi

    # Ensure whisper-cli is installed (download prebuilt binary if missing from PATH)
    if ! command -v whisper-cli >/dev/null 2>&1 && ! command -v whisper-cpp >/dev/null 2>&1; then
        echo "==> whisper-cli not found on PATH. Installing official prebuilt binary..."
        local whisper_ver="b5454"
        local whisper_tarball=""
        if [[ "$arch" == "x86_64" ]]; then
            whisper_tarball="whisper-bin-ubuntu-x64.tar.gz"
        elif [[ "$arch" == "aarch64" || "$arch" == "arm64" ]]; then
            whisper_tarball="whisper-bin-ubuntu-arm64.tar.gz"
        fi

        if [[ -n "$whisper_tarball" ]]; then
            local target_lib="${HOME}/.local/lib/whisper-cpp"
            mkdir -p "$target_lib" "$BIN_DIR"
            echo "==> Downloading whisper.cpp ($whisper_ver for $arch)..."
            curl -fsSL "https://github.com/ggerganov/whisper.cpp/releases/download/${whisper_ver}/${whisper_tarball}" | \
                tar -xz --strip-components=1 -C "$target_lib"
            ln -sfn "${target_lib}/whisper-cli" "${BIN_DIR}/whisper-cli"
            chmod +x "${BIN_DIR}/whisper-cli"
            echo "==> Installed whisper-cli to ${BIN_DIR}/whisper-cli"
        else
            echo "Warning: No prebuilt whisper-cli binary available for $arch. Please build whisper.cpp manually." >&2
        fi
    fi
}

detect_and_install_deps

# 3. Set up directories, symlinks, launcher, and desktop entry
mkdir -p "$BIN_DIR" "$APPS_DIR" "$MODELS_DIR"

# Pre-fetch Silero VAD model (865 KB) if not already present for silence detection
if [[ ! -f "$MODELS_DIR/ggml-silero-v6.2.0.bin" ]]; then
    echo "==> Downloading Silero VAD model (865 KB) into $MODELS_DIR..."
    curl -fsSL "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin" -o "$MODELS_DIR/ggml-silero-v6.2.0.bin" || true
fi

if [[ "$SOURCE_DIR" != "$SHARE_DIR" ]]; then
    rm -rf "$SHARE_DIR"
    ln -sfn "$SOURCE_DIR" "$SHARE_DIR"
fi

chmod +x "$SOURCE_DIR/transcribe_app.py"

cat > "$BIN_DIR/omarchy-transcribe" << 'EOF'
#!/usr/bin/env bash
# omarchy-transcribe - Modern Whisper transcription GUI for Omarchy & Linux

export PATH="${HOME}/.local/bin:${PATH}"
APP_SCRIPT="${HOME}/.local/share/omarchy-transcribe-gui/transcribe_app.py"

exec python3 "$APP_SCRIPT" "$@"
EOF

chmod +x "$BIN_DIR/omarchy-transcribe"
ln -sfn "$BIN_DIR/omarchy-transcribe" "$BIN_DIR/transcribe"

cat > "$APPS_DIR/omarchy-transcribe.desktop" << EOF
[Desktop Entry]
Version=1.0
Name=Transcribe Studio
GenericName=Audio & Video Transcriber
Comment=Whisper AI speech-to-text audio and video transcriber with model manager
Exec=${BIN_DIR}/omarchy-transcribe %f
Icon=audio-input-microphone
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Utility;
Keywords=transcribe;whisper;speech;text;audio;video;subtitles;srt;voice;ai;
StartupNotify=true
StartupWMClass=org.omarchy.transcribe
MimeType=audio/mpeg;audio/x-wav;audio/flac;audio/ogg;audio/mp4;video/mp4;video/x-matroska;video/webm;video/quicktime;
EOF

echo ""
echo "==> Installed Omarchy Transcribe Studio successfully!"
echo "    - Launch GUI:  transcribe (or search 'Transcribe Studio' in your app launcher)"
echo "    - CLI Mode:    transcribe --cli <video_or_audio_file>"
echo "    - Models Dir:  $MODELS_DIR"
