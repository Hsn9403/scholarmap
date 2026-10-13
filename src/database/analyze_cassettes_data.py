#!/usr/bin/env python3
"""Analyze what Scholar data is available in cassettes."""
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.logger import logger


def analyze_cassettes():
    """Analyze Scholar author cassettes to see what data is available."""
    cassettes_dir = project_root / "src" / "api" / "cassettes"

    print('🔍 Données disponibles dans les cassettes Scholar author:')
    print('=' * 100)

    profiles = []

    for cassette_file in cassettes_dir.glob('*.json'):
        try:
            with open(cassette_file, 'r') as f:
                data = json.load(f)

            if data.get('request', {}).get('engine') != 'google_scholar_author':
                continue

            response = data.get('response', {})
            author = response.get('author', {})

            name = author.get('name')
            if not name:
                continue

            scholar_id = author.get('author_id')

            # Extraire H-index
            cited_by = response.get('cited_by', {})
            h_index = None
            if cited_by and isinstance(cited_by, dict):
                table = cited_by.get('table', [])
                if len(table) > 1:
                    h_index_entry = table[1]
                    h_data = h_index_entry.get('indice_h') or h_index_entry.get('h_index')
                    if h_data:
                        h_index = h_data.get('all')

            scholar_url = f'https://scholar.google.com/citations?user={scholar_id}' if scholar_id else None

            profiles.append({
                'name': name,
                'scholar_id': scholar_id,
                'h_index': h_index,
                'scholar_url': scholar_url,
                'cassette': cassette_file.name
            })

        except Exception as e:
            continue

    # Afficher les résultats
    print(f'Total profils Scholar trouvés: {len(profiles)}')
    print()

    for profile in sorted(profiles, key=lambda x: x['h_index'] or 0, reverse=True):
        scholar_id_str = profile['scholar_id'] or '✗ Manquant'
        h_index_str = str(profile['h_index']) if profile['h_index'] else '✗ Manquant'

        print(f'{profile["name"]:40s} | Scholar ID: {scholar_id_str:>20} | H-index: {h_index_str:>10}')

    print()
    print('📊 Statistiques:')
    with_scholar_id = sum(1 for p in profiles if p['scholar_id'])
    with_h_index = sum(1 for p in profiles if p['h_index'])
    with_both = sum(1 for p in profiles if p['scholar_id'] and p['h_index'])

    print(f'   Avec Scholar ID: {with_scholar_id}/{len(profiles)}')
    print(f'   Avec H-index: {with_h_index}/{len(profiles)}')
    print(f'   Avec les deux: {with_both}/{len(profiles)}')


if __name__ == '__main__':
    analyze_cassettes()
