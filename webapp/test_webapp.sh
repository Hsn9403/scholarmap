#!/bin/bash
#
# Script de test rapide pour la webapp Scholarmap
#
# Usage:
#   ./webapp/test_webapp.sh
#

set -e

echo "========================================="
echo "  Testing Scholarmap Webapp"
echo "========================================="
echo ""

# Configuration
PORT=${FLASK_PORT:-5001}
BASE_URL="http://localhost:${PORT}"

# Fonction pour tester un endpoint
test_endpoint() {
    local name=$1
    local url=$2
    local method=${3:-GET}

    echo -n "Testing ${name}... "

    if [ "$method" = "POST" ]; then
        status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${url}" -d "researcher_name=Test User")
    else
        status=$(curl -s -o /dev/null -w "%{http_code}" "${url}")
    fi

    if [ "$status" = "200" ]; then
        echo "✅ OK (HTTP $status)"
    else
        echo "❌ FAILED (HTTP $status)"
        return 1
    fi
}

# Vérifier que l'app tourne
echo "Checking if webapp is running on port ${PORT}..."
if ! curl -s "${BASE_URL}" > /dev/null 2>&1; then
    echo "❌ Webapp is not running!"
    echo "   Please start it first: python webapp/app.py"
    exit 1
fi
echo "✅ Webapp is running"
echo ""

# Tests
echo "Running tests..."
echo ""

test_endpoint "Landing page      (GET /)" "${BASE_URL}/"
test_endpoint "Analyze endpoint  (POST /analyze)" "${BASE_URL}/analyze" POST
test_endpoint "API status        (GET /api/status/test)" "${BASE_URL}/api/status/test"
test_endpoint "History page      (GET /history)" "${BASE_URL}/history"

echo ""
echo "========================================="
echo "  All tests passed! ✅"
echo "========================================="
echo ""
echo "Open your browser at: ${BASE_URL}"
echo ""
