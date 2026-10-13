#!/bin/bash
#
# Script pour lancer tous les services de la webapp en même temps
#
# Usage:
#   ./webapp/start_all.sh
#
# Ce script lance :
#   1. Redis (si pas déjà lancé)
#   2. Celery worker
#   3. Flask app
#
# Tous les logs sont dans /tmp/sci-diligence-webapp/
#

set -e

echo "========================================="
echo "  Starting Scholarmap Webapp (Phase 2)"
echo "========================================="
echo ""

# Créer le dossier pour les logs
LOGS_DIR="/tmp/sci-diligence-webapp"
mkdir -p "$LOGS_DIR"

# Vérifier qu'on est dans le bon dossier
if [ ! -f "webapp/app.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    echo "   Usage: ./webapp/start_all.sh"
    exit 1
fi

# Vérifier que l'environnement virtuel est activé
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: Virtual environment not activated"
    echo "   Activating .venv..."
    source .venv/bin/activate || {
        echo "❌ Error: Could not activate virtual environment"
        echo "   Please run: source .venv/bin/activate"
        exit 1
    }
fi

# Fonction pour vérifier si un processus tourne
is_running() {
    pgrep -f "$1" > /dev/null 2>&1
}

# 1. Vérifier/Lancer Redis
echo "📦 Checking Redis..."
if is_running "redis-server"; then
    echo "  ✅ Redis is already running"
else
    echo "  🚀 Starting Redis..."
    redis-server > "$LOGS_DIR/redis.log" 2>&1 &
    sleep 2

    # Vérifier que Redis a démarré
    if redis-cli ping > /dev/null 2>&1; then
        echo "  ✅ Redis started successfully"
    else
        echo "  ❌ Failed to start Redis"
        echo "     Please install Redis: brew install redis"
        exit 1
    fi
fi

# 2. Lancer Celery Worker
echo ""
echo "🔧 Starting Celery worker..."
cd webapp
celery -A services.celery_app worker --loglevel=info > "$LOGS_DIR/celery.log" 2>&1 &
CELERY_PID=$!
cd ..

sleep 3
if ps -p $CELERY_PID > /dev/null; then
    echo "  ✅ Celery worker started (PID: $CELERY_PID)"
else
    echo "  ❌ Failed to start Celery worker"
    echo "     Check logs: cat $LOGS_DIR/celery.log"
    exit 1
fi

# 3. Lancer Flask App
echo ""
echo "🌐 Starting Flask app..."
python3 webapp/app.py > "$LOGS_DIR/flask.log" 2>&1 &
FLASK_PID=$!

sleep 3
if ps -p $FLASK_PID > /dev/null; then
    echo "  ✅ Flask app started (PID: $FLASK_PID)"
else
    echo "  ❌ Failed to start Flask app"
    echo "     Check logs: cat $LOGS_DIR/flask.log"
    kill $CELERY_PID 2>/dev/null
    exit 1
fi

echo ""
echo "========================================="
echo "  ✅ All services started successfully!"
echo "========================================="
echo ""
echo "📍 Access points:"
echo "   - Webapp:  http://localhost:5001"
echo "   - Redis:   localhost:6379"
echo ""
echo "📝 Logs directory:"
echo "   $LOGS_DIR"
echo ""
echo "📊 Monitor logs:"
echo "   tail -f $LOGS_DIR/flask.log"
echo "   tail -f $LOGS_DIR/celery.log"
echo ""
echo "🛑 Stop all services:"
echo "   kill $FLASK_PID $CELERY_PID"
echo "   # or: pkill -f 'flask|celery|redis-server'"
echo ""
echo "💡 Tips:"
echo "   - Open http://localhost:5001 in your browser"
echo "   - Check Celery logs to see task progress"
echo "   - Use Ctrl+C in this terminal won't stop services (they run in background)"
echo ""

# Sauvegarder les PIDs pour pouvoir les arrêter facilement
echo "$FLASK_PID" > "$LOGS_DIR/flask.pid"
echo "$CELERY_PID" > "$LOGS_DIR/celery.pid"

echo "✅ Ready for testing! 🚀"
echo ""
