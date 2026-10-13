"""
Scholarmap — API Flask.

Le parcours public tient en quatre appels, sans compte :
    POST /api/analyze/resolve   nom → profils OpenAlex candidats (ou rapport déjà en base)
    POST /api/analyze/start     profil choisi → lance le pipeline en arrière-plan
    GET  /api/status/<task_id>  progression, pour la page de chargement
    GET  /api/report/<name>     rapport + URL du graphe filtrable (/graphs/db/<slug>)

Le frontend Next.js (../frontend) proxifie ces routes ; Flask ne sert pas de HTML
hormis les graphes pyvis.

Pour lancer l'application :
    python webapp/app.py
"""
import sys
import os
import json
import threading
import time
import uuid
from pathlib import Path

# Ajouter le dossier webapp ET la racine du projet au PYTHONPATH
webapp_dir = Path(__file__).parent
project_root = webapp_dir.parent
sys.path.insert(0, str(webapp_dir))
sys.path.insert(0, str(project_root))

from flask import Flask, request, jsonify, session
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import get_config
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
app.config.from_object(get_config())
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV', 'production') != 'development'

# Pas de CORS : le frontend passe par son proxy (même origine). L'ouvrir laisserait
# n'importe quel site lancer des analyses depuis le navigateur de ses visiteurs.
Compress(app)

# Derrière le proxy Next.js (et éventuellement nginx), l'IP du client est dans
# X-Forwarded-For. Sans ça, le rate limit verrait une seule IP pour tout le monde.
# Ne faire confiance qu'au nombre de proxys réellement présents, sinon l'en-tête
# est falsifiable — et ne jamais exposer le port Flask directement.
_proxy_hops = int(os.getenv('TRUSTED_PROXY_HOPS', '1'))
if _proxy_hops > 0:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_proxy_hops)

# Sans compte, le rate limiting par IP est la seule protection des clés API :
# une analyse coûte des dizaines d'appels SerpAPI.
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=os.getenv('REDIS_URL', 'memory://'),
    default_limits=[],
)
ANALYSIS_RATE_LIMIT = os.getenv('ANALYSIS_RATE_LIMIT', '10 per hour')
MAX_NAME_LENGTH = 200

from services.error_tracking import capture_exception

# Cache for similar-researchers endpoint (borné : la clé vient de la requête)
_SIMILAR_CACHE: dict = {}
_SIMILAR_CACHE_MAX = 500

# Les graphes embarquent des chaînes externes (titres, noms d'entreprises, sponsors)
# insérées en HTML. Le sandbox CSP les fait tourner dans une origine opaque, même
# ouverts hors iframe : un titre piégé ne peut rien atteindre du site.
_GRAPH_HEADERS = {
    'Content-Security-Policy': 'sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-modals',
    'X-Content-Type-Options': 'nosniff',
}


@app.after_request
def _security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return response

# ── i18n ──────────────────────────────────────────────────────────────────────
_TRANSLATIONS: dict = {}
_TRANSLATIONS_DIR = Path(__file__).parent / 'translations'
for _lang in ('fr', 'en'):
    with open(_TRANSLATIONS_DIR / f'{_lang}.json', encoding='utf-8') as _f:
        _TRANSLATIONS[_lang] = json.load(_f)


@app.route('/api/i18n')
def api_i18n():
    """
    Dictionnaire de traduction de la langue courante, pour le front React.

    Réponse: {lang, translations}
    """
    lang = session.get('lang', 'fr')
    # Le français sert de repli pour les clés absentes d'une autre langue
    merged = {**_TRANSLATIONS['fr'], **_TRANSLATIONS.get(lang, {})}
    return jsonify({'lang': lang, 'translations': merged})


@app.route('/api/i18n/lang', methods=['POST'])
def api_set_lang():
    """Change la langue de la session."""
    data = request.get_json(silent=True) or {}
    lang = (data.get('lang') or '').strip()
    if lang not in ('fr', 'en'):
        return jsonify({'error': 'Unsupported language'}), 400
    session['lang'] = lang
    return jsonify({'lang': lang})
# ──────────────────────────────────────────────────────────────────────────────


@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static', 'images'), 'favicon.ico', mimetype='image/x-icon')


# =============================================
# HELPERS
# =============================================

def _patch_graph_html(html: str) -> str:
    """Applique les patches nécessaires sur le HTML d'un graphe pyvis avant de le servir."""
    import re
    from pathlib import Path

    # Patch 0 : inliner lib/bindings/utils.js (chemin relatif invalide une fois servi par Flask)
    if 'src="lib/bindings/utils.js"' in html:
        utils_path = Path(__file__).parent / 'lib' / 'bindings' / 'utils.js'
        try:
            utils_content = utils_path.read_text(encoding='utf-8')
            html = html.replace(
                '<script src="lib/bindings/utils.js"></script>',
                f'<script>{utils_content}</script>'
            )
        except Exception:
            pass

    # Patch 1 : guard contre nodeData[0] undefined (crash sur les arêtes)
    html = re.sub(
        r'(var nodeData = nodes\.get\(\[nodeId\]\);)',
        r'\1\n                          if (!nodeData || !nodeData[0]) return;',
        html,
        count=1
    )
    html = html.replace(
        "popup.className = 'popup';",
        "popup.className = 'popup'; popup.style.pointerEvents = 'none';"
    )
    # Patch 2 : window.open → helper iframe-safe
    if 'window.open(' in html and 'function openUrl' not in html:
        patch = 'function openUrl(u){window.parent.postMessage({type:"openUrl",url:u},"*");}\n'
        html = html.replace(
            "window.open(nodeData.patents_url, '_blank')", 'openUrl(nodeData.patents_url)'
        ).replace(
            "window.open(nodeData.scholar_url, '_blank')", 'openUrl(nodeData.scholar_url)'
        ).replace('</script>', patch + '</script>', 1)

    # Patch 3 : indicateur "↓ défiler" sur le panneau CONNEXION
    # Un seul MutationObserver gère ajout ET suppression dans le bon ordre
    scrollbar_patch = (
        '<script>'
        '(function(){'
        'var obs=new MutationObserver(function(ms){'
        'ms.forEach(function(m){'
        # Suppression du panel → enlève l'indicateur
        'm.removedNodes.forEach(function(n){'
        'if(n.nodeType===1&&n.id==="paths-info-panel"){'
        'var old=document.getElementById("connexion-scroll-indicator");'
        'if(old)old.remove();'
        '}'
        '});'
        # Ajout du panel → crée l'indicateur ↓ défiler
        'm.addedNodes.forEach(function(n){'
        'if(n.nodeType===1&&n.id==="paths-info-panel"){'
        'var ind=document.createElement("div");'
        'ind.id="connexion-scroll-indicator";'
        'ind.style.cssText="position:fixed;bottom:20px;left:20px;height:52px;background:linear-gradient(to bottom,transparent,rgba(255,255,255,0.97));border-radius:0 0 10px 10px;z-index:10001;pointer-events:none;display:flex;align-items:flex-end;justify-content:center;padding-bottom:8px;opacity:0;transition:opacity 0.2s;";'
        'ind.innerHTML=\'<span style="font-size:11px;color:#64748B;background:rgba(255,255,255,0.9);border:1px solid #E2E8F0;border-radius:10px;padding:2px 10px;">\u2193 d\u00e9filer</span>\';'
        'document.body.appendChild(ind);'
        'function upd(){'
        'ind.style.width=n.offsetWidth+"px";'
        'var hasMore=n.scrollHeight>n.clientHeight+5;'
        'var atBot=n.scrollTop+n.clientHeight>=n.scrollHeight-5;'
        'ind.style.opacity=(hasMore&&!atBot)?"1":"0";'
        '}'
        'n.addEventListener("scroll",upd);'
        'setTimeout(upd,60);'
        '}'
        '});'
        '});'
        '});'
        'obs.observe(document.body,{childList:true,subtree:false});'
        '})();'
        '</script>'
    )
    if '</head>' in html:
        html = html.replace('</head>', scrollbar_patch + '</head>', 1)
    elif '</body>' in html:
        html = html.replace('</body>', scrollbar_patch + '</body>', 1)

    # Patch 4 : intégration visuelle transparente — supprime l'effet "boîte HTML"
    integration_css = (
        '<style>'
        'html,body{margin:0!important;background:transparent!important;overflow:hidden!important;}'
        '.card{border:none!important;background:transparent!important;margin:0!important;padding:0!important;box-shadow:none!important;}'
        '.card-body{padding:0!important;}'
        '#mynetwork{border:none!important;height:100vh!important;}'
        '</style>'
    )
    if '</head>' in html:
        html = html.replace('</head>', integration_css + '</head>', 1)
    elif '</body>' in html:
        html = html.replace('</body>', integration_css + '</body>', 1)

    return html


# =============================================
# ANALYSE : nom → candidats → pipeline
# =============================================

def _lookup_existing_analysis(researcher_name: str, scholar_id=None, openalex_id=None):
    """
    Look up a researcher already present in the database.

    Args:
        researcher_name: Name to look up.
        scholar_id: Scholar ID supplied by the caller, if any.
        openalex_id: OpenAlex ID supplied by the caller, if any.

    Returns:
        Tuple of (existing_data, scholar_id, openalex_id). existing_data is None
        when the researcher is unknown. When the caller supplied no IDs, they are
        recovered from the DB record so a forced re-analysis can route the pipeline.
    """
    from services.db_service import DatabaseService

    with DatabaseService() as db:
        already_analyzed = db.has_search_history(researcher_name)
        existing_scientist = db.get_scientist_by_name(researcher_name)

    if not already_analyzed and existing_scientist is None:
        return None, scholar_id, openalex_id

    # If IDs weren't provided by the caller, recover them from the DB record
    if existing_scientist and not scholar_id and not openalex_id:
        db_scholar_id = existing_scientist.scholar_id or ""
        db_scholar_url = existing_scientist.scholar_url or ""
        # OpenAlex IDs can be stored in either column — detect by URL pattern
        if "openalex.org" in db_scholar_url:
            openalex_id, scholar_id = db_scholar_url, None
        elif "openalex.org" in db_scholar_id:
            openalex_id, scholar_id = db_scholar_id, None
        else:
            scholar_id, openalex_id = (db_scholar_id or None), None
        logger.info(f"Recovered from DB — scholar_id={scholar_id}, openalex_id={openalex_id}")

    existing_data = {
        'name': existing_scientist.name if existing_scientist else researcher_name,
        'affiliation': existing_scientist.affiliation if existing_scientist else None,
        'h_index': existing_scientist.h_index if existing_scientist else None,
        'created_at': (
            existing_scientist.created_at.strftime('%Y-%m-%d %H:%M')
            if existing_scientist and existing_scientist.created_at else None
        ),
    }
    return existing_data, scholar_id, openalex_id


def _search_openalex_candidates(researcher_name: str):
    """
    Search OpenAlex for up to 5 author profiles matching a name.

    Args:
        researcher_name: Name to search for.

    Returns:
        Tuple of (candidates, error). error is 'maintenance' when the OpenAlex API
        is unavailable, None otherwise.
    """
    from src.pathfinding.openalex_client import OpenAlexClient
    from src.exceptions import APIError

    candidates = []
    try:
        oa_client = OpenAlexClient()
        raw = oa_client._make_request('/authors', {
            'filter': f'display_name.search:{researcher_name}',
            'per-page': 5,
        })
        for author in raw.get('results', []):
            all_affils = [
                a.get('institution', {}).get('display_name', '')
                for a in author.get('affiliations', [])
                if a.get('institution', {}).get('display_name')
            ]
            candidates.append({
                'openalex_id': author.get('id', ''),
                'name': author.get('display_name', ''),
                'works_count': author.get('works_count', 0),
                'cited_by_count': author.get('cited_by_count', 0),
                'affiliations': all_affils[:2],   # affichées sur la carte
                'all_affiliations': all_affils,   # utilisées pour le filtre
            })
    except APIError as oa_e:
        # Distinguish a maintenance window from a plain miss
        if "unavailable" in str(oa_e).lower() or "timeout" in str(oa_e).lower():
            logger.error(f"OpenAlex maintenance: {oa_e}")
            return candidates, "maintenance"
        logger.warning(f"OpenAlex search failed for '{researcher_name}': {oa_e}")
    except Exception as oa_e:
        logger.warning(f"OpenAlex search failed for '{researcher_name}': {oa_e}")

    return candidates, None


def _launch_analysis(researcher_name: str, scholar_id=None, openalex_id=None, force_new: bool = False) -> str:
    """
    Start the discovery pipeline in the background.

    Args:
        researcher_name: Canonical researcher name.
        scholar_id: Optional Scholar ID to pin the profile.
        openalex_id: Optional OpenAlex ID to pin the profile.
        force_new: Whether this run overrides an existing report (analytics only).

    Returns:
        The task_id to poll on /api/status/<task_id>.
    """
    logger.info(f"Starting new analysis for: {researcher_name} (force_new={force_new})")

    # Sans compte, on ne sait pas si c'est une première visite : les tips restent affichés
    _is_onboarding = True

    if app.config.get('USE_CELERY', False):
        # Mode production : Celery asynchrone
        from services.tasks import analyze_researcher_task

        task = analyze_researcher_task.delay(
            researcher_name=researcher_name,
            scholar_id=scholar_id,
            max_coauthors=5
        )
        logger.info(f"Task created (Celery): {task.id}")
        _init_task_info(task.id, researcher_name, bool(openalex_id), _is_onboarding, True)
        return task.id

    # Mode thread réel : vrai pipeline en background
    task_id = str(uuid.uuid4())
    _init_task_info(task_id, researcher_name, bool(openalex_id), _is_onboarding, False)

    t = threading.Thread(
        target=_run_pipeline_thread,
        args=(task_id, researcher_name, scholar_id, openalex_id),
        daemon=True
    )
    t.start()
    logger.info(f"Pipeline thread started for {researcher_name} (task_id={task_id})")
    return task_id


@app.route('/api/analyze/resolve', methods=['POST'])
@limiter.limit(lambda: os.getenv('RESOLVE_RATE_LIMIT', '60 per minute'))
def api_analyze_resolve():
    """
    Résout ce qu'il faut faire d'un nom de chercheur, sans rien lancer.

    Body JSON: {researcher_name, force_new?}
    Réponse (union discriminée sur `action`) :
      - {action: 'reuse', researcher_name, existing, scholar_id, openalex_id}
      - {action: 'disambiguate', researcher_name, candidates}
      - {action: 'error', error}
    """
    data = request.get_json(silent=True) or {}
    researcher_name = (data.get('researcher_name') or '').strip()
    force_new = bool(data.get('force_new'))

    if not researcher_name:
        return jsonify({'action': 'error', 'error': 'Missing researcher_name'}), 400
    if len(researcher_name) > MAX_NAME_LENGTH:
        return jsonify({'action': 'error', 'error': 'Name too long'}), 400

    try:
        # ── Rapport déjà en base : proposer la réutilisation ──
        if not force_new:
            existing_data, scholar_id, openalex_id = _lookup_existing_analysis(researcher_name)
            if existing_data:
                return jsonify({
                    'action': 'reuse',
                    'researcher_name': researcher_name,
                    'existing': existing_data,
                    'scholar_id': scholar_id,
                    'openalex_id': openalex_id,
                })

        # ── Sinon : désambiguisation OpenAlex ──
        candidates, oa_error = _search_openalex_candidates(researcher_name)
        if candidates:
            return jsonify({
                'action': 'disambiguate',
                'researcher_name': researcher_name,
                'candidates': candidates,
            })

        if oa_error == 'maintenance':
            error_msg = "L'API OpenAlex est en maintenance. Réessayez dans quelques minutes."
        else:
            error_msg = f'Aucun profil trouvé pour "{researcher_name}" sur OpenAlex. Vérifiez l\'orthographe.'
        return jsonify({'action': 'error', 'error': error_msg})

    except Exception as e:
        logger.error(f"Failed to resolve analysis: {e}", exc_info=True)
        capture_exception(e, route='/api/analyze/resolve', researcher=researcher_name)
        return jsonify({'action': 'error', 'error': 'Internal error'}), 500


@app.route('/api/analyze/start', methods=['POST'])
@limiter.limit(lambda: ANALYSIS_RATE_LIMIT)
def api_analyze_start():
    """
    Lance le pipeline pour un profil désambiguïsé.

    Body JSON: {researcher_name, openalex_id?, scholar_id?, force_new?}
    Réponse: {task_id}
    """
    data = request.get_json(silent=True) or {}
    researcher_name = (data.get('researcher_name') or '').strip()
    openalex_id = data.get('openalex_id') or None
    scholar_id = data.get('scholar_id') or None
    force_new = bool(data.get('force_new'))

    if not researcher_name:
        return jsonify({'error': 'Missing researcher_name'}), 400
    if len(researcher_name) > MAX_NAME_LENGTH:
        return jsonify({'error': 'Name too long'}), 400

    try:
        task_id = _launch_analysis(researcher_name, scholar_id, openalex_id, force_new)
        return jsonify({'task_id': task_id, 'researcher_name': researcher_name})
    except Exception as e:
        logger.error(f"Failed to start analysis: {e}", exc_info=True)
        capture_exception(e, route='/api/analyze/start', researcher=researcher_name)
        return jsonify({'error': 'Internal error'}), 500


@app.route('/api/analyze/task/<task_id>')
def api_analyze_task(task_id):
    """Métadonnées d'une tâche (nom du chercheur, onboarding) pour la page de chargement."""
    task_data = _get_task_status(task_id)
    if not task_data or not task_data.get('researcher_name'):
        return jsonify({'error': 'Task not found or expired'}), 404

    return jsonify({
        'task_id': task_id,
        'researcher_name': task_data.get('researcher_name', ''),
        'is_openalex': bool(task_data.get('is_openalex', False)),
        'is_onboarding': bool(task_data.get('is_onboarding', False)),
        'use_celery': bool(task_data.get('use_celery', False)),
    })


# =============================================
# RAPPORT
# =============================================

def _build_report_data(researcher_name: str) -> dict:
    """
    Assemble les données de rapport d'un chercheur depuis les sources disponibles.

    Les sources sont essayées par ordre de priorité : JSON pré-généré, DB, Excel
    généré par la pipeline, puis un squelette vide. Les métriques numériques sont
    toujours reprises de l'Excel quand il existe (la DB peut être obsolète).

    Args:
        researcher_name: Nom du chercheur.

    Returns:
        Le dict produit par format_report_data (researcher, coauthors,
        potential_buyers, graph_url, excel_url, summary).
    """
    from services.report_service import (
        format_report_data,
        load_from_pregenerated_json,
        load_from_excel
    )
    from services.db_service import get_scientist_from_db

    # Priorité 1 : Charger depuis JSON pré-généré (pour démo sans DB)
    analysis_result = load_from_pregenerated_json(researcher_name)

    if analysis_result:
        logger.info(f"Using pre-generated JSON data for: {researcher_name}")
    else:
        # Priorité 2 : Essayer la DB (si disponible)
        try:
            analysis_result = get_scientist_from_db(researcher_name)
            if analysis_result:
                logger.info(f"Using DB data for: {researcher_name}")
        except Exception as db_error:
            logger.warning(f"DB not available: {db_error}")
            analysis_result = None

    # Priorité 3 : Charger depuis l'Excel généré par la pipeline (données réelles)
    excel_result = load_from_excel(researcher_name)
    if not analysis_result:
        analysis_result = excel_result
        if analysis_result:
            logger.info(f"Using Excel report data for: {researcher_name}")

    # Supplément depuis Excel : les métriques numériques (h_index, patents_count,
    # recent_publications) sont toujours écrasées par l'Excel quand il existe,
    # car l'Excel est régénéré à chaque analyse depuis les vraies données OpenAlex/Patents.
    if analysis_result and excel_result:
        r = analysis_result.setdefault('researcher', {})
        r_xl = excel_result.get('researcher', {})
        for field in ('h_index', 'patents_count'):
            if r_xl.get(field):
                r[field] = r_xl[field]
        # recent_publications est calculé depuis le graphe HTML (pas depuis l'Excel).
        # La valeur 0 est valide (pas de pub récente) — utiliser is not None.
        recent_xl = r_xl.get('recent_publications')
        if recent_xl is not None:
            r['recent_publications'] = recent_xl
        logger.info(
            f"Metrics overridden from Excel — "
            f"h_index={r_xl.get('h_index')} "
            f"patents={r_xl.get('patents_count')} "
            f"recent_pubs={r_xl.get('recent_publications')}"
        )

    # Priorité 4 : données minimales (pas de mock) si rien trouvé
    if not analysis_result:
        logger.info(f"No data found for: {researcher_name}, using empty result")
        analysis_result = {
            'researcher': {'name': researcher_name},
            'coauthors': [],
            'corporate_connections': [],
        }

    return format_report_data(analysis_result)


@app.route('/api/report/<path:researcher_name>')
def api_report(researcher_name):
    """
    Données du rapport en JSON pour le front React.

    Réponse: {researcher, graph_url, excel_url, coauthors, potential_buyers, summary}
    """
    try:
        return jsonify(_build_report_data(researcher_name))
    except Exception as e:
        logger.error(f"Error building report data: {e}", exc_info=True)
        capture_exception(e, route='/api/report', researcher=researcher_name)
        return jsonify({'error': 'Internal error'}), 500


@app.route('/api/coauthor/<path:coauthor_name>')
def api_coauthor(coauthor_name):
    """
    Profil d'un co-auteur en JSON pour le front React.

    Query params: seed — chercheur de départ, pour compter les co-publications.
    """
    from services.coauthor_service import get_coauthor_profile

    seed_researcher = request.args.get('seed')
    try:
        profile = get_coauthor_profile(coauthor_name, seed_researcher)
        if not profile:
            return jsonify({'error': f'Profil introuvable : {coauthor_name}'}), 404
        return jsonify({'coauthor': profile, 'seed_researcher': seed_researcher})
    except Exception as e:
        logger.error(f"Error getting coauthor profile: {e}", exc_info=True)
        capture_exception(e, route='/api/coauthor', coauthor=coauthor_name)
        return jsonify({'error': 'Internal error'}), 500


@app.route('/graphs/db/<normalized_name>')
def serve_graph_from_db(normalized_name):
    """Servir le graphe HTML depuis la DB (persistant d'un déploiement à l'autre)."""
    from flask import Response
    from src.database.database import SessionLocal
    from src.database.models import Scientist

    db = SessionLocal()
    try:
        html = db.query(Scientist.graph_html).filter_by(normalized_name=normalized_name).scalar()
        if not html:
            logger.warning(f"Graph not found in DB for: {normalized_name}")
            return "Graph not found", 404
    finally:
        db.close()

    html = _patch_graph_html(html)
    return Response(html, mimetype='text/html', headers=_GRAPH_HEADERS)


@app.route('/graphs/<filename>')
def serve_graph(filename):
    """Servir un fichier de graphe HTML depuis le filesystem (fallback local/dev)."""
    from flask import Response

    # Route publique : seul un .html posé à la racine du projet est servable,
    # sinon /graphs/.env ou /graphs/../… exposerait n'importe quel fichier.
    filepath = (project_root / filename).resolve()
    if (
        filepath.parent != project_root.resolve()
        or filepath.suffix.lower() != '.html'
        or not filepath.is_file()
    ):
        logger.error(f"Graph file not found: {filename}")
        return "Graph not found", 404

    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    return Response(_patch_graph_html(html), mimetype='text/html', headers=_GRAPH_HEADERS)


# =============================================
# API ENDPOINTS (pour HTMX et futures intégrations)
# =============================================

# ── Helpers de statut de tâches (DB-backed, multi-process safe) ──────────────

# Stockage du statut des tâches via fichiers /tmp.
# Fonctionne quel que soit le nombre de workers/threads/processus sur la même instance.
import json as _json

_TASK_DIR = '/tmp/sci_diligence_tasks'


def _task_file(task_id: str) -> str:
    os.makedirs(_TASK_DIR, exist_ok=True)
    return os.path.join(_TASK_DIR, f'{task_id}.json')


def _init_task_info(task_id: str, researcher_name: str, is_openalex: bool, is_onboarding: bool, use_celery: bool):
    """Initialize task info (called once when task is created)."""
    try:
        path = _task_file(task_id)
        payload = {
            'researcher_name': researcher_name,
            'is_openalex': is_openalex,
            'is_onboarding': is_onboarding,
            'use_celery': use_celery,
            'status': 'processing',
            'progress': 0,
            'message': '',
            'started_at': time.time(),
            'updated_at': time.time(),
        }
        with open(path, 'w') as f:
            _json.dump(payload, f)
        logger.info(f"task {task_id}: initialized")
    except Exception as e:
        logger.error(f"_init_task_info error: {e}")


def _set_task_status(task_id: str, status: str, progress: int, message: str = ''):
    try:
        path = _task_file(task_id)
        # Preserve task info across updates
        data = {}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = _json.load(f)
            except Exception:
                pass
        # Update only status-related fields
        data['status'] = status
        data['progress'] = progress
        data['message'] = message or ''
        data['updated_at'] = time.time()
        # Ensure started_at exists
        if 'started_at' not in data:
            data['started_at'] = time.time()
        with open(path, 'w') as f:
            _json.dump(data, f)
        logger.info(f"task {task_id}: {status} {progress}%")
    except Exception as e:
        logger.error(f"_set_task_status error: {e}")


def _get_task_status(task_id: str):
    path = _task_file(task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return _json.load(f)
    except Exception as e:
        logger.error(f"_get_task_status error: {e}")
        return None


def _delete_task_status(task_id: str):
    try:
        os.unlink(_task_file(task_id))
    except Exception:
        pass


def _cancel_task(task_id: str):
    """Mark a task as cancelled in its status file."""
    try:
        path = _task_file(task_id)
        data = {}
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = _json.load(f)
            except Exception:
                pass
        data['cancelled'] = True
        data['status'] = 'cancelled'
        data['updated_at'] = time.time()
        with open(path, 'w') as f:
            _json.dump(data, f)
        logger.info(f"task {task_id}: cancelled by user")
    except Exception as e:
        logger.error(f"_cancel_task error: {e}")


def _is_task_cancelled(task_id: str) -> bool:
    """Check if a task has been cancelled."""
    try:
        path = _task_file(task_id)
        if not os.path.exists(path):
            return False
        with open(path) as f:
            return _json.load(f).get('cancelled', False)
    except Exception:
        return False


def _run_pipeline_thread(task_id: str, researcher_name: str, scholar_id: str = None, openalex_id: str = None):
    """
    Exécute le vrai pipeline d'analyse dans un thread background.

    Le scholar_id est fourni par /analyze (qui a déjà fait find_candidates).
    1. Lance build_ultra_complete_graph()
    2. Ajoute à search_history si succès
    """
    try:
        # Nettoyage RAM préventif — libère les restes des recherches précédentes
        import gc
        import tracemalloc
        gc.collect()
        tracemalloc.start()

        try:
            import psutil as _psutil
            _proc = _psutil.Process()
            _has_psutil = True
        except ImportError:
            _has_psutil = False

        def _ram_snapshot(label: str):
            """Log RAM snapshot : tracemalloc (Python) + RSS réel si psutil dispo."""
            current, peak = tracemalloc.get_traced_memory()
            if _has_psutil:
                rss = _proc.memory_info().rss / 1024 / 1024
                logger.info(
                    f"[RAM] {label} — "
                    f"py_current: {current/1024/1024:.1f} MB | py_peak: {peak/1024/1024:.1f} MB | "
                    f"rss: {rss:.1f} MB"
                )
            else:
                logger.info(
                    f"[RAM] {label} — "
                    f"py_current: {current/1024/1024:.1f} MB | py_peak: {peak/1024/1024:.1f} MB"
                )

        _ram_snapshot("pipeline start")

        # Charger le .env pour avoir les clés API
        try:
            from dotenv import load_dotenv
            load_dotenv(project_root / '.env')
        except ImportError:
            pass

        # S'assurer que scripts/ est dans sys.path (pour les imports internes de phase1)
        scripts_dir = str(project_root / 'scripts')
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        logger.info(f"[{task_id}] Starting pipeline for: {researcher_name} (scholar_id={scholar_id})")

        def _check_cancelled():
            if _is_task_cancelled(task_id):
                logger.info(f"[{task_id}] Pipeline cancelled by user — aborting")
                raise InterruptedError("task_cancelled")

        # ── Phase 1 : collecte des données (10% → 60%) ───────────────────
        import time as _time
        _t_phase1 = _time.time()
        _check_cancelled()
        _set_task_status(task_id, 'processing', 10, 'loading_msg_data_collection')
        try:
            from scripts.modules.phase1_data_collection import collect_all_data
            data = collect_all_data(
                researcher_name=researcher_name,
                max_publications=100,
                max_patents=10,
                max_coauthors_ct=30,
                max_coauthors_ts=50,
                min_amount_ts=0.0,
                use_db_only=False,
                scholar_id=scholar_id,
                openalex_id=openalex_id,
            )
        except Exception as _phase1_err:
            capture_exception(_phase1_err, route='pipeline', phase='1_data_collection', researcher=researcher_name, task_id=task_id)
            raise
        _phase1_duration = _time.time() - _t_phase1
        logger.info(f"⏱  Phase 1 total: {_phase1_duration:.1f}s")
        _ram_snapshot("après Phase 1")
        if _phase1_duration > 120:
            capture_exception(Exception(f"Phase 1 slow: {_phase1_duration:.0f}s"), route='pipeline', phase='1_slow', researcher=researcher_name, duration_s=round(_phase1_duration))

        # Fail fast si OpenAlex n'a rien retourné — évite un crash obscur en Phase 2/3
        if not data.get('scholar'):
            _err = Exception(f"Aucune publication trouvée pour « {researcher_name} » — le profil OpenAlex est peut-être temporairement indisponible.")
            capture_exception(_err, route='pipeline', phase='1_no_scholar_data', researcher=researcher_name, task_id=task_id, openalex_id=openalex_id)
            raise _err

        # Tracker les co-auteurs skippés après retries (CT + TS)
        ct_skipped = data.get('ct_skipped_coauthors') or []
        ts_skipped = data.get('ts_skipped_coauthors') or []
        if ct_skipped or ts_skipped:
            logger.warning(f"[{task_id}] ⚠ Skipped coauthors — CT: {ct_skipped}, TS: {ts_skipped}")

        # ── Phase 2 : sauvegarde en base de données (60% → 70%) ──────────
        _t_phase2 = _time.time()
        _check_cancelled()
        _set_task_status(task_id, 'processing', 60, 'loading_msg_db_save')
        try:
            from scripts.modules.phase2_database_storage import store_all_to_database
            store_all_to_database(researcher_name=researcher_name, data=data)
        except Exception as _phase2_err:
            capture_exception(_phase2_err, route='pipeline', phase='2_database_storage', researcher=researcher_name, task_id=task_id)
            raise
        logger.info(f"⏱  Phase 2 total: {_time.time() - _t_phase2:.1f}s")

        # Libérer les clés CT/TS — déjà stockées en DB, inutiles pour Phase 3
        for _key in ('clinical_trials_corporates', 'clinical_trials_links',
                     'transparence_sante_corporates', 'transparence_sante_declarations',
                     'open_payments_corporates', 'open_payments_records',
                     'ct_skipped_coauthors', 'ts_skipped_coauthors', 'op_skipped_coauthors'):
            data.pop(_key, None)
        gc.collect()
        _ram_snapshot("après Phase 2")

        # ── Phase 3 : génération du graphe (70% → 85%) ───────────────────
        _t_phase3 = _time.time()
        _check_cancelled()
        _set_task_status(task_id, 'processing', 70, 'loading_msg_graph_gen')

        # Heartbeat thread : phase 3 peut durer 60-120s sans mise à jour de statut
        # (SerpAPI calls, OpenAlex enrichment). Sans heartbeat, HEARTBEAT_TIMEOUT=75s
        # déclencherait un faux timeout. On rafraîchit le statut toutes les 30s.
        _p3_heartbeat_stop = threading.Event()
        def _p3_heartbeat():
            while not _p3_heartbeat_stop.wait(30):
                _set_task_status(task_id, 'processing', 70, 'loading_msg_graph_gen')
        _p3_heartbeat_thread = threading.Thread(target=_p3_heartbeat, daemon=True)
        _p3_heartbeat_thread.start()

        try:
            from scripts.modules.phase3_graph_generation import generate_complete_graph
            generate_complete_graph(
                researcher_name=researcher_name,
                scholar_data=data['scholar'],
                patents_data=data.get('patents'),
                enrich_persons=True,
                discover_coauthor_patents_api=True,
            )
        except Exception as _phase3_err:
            capture_exception(_phase3_err, route='pipeline', phase='3_graph_generation', researcher=researcher_name, task_id=task_id)
            raise
        finally:
            _p3_heartbeat_stop.set()
        _phase3_duration = _time.time() - _t_phase3
        logger.info(f"⏱  Phase 3 total: {_phase3_duration:.1f}s")
        _ram_snapshot("après Phase 3")
        if _phase3_duration > 60:
            capture_exception(Exception(f"Phase 3 slow: {_phase3_duration:.0f}s"), route='pipeline', phase='3_slow', researcher=researcher_name, duration_s=round(_phase3_duration))

        # ── Phase 4 : historique DB (85% → 100%) ─────────────────────────
        _set_task_status(task_id, 'processing', 95, 'loading_msg_finalizing')

        # Enregistrer dans search_history (rapide, avant la redirection)
        try:
            from services.db_service import DatabaseService
            with DatabaseService() as db:
                scientist = db.get_scientist_by_name(researcher_name)
                if scientist:
                    db.add_search_history(scientist.id)
                    logger.info(f"[{task_id}] Added to search history: {researcher_name}")
        except Exception as hist_err:
            logger.warning(f"[{task_id}] Could not add search history: {hist_err}")

        # Marquer comme terminé → l'utilisateur est redirigé vers le graphe
        # AVANT la génération Excel (qui continue en arrière-plan)
        _set_task_status(task_id, 'completed', 100, 'Analysis complete!')
        logger.info(f"[{task_id}] Pipeline completed for: {researcher_name}")

        # ── Phase 5 : Excel en arrière-plan ──────────────────────────────
        # L'utilisateur est déjà sur la page rapport ; le fichier apparaîtra
        # quelques secondes plus tard (polling JS côté client).
        try:
            from src.export.excel import ExcelExporter
            from src.models import PatentsData, PatentItem
            from src.helpers import slug
            from src.database.database import SessionLocal
            from src.database.models import Scientist, Patent as DBPatent

            db = SessionLocal()
            patents_list = []
            try:
                from sqlalchemy.orm import defer as _defer
                scientist_rec = db.query(Scientist).options(
                    _defer(Scientist.graph_html)
                ).filter(
                    (Scientist.name == researcher_name) |
                    (Scientist.normalized_name == slug(researcher_name))
                ).first()
                if scientist_rec:
                    for db_patent in db.query(DBPatent).join(DBPatent.inventors).filter(Scientist.id == scientist_rec.id).all():
                        claims_top3 = [c.strip() for c in (db_patent.claims_excerpt or "").split("\n\n") if c.strip()][:3]
                        if db_patent.inventors_json:
                            co_inventors = [inv if isinstance(inv, str) else inv.get("name", "") for inv in (db_patent.inventors_json if isinstance(db_patent.inventors_json, list) else [])]
                            co_inventors = [c for c in co_inventors if c.strip()]
                        else:
                            co_inventors = [inv.name for inv in db_patent.inventors]
                        citing_assignees = list({c.get("assignee", "").strip() for c in (db_patent.citing_patents_json or []) if isinstance(c, dict) and c.get("assignee", "").strip()})
                        cited_assignees = list({c.get("assignee", "").strip() for c in (db_patent.cited_patents_json or []) if isinstance(c, dict) and c.get("assignee", "").strip()})
                        patents_list.append(PatentItem(title=db_patent.title, link=db_patent.link or "", patent_id=db_patent.patent_id or "", current_assignee=db_patent.assignee, publication_date=str(db_patent.publication_date) if db_patent.publication_date else None, claims_top3=claims_top3, co_inventors=co_inventors, cited_assignees=cited_assignees, citing_assignees=citing_assignees))
            finally:
                db.close()

            patents_obj = PatentsData(top_patents=patents_list, patents_total=len(patents_list)) if patents_list else PatentsData(top_patents=data.get('patents', []), patents_total=len(data.get('patents', [])))
            excel_filename = f"{slug(researcher_name)}_report.xlsx"
            webapp_reports_dir = project_root / "webapp" / "static" / "reports"
            webapp_reports_dir.mkdir(parents=True, exist_ok=True)
            ExcelExporter().write(out_path=str(webapp_reports_dir / excel_filename), researcher_name=researcher_name, scholar=data['scholar'], patents=patents_obj)
            logger.info(f"[{task_id}] Excel report generated: {excel_filename}")

            # Sync h_index from Excel → DB (maintenant que l'Excel est prêt)
            try:
                from services.db_service import DatabaseService
                from services.report_service import load_from_excel
                with DatabaseService() as db:
                    scientist = db.get_scientist_by_name(researcher_name)
                    if scientist and not scientist.h_index:
                        excel_result = load_from_excel(researcher_name)
                        h_from_excel = (
                            excel_result.get('researcher', {}).get('h_index')
                            if excel_result else None
                        )
                        if h_from_excel:
                            scientist.h_index = h_from_excel
                            db.session.commit()
                            logger.info(
                                f"[{task_id}] Synced h_index={h_from_excel} to DB for: {researcher_name}"
                            )
            except Exception as h_sync_err:
                logger.warning(f"[{task_id}] h_index sync failed: {h_sync_err}")

        except Exception as excel_err:
            logger.warning(f"[{task_id}] Excel generation failed (non-blocking): {excel_err}")

    except InterruptedError:
        logger.info(f"[{task_id}] Pipeline aborted — task cancelled by user")
        _set_task_status(task_id, 'cancelled', 0, 'Recherche annulée.')
    except Exception as e:
        logger.error(f"[{task_id}] Pipeline error for {researcher_name}: {e}", exc_info=True)
        _oom_signals = ('MemoryError', 'cannot allocate', 'out of memory', 'Killed', 'OOM')
        _is_oom = isinstance(e, MemoryError) or any(s.lower() in str(e).lower() for s in _oom_signals)
        if _is_oom:
            capture_exception(e, route='pipeline', phase='OOM_concurrency', researcher=researcher_name, task_id=task_id)
            user_msg = 'loading_error_oom'
        else:
            capture_exception(e, route='pipeline', researcher=researcher_name, task_id=task_id)
            user_msg = str(e) if 'Aucune publication' in str(e) else f"Une erreur est survenue lors de l'analyse de « {researcher_name} ». Veuillez réessayer."
        _set_task_status(task_id, 'error', 0, user_msg)

    finally:
        # Libérer explicitement la mémoire — évite l'accumulation RAM sur recherches consécutives
        import gc
        try:
            del data
        except NameError:
            pass
        gc.collect()
        try:
            _ram_snapshot("pipeline end (avant GC final)")
            tracemalloc.stop()
        except Exception:
            pass


@app.route('/api/cancel/<task_id>', methods=['POST'])
def api_cancel_task(task_id):
    """Cancel a running pipeline task (called by loading page on navigate away)."""
    if _get_task_status(task_id) is None:
        return jsonify({'ok': False}), 404
    _cancel_task(task_id)
    return {'ok': True}


@app.route('/api/status/<task_id>')
def api_status(task_id):
    """
    Endpoint API pour vérifier le statut d'une tâche async.
    Utilisé par la page de chargement pour le polling.
    """
    try:
        if app.config.get('USE_CELERY', False):
            # Mode production : vrai Celery
            from services.tasks import analyze_researcher_task
            from celery.result import AsyncResult

            task = AsyncResult(task_id, app=analyze_researcher_task.app)

            if task.state == 'PENDING':
                response = {'status': 'pending', 'progress': 0, 'message': 'Waiting to start...'}
            elif task.state == 'PROGRESS':
                response = {
                    'status': 'processing',
                    'progress': task.info.get('progress', 0),
                    'message': task.info.get('message', 'Processing...'),
                    'step': task.info.get('step', 0),
                    'total_steps': task.info.get('total_steps', 4),
                    'data': task.info.get('data')
                }
            elif task.state == 'SUCCESS':
                response = {'status': 'completed', 'progress': 100, 'message': 'Analysis complete!', 'result': task.result}
            elif task.state == 'FAILURE':
                response = {'status': 'error', 'progress': 0, 'message': str(task.info)}
            else:
                response = {'status': task.state.lower(), 'progress': 0, 'message': f'Task state: {task.state}'}

        else:
            # Mode thread réel : lire le statut depuis PostgreSQL
            task_data = _get_task_status(task_id)

            if not task_data:
                return jsonify({'status': 'error', 'progress': 0, 'message': 'loading_error_maintenance'}), 404

            status = task_data['status']

            if status == 'completed':
                response = {'status': 'completed', 'progress': 100, 'message': 'Analysis complete!'}
                _delete_task_status(task_id)

            elif status == 'error':
                response = {'status': 'error', 'progress': 0, 'message': task_data.get('message', 'Analysis failed')}
                _delete_task_status(task_id)

            else:
                # Detect silent hang: task stuck in processing for too long
                started_at = task_data.get('started_at')
                updated_at = task_data.get('updated_at', started_at)
                now = time.time()
                total_timeout = app.config.get('ANALYSIS_TIMEOUT', 300)
                heartbeat_timeout = app.config.get('HEARTBEAT_TIMEOUT', 75)
                elapsed_total = int(now - started_at) if started_at else 0
                elapsed_since_update = int(now - updated_at) if updated_at else 0
                if (started_at and elapsed_total > total_timeout) or (updated_at and elapsed_since_update > heartbeat_timeout):
                    capture_exception(
                        Exception("Pipeline timeout — task stuck in processing"),
                        route='/api/status',
                        task_id=task_id,
                        progress=task_data.get('progress', 0),
                        last_message=task_data.get('message', ''),
                        elapsed_total_s=elapsed_total,
                        elapsed_since_update_s=elapsed_since_update,
                    )
                    _delete_task_status(task_id)
                    return jsonify({'status': 'error', 'progress': 0, 'message': 'loading_error_timeout'}), 200

                response = {
                    'status': 'processing',
                    'progress': task_data.get('progress', 0),
                    'message': task_data.get('message', 'loading_msg_data_collection'),
                }

        # Translate message key if it's a known i18n key
        _lang = session.get('lang', 'fr')
        _t_dict = _TRANSLATIONS.get(_lang, _TRANSLATIONS['fr'])
        _fb = _TRANSLATIONS['fr']
        msg = response.get('message', '')
        if msg in _t_dict or msg in _fb:
            response['message'] = _t_dict.get(msg, _fb.get(msg, msg))

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error getting task status: {e}", exc_info=True)
        return jsonify({'status': 'error', 'progress': 0, 'message': 'Internal error'}), 500


@app.route('/api/excel_ready/<path:researcher_name>')
def api_excel_ready(researcher_name):
    """
    Vérifie si le rapport Excel est disponible pour un chercheur.
    Utilisé par le polling JS de la page rapport.
    """
    from src.helpers import slug
    filename = f"{slug(researcher_name)}_report.xlsx"
    path = project_root / "webapp" / "static" / "reports" / filename
    return jsonify({"ready": path.exists(), "url": f"/static/reports/{filename}"})


@app.route('/api/similar-researchers')
@limiter.limit(lambda: os.getenv('SIMILAR_RATE_LIMIT', '30 per hour'))
def api_similar_researchers():
    """Retourne des chercheurs dans le même domaine — appelé en async depuis la loading page."""
    name = (request.args.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    if len(name) > 200:
        return jsonify({'error': 'name too long'}), 400

    # Cache simple en mémoire par nom
    cache_key = f"similar__{name.lower()}"
    cached = _SIMILAR_CACHE.get(cache_key)
    if cached:
        return jsonify(cached)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return jsonify({'researchers': []}), 200

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {"role": "system", "content": "You are a scientific research expert with deep knowledge of academic collaboration networks. Respond only with valid JSON."},
                {"role": "user", "content": (
                    f"List 6 real researchers who work on the exact same scientific specialty as \"{name}\" AND have very likely collaborated with them "
                    "(co-authored papers, same clinical trial, same consortium). "
                    "They must share both the same specialty AND a plausible collaboration history. "
                    "Do NOT list researchers who only share the broad field without a real collaboration link. "
                    "For each, give their full name and a short reason (3-6 words) for the collaboration (e.g. 'co-auteur essai phase III', 'même équipe CHU Lyon'). "
                    "Return ONLY a JSON object: {\"researchers\": [{\"name\": \"...\", \"field\": \"...\"}]}"
                )}
            ],
            max_completion_tokens=300,
            temperature=0.4,
            timeout=8
        )
        import json as _json
        content = resp.choices[0].message.content.strip()
        # Strip markdown code blocks if present (```json ... ```)
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        result = _json.loads(content)
        if len(_SIMILAR_CACHE) >= _SIMILAR_CACHE_MAX:
            _SIMILAR_CACHE.pop(next(iter(_SIMILAR_CACHE)))
        _SIMILAR_CACHE[cache_key] = result
        return jsonify(result)
    except Exception as e:
        logger.warning(f"similar-researchers API error: {e}", exc_info=True)
        return jsonify({'researchers': []}), 200


# =============================================
# ERROR HANDLERS
# =============================================

@app.errorhandler(429)
def too_many_requests(e):
    return jsonify({'error': "Trop d'analyses lancées depuis cette adresse. Réessayez plus tard."}), 429


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({'error': 'An error occurred. Please try again.'}), 500


# =============================================
# MAIN
# =============================================

if __name__ == '__main__':
    # Port configurable via variable d'environnement (5001 par défaut pour éviter AirPlay sur macOS)
    port = int(os.getenv('FLASK_PORT', 5001))

    logger.info("Starting Scholarmap API...")
    logger.info(f"Debug mode: {app.config['DEBUG']}")
    logger.info(f"Port: {port}")

    # 127.0.0.1 par défaut : en debug, Werkzeug expose une console Python interactive
    app.run(
        host=os.getenv('FLASK_HOST', '127.0.0.1'),
        port=port,
        debug=app.config['DEBUG']
    )
