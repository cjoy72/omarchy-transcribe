#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARE_DIR="${HOME}/.local/share/omarchy-transcribe-gui"
BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"
MODELS_DIR="${WHISPER_MODELS_DIR:-${HOME}/.local/share/whisper-cpp/models}"

echo "==> Installing Omarchy Transcribe Studio..."

mkdir -p "$BIN_DIR" "$APPS_DIR" "$MODELS_DIR"

# Link or copy application directory
if [[ "$REPO_DIR" != "$SHARE_DIR" ]]; then
    ln -sfn "$REPO_DIR" "$SHARE_DIR"
fi

chmod +x "$REPO_DIR/transcribe_app.py"

# Create launcher script
cat > "$BIN_DIR/omarchy-transcribe" << 'EOF'
#!/usr/bin/env bash
# omarchy-transcribe - Modern Whisper transcription GUI for Omarchy

APP_SCRIPT="${HOME}/.local/share/omarchy-transcribe-gui/transcribe_app.py"

exec python3 "$APP_SCRIPT" "$@"
EOF

chmod +x "$BIN_DIR/omarchy-transcribe"
ln -sfn "$BIN_DIR/omarchy-transcribe" "$BIN_DIR/transcribe"

# Install desktop entry
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

echo "==> Installed successfully!"
echo "    - Command: transcribe (or omarchy-transcribe)"
echo "    - Models directory: $MODELS_DIR"
