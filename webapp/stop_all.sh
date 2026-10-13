#!/bin/bash
#
# Script pour arrêter tous les services de la webapp
#
# Usage:
#   ./webapp/stop_all.sh
#

set -e

echo "========================================="
echo "  Stopping Scholarmap Webapp"
echo "========================================="
echo ""

LOGS_DIR="/tmp/sci-diligence-webapp"

# Fonction pour arrêter un processus par nom
stop_process() {
    local process_name=$1
    local friendly_name=$2

    echo "🛑 Stopping $friendly_name..."

    if pgrep -f "$process_name" > /dev/null 2>&1; then
        pkill -f "$process_name"
        sleep 1

        if pgrep -f "$process_name" > /dev/null 2>&1; then
            echo "  ⚠️  Process still running, force killing..."
            pkill -9 -f "$process_name"
        fi

        echo "  ✅ $friendly_name stopped"
    else
        echo "  ℹ️  $friendly_name was not running"
    fi
}

# Arrêter Flask
stop_process "webapp/app.py" "Flask app"

# Arrêter Celery
stop_process "celery.*worker" "Celery worker"

# Arrêter Redis (optionnel - peut être utilisé par d'autres apps)
read -p "Stop Redis server? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    stop_process "redis-server" "Redis"
fi

# Nettoyer les fichiers PID
if [ -d "$LOGS_DIR" ]; then
    rm -f "$LOGS_DIR"/*.pid
    echo ""
    echo "📁 Logs preserved in: $LOGS_DIR"
fi

echo ""
echo "========================================="
echo "  ✅ All services stopped"
echo "========================================="
echo ""
