#!/bin/bash
# Script pour faire des requêtes rapides sur la base de données

DB_CMD="/opt/homebrew/opt/postgresql@16/bin/psql -U sci_diligence -d sci_diligence -q"

case "$1" in
  "dashboard")
    echo "📊 Dashboard complet"
    $DB_CMD << 'EOF'
SELECT 'Scientists' as entity, COUNT(*)::text as count FROM scientists
UNION ALL SELECT 'Publications', COUNT(*)::text FROM publications
UNION ALL SELECT 'Institutions', COUNT(*)::text FROM institution
UNION ALL SELECT 'API Calls', COUNT(*)::text FROM api_calls;
EOF
    ;;

  "search")
    if [ -z "$2" ]; then
      echo "Usage: ./query.sh search <nom>"
      exit 1
    fi
    echo "🔍 Recherche de '$2'..."
    $DB_CMD << EOF
SELECT name, scholar_id, LEFT(COALESCE(affiliation, 'N/A'), 40) as affiliation
FROM scientists
WHERE name ILIKE '%$2%'
ORDER BY name;
EOF
    ;;

  "pubs")
    if [ -z "$2" ]; then
      echo "Usage: ./query.sh pubs <nom scientifique>"
      exit 1
    fi
    echo "📚 Publications de '$2'..."
    $DB_CMD << EOF
SELECT
    LEFT(p.title, 70) as title,
    p.year,
    p.cited_by as citations
FROM publications p
JOIN publications_author pa ON p.id = pa.publication_id
JOIN scientists s ON pa.author_id = s.id
WHERE s.name ILIKE '%$2%'
ORDER BY p.cited_by DESC NULLS LAST;
EOF
    ;;

  "top")
    echo "🏆 Top 10 publications"
    $DB_CMD << 'EOF'
SELECT
    LEFT(title, 65) as title,
    year,
    cited_by
FROM publications
WHERE cited_by IS NOT NULL
ORDER BY cited_by DESC
LIMIT 10;
EOF
    ;;

  "institutions")
    echo "🏛️ Institutions"
    $DB_CMD << 'EOF'
SELECT
    LEFT(i.name, 55) as institution,
    COUNT(si.scientist_id) as scientists
FROM institution i
LEFT JOIN scientist_institution si ON i.id = si.institution_id
GROUP BY i.id, i.name
ORDER BY scientists DESC;
EOF
    ;;

  *)
    echo "Usage: ./query.sh [commande]"
    echo ""
    echo "Commandes disponibles:"
    echo "  dashboard           - Vue d'ensemble"
    echo "  search <nom>        - Chercher un scientifique"
    echo "  pubs <nom>          - Publications d'un scientifique"
    echo "  top                 - Top 10 publications citées"
    echo "  institutions        - Liste des institutions"
    echo ""
    echo "Exemples:"
    echo "  ./query.sh search alice"
    echo "  ./query.sh pubs philippe"
    echo "  ./query.sh top"
    ;;
esac
