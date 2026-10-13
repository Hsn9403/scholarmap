#!/bin/bash
#
# Script de lancement rapide pour la webapp Scholarmap
#
# Usage:
#   ./webapp/run.sh
#

set -e  # Exit on error

echo "========================================="
echo "  Starting Scholarmap Webapp"
echo "========================================="
echo ""

# Vérifier qu'on est dans le bon dossier
if [ ! -f "webapp/app.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    echo "   Usage: ./webapp/run.sh"
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

# Installer les dépendances si nécessaire
echo "📦 Installing dependencies..."
pip install -q -r webapp/requirements-webapp.txt

echo ""
echo "✅ Dependencies installed"
echo ""
echo "🚀 Starting Flask server..."
echo "   URL: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Lancer l'application
cd webapp && python app.py
