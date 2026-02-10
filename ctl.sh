#!/bin/bash
# TeleAutoGram control script

APP_NAME="tele-auto-gram"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$APP_DIR/$APP_NAME.pid"
LOG_FILE="$APP_DIR/$APP_NAME.log"
PYTHON="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"

OS="$(uname -s)"
SERVICE_LABEL="com.nalbam.$APP_NAME"
WEB_HOST="${HOST:-0.0.0.0}"
WEB_PORT="${PORT:-5000}"

# --- helpers ---

_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return
        fi
        rm -f "$PID_FILE"
    fi
}

_require_python() {
    if [ -z "$PYTHON" ]; then
        echo "Error: python3 not found"
        exit 1
    fi
}

_copy_identity() {
    local src="$APP_DIR/example/IDENTITY.md"
    local dst="$APP_DIR/data/IDENTITY.md"
    
    if [ ! -f "$src" ]; then
        echo "Error: Source file not found: $src"
        return 1
    fi
    
    mkdir -p "$APP_DIR/data"
    if cp "$src" "$dst"; then
        echo "Copied $src -> $dst"
    else
        echo "Error: Failed to copy file"
        return 1
    fi
}

# --- background commands ---

bg_start() {
    _require_python
    if [ -n "$(_pid)" ]; then
        echo "Already running (PID $(_pid))"
        return
    fi
    cd "$APP_DIR"
    nohup "$PYTHON" main.py >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started (PID $!), log: $LOG_FILE"
    if [ "$WEB_HOST" = "0.0.0.0" ]; then
        echo "Web UI: http://127.0.0.1:$WEB_PORT"
    else
        echo "Web UI: http://$WEB_HOST:$WEB_PORT"
    fi
}

bg_stop() {
    local pid
    pid=$(_pid)
    if [ -z "$pid" ]; then
        echo "Not running"
        return
    fi
    kill "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "Stopped (PID $pid)"
}

bg_restart() {
    local copy_identity="${1:-}"
    bg_stop
    cd "$APP_DIR"
    echo "Pulling latest changes..."
    git pull
    # Copy identity AFTER git pull to use the latest example file
    # Note: This will overwrite any local customizations in data/IDENTITY.md
    # Errors are non-fatal - restart continues even if copy fails
    if [ "$copy_identity" = "--copy-identity" ]; then
        _copy_identity || true
    fi
    sleep 1
    bg_start
}

bg_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo "No log file: $LOG_FILE"
        return
    fi
    tail -f "$LOG_FILE"
}

bg_status() {
    local pid
    pid=$(_pid)
    if [ -n "$pid" ]; then
        echo "Running (PID $pid)"
    else
        echo "Stopped"
    fi
}

# --- service commands (systemd / launchd) ---

_systemd_file="/etc/systemd/system/$APP_NAME.service"
_launchd_file="$HOME/Library/LaunchAgents/$SERVICE_LABEL.plist"

svc_install() {
    _require_python
    if [ "$OS" = "Linux" ]; then
        sudo tee "$_systemd_file" > /dev/null << EOF
[Unit]
Description=TeleAutoGram
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$PYTHON main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable "$APP_NAME"
        echo "Service installed: $_systemd_file"

    elif [ "$OS" = "Darwin" ]; then
        mkdir -p "$HOME/Library/LaunchAgents"
        cat > "$_launchd_file" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$SERVICE_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$APP_DIR</string>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>$LOG_FILE</string>
    <key>StandardErrorPath</key>
    <string>$LOG_FILE</string>
</dict>
</plist>
EOF
        echo "Service installed: $_launchd_file"
    fi
}

svc_start() {
    if [ "$OS" = "Linux" ]; then
        sudo systemctl start "$APP_NAME"
    elif [ "$OS" = "Darwin" ]; then
        launchctl load "$_launchd_file"
    fi
    echo "Service started"
    if [ "$WEB_HOST" = "0.0.0.0" ]; then
        echo "Web UI: http://127.0.0.1:$WEB_PORT"
    else
        echo "Web UI: http://$WEB_HOST:$WEB_PORT"
    fi
}

svc_stop() {
    if [ "$OS" = "Linux" ]; then
        sudo systemctl stop "$APP_NAME"
    elif [ "$OS" = "Darwin" ]; then
        launchctl unload "$_launchd_file" 2>/dev/null
    fi
    echo "Service stopped"
}

svc_restart() {
    local copy_identity="${1:-}"
    cd "$APP_DIR"
    echo "Pulling latest changes..."
    git pull
    # Copy identity AFTER git pull to use the latest example file
    # Note: This will overwrite any local customizations in data/IDENTITY.md
    # Errors are non-fatal - restart continues even if copy fails
    if [ "$copy_identity" = "--copy-identity" ]; then
        _copy_identity || true
    fi
    if [ "$OS" = "Linux" ]; then
        sudo systemctl restart "$APP_NAME"
        echo "Service restarted"
        if [ "$WEB_HOST" = "0.0.0.0" ]; then
            echo "Web UI: http://127.0.0.1:$WEB_PORT"
        else
            echo "Web UI: http://$WEB_HOST:$WEB_PORT"
        fi
    elif [ "$OS" = "Darwin" ]; then
        svc_stop
        sleep 1
        svc_start
    fi
}

svc_uninstall() {
    svc_stop 2>/dev/null || true
    if [ "$OS" = "Linux" ]; then
        sudo systemctl disable "$APP_NAME" 2>/dev/null || true
        sudo rm -f "$_systemd_file"
        sudo systemctl daemon-reload
    elif [ "$OS" = "Darwin" ]; then
        rm -f "$_launchd_file"
    fi
    echo "Service uninstalled"
}

svc_logs() {
    if [ "$OS" = "Linux" ]; then
        sudo journalctl -u "$APP_NAME" -f
    elif [ "$OS" = "Darwin" ]; then
        bg_logs
    fi
}

svc_status() {
    if [ "$OS" = "Linux" ]; then
        sudo systemctl status "$APP_NAME" --no-pager
    elif [ "$OS" = "Darwin" ]; then
        launchctl list | grep "$SERVICE_LABEL" || echo "Service not loaded"
    fi
}

# --- main ---

usage() {
    cat << EOF
Usage: $0 <command> [options]

Background:
  start                Start in background
  stop                 Stop background process
  restart              Restart background process
  restart --copy-identity  Restart and copy example/IDENTITY.md to data/IDENTITY.md
  status               Show background process status
  logs                 Tail background log

Service (systemd on Linux, launchd on macOS):
  install              Register as system service
  uninstall            Remove system service
  svc-start            Start service
  svc-stop             Stop service
  svc-restart          Restart service
  svc-restart --copy-identity  Restart service and copy example/IDENTITY.md to data/IDENTITY.md
  svc-status           Show service status
  svc-logs             Tail service logs

Utilities:
  copy-identity        Copy example/IDENTITY.md to data/IDENTITY.md
EOF
}

case "${1:-}" in
    start)       bg_start ;;
    stop)        bg_stop ;;
    restart)     bg_restart "$2" ;;
    status)      bg_status ;;
    logs)        bg_logs ;;
    install)     svc_install ;;
    uninstall)   svc_uninstall ;;
    svc-start)   svc_start ;;
    svc-stop)    svc_stop ;;
    svc-restart) svc_restart "$2" ;;
    svc-status)  svc_status ;;
    svc-logs)    svc_logs ;;
    copy-identity) _copy_identity ;;
    *)           usage ;;
esac
