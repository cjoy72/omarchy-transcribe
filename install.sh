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

# 2. Auto-detect GPU vendor (NVIDIA / AMD / Intel / CPU) & install missing packages if needed
detect_and_install_deps() {
    local gpu_vendor="cpu"
    if command -v nvidia-smi >/dev/null 2>&1 || (command -v lspci >/dev/null 2>&1 && lspci | grep -qi "nvidia"); then
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

    # Check if core runtime tools are already present
    if command -v whisper-cli >/dev/null 2>&1 && command -v ffmpeg >/dev/null 2>&1 && python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')" 2>/dev/null; then
        # On Arch, check if NVIDIA user needs ggml-cuda / ggml-vulkan or AMD/Intel user needs ggml-vulkan
        if command -v pacman >/dev/null 2>&1; then
            if [[ "$gpu_vendor" == "nvidia" ]] && ! pacman -Qi ggml-cuda >/dev/null 2>&1 && ! pacman -Qi ggml-vulkan >/dev/null 2>&1; then
                echo "==> Installing GPU acceleration backend for NVIDIA..."
                sudo pacman -S --needed --noconfirm ggml-cuda ggml-vulkan || sudo pacman -S --needed --noconfirm ggml-vulkan || true
            elif [[ "$gpu_vendor" == "amd" || "$gpu_vendor" == "intel" ]] && ! pacman -Qi ggml-vulkan >/dev/null 2>&1; then
                echo "==> Installing Vulkan GPU backend..."
                sudo pacman -S --needed --noconfirm ggml-vulkan || true
            fi
        fi
        return 0
    fi

    echo "==> Installing system dependencies..."
    if command -v pacman >/dev/null 2>&1; then
        local pkgs=(whisper-cpp ffmpeg python-gobject gtk4 libadwaita wl-clipboard libnotify)
        if [[ "$gpu_vendor" == "nvidia" ]]; then
            # Install Vulkan + CUDA backends on NVIDIA machines
            pkgs+=(ggml-vulkan)
            if pacman -Si ggml-cuda >/dev/null 2>&1; then
                pkgs+=(ggml-cuda)
            fi
        elif [[ "$gpu_vendor" == "amd" || "$gpu_vendor" == "intel" ]]; then
            pkgs+=(ggml-vulkan)
        fi
        sudo pacman -S --needed --noconfirm "${pkgs[@]}"
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y ffmpeg python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 wl-clipboard xclip libnotify-bin
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y ffmpeg python3-gobject gtk4 libadwaita wl-clipboard xclip libnotify
    fi
}

detect_and_install_deps

# 3. Set up directories, symlinks, launcher, and desktop entry
mkdir -p "$BIN_DIR" "$APPS_DIR" "$MODELS_DIR"

if [[ "$SOURCE_DIR" != "$SHARE_DIR" ]]; then
    ln -sfn "$SOURCE_DIR" "$SHARE_DIR"
fi

chmod +x "$SOURCE_DIR/transcribe_app.py"

cat > "$BIN_DIR/omarchy-transcribe" << 'EOF'
#!/usr/bin/env bash
# omarchy-transcribe - Modern Whisper transcription GUI for Omarchy & Linux

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
