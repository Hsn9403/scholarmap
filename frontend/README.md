# Scholarmap — frontend Next.js

Interface publique de Scholarmap en Next.js 16 / React 19, sans compte. Flask (`../webapp`)
ne sert que l'API JSON, les fichiers statiques et les graphes pyvis. `next.config.ts`
proxifie ces routes vers `SCHOLARMAP_API_URL` (par défaut `http://localhost:5001`).

## Démarrer

```bash
# terminal 1 — API Flask (port 5001)
cd .. && python webapp/app.py

# terminal 2 — frontend
pnpm dev        # http://localhost:3000
```

## Stack

- Next.js 16 (App Router) + React 19, Turbopack
- Tailwind v4 + shadcn (`@base-ui/react`), lucide-react
- TanStack Query pour le cache serveur, zod pour valider chaque réponse d'API
- axios (`src/lib/fetcher.ts`) avec `withCredentials` — la langue est gardée dans la session Flask

## Écrans

| Écran | Route |
|---|---|
| Accueil / recherche | `/` |
| Rapport existant | `/confirm-reuse?name=` |
| Désambiguisation | `/disambiguation?name=` |
| Chargement pipeline | `/analyze/[taskId]` |
| Rapport + carte du réseau | `/report/[name]` (+ `?embed=1`) |
| Profil co-auteur | `/coauthor/[name]?seed=` |

## i18n

`webapp/translations/{fr,en}.json` est la **source unique**. Le front les récupère via
`GET /api/i18n` (langue de la session Flask, repli sur le français clé par clé) et les
expose par `useT()` :

```tsx
const t = useT();
<h2>{t("network_title")}</h2>
<p>{t("coauthor_copublications", { name: seed })}</p>   // {placeholders}
```

Ajouter une chaîne = ajouter la clé dans **les deux** fichiers. Une clé absente
s'affiche telle quelle, ce qui la rend visible immédiatement. Le sélecteur FR/EN du
header appelle `POST /api/i18n/lang` puis invalide tout le cache Query, pour que les
ressources rendues côté serveur (graphes, Excel) suivent la langue.

Vérifier la parité :

```bash
python3 -c "
import json
fr=json.load(open('../webapp/translations/fr.json')); en=json.load(open('../webapp/translations/en.json'))
print('écarts:', sorted(set(fr)^set(en)) or 'aucun')"
```

## Le graphe

Le graphe réseau **n'est pas du React** : c'est un HTML pyvis généré par le pipeline
Python, stocké en base et servi par Flask (`/graphs/db/<slug>`), affiché en iframe.
Les filtres (corporates, institutions, brevets, publications, co-auteurs) vivent dans
ce HTML. Il parle à la page par `postMessage` : `openUrl` ouvre un lien dans un onglet.
Voir le listener dans `app/report/[name]/page.tsx`.

## API consommée

- `POST /api/analyze/resolve` → `{action: 'reuse' | 'disambiguate' | 'error', …}`, ne lance rien
- `POST /api/analyze/start` → `{task_id}` (rate-limité par IP)
- `GET  /api/analyze/task/<task_id>` · `GET /api/status/<task_id>` · `POST /api/cancel/<task_id>`
- `GET  /api/report/<name>` · `GET /api/excel_ready/<name>`
- `GET  /api/coauthor/<name>?seed=`
- `GET  /api/similar-researchers?name=`
- `GET  /api/i18n` · `POST /api/i18n/lang`
