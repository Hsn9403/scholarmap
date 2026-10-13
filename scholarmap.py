#!/usr/bin/env python3
"""
Scholarmap en ligne de commande.

    python scholarmap.py                    # demande un nom
    python scholarmap.py "Alice Nedelec"    # nom passé directement

Cherche le nom sur OpenAlex, propose les profils candidats, lance le pipeline
puis ouvre la carte du réseau (HTML filtrable) dans le navigateur.

Sans DATABASE_URL, les données vont dans un fichier SQLite local
(scholarmap.db) : rien à installer d'autre que les dépendances Python.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import threading
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "webapp"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# Avant tout import de src.database, qui lit DATABASE_URL à l'import
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'scholarmap.db'}")

OUTPUT_DIR = ROOT / "output"

from src import progress  # noqa: E402  (après le chargement de l'environnement)

_ANSI = re.compile(r"\033\[[0-9;]*m")


# ── Affichage ─────────────────────────────────────────────────────────────────

def _supports_color() -> bool:
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _style(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _supports_color() else text


def bold(text: str) -> str:
    return _style(text, "1")


def dim(text: str) -> str:
    return _style(text, "2")


def blue(text: str) -> str:
    return _style(text, "34")


def green(text: str) -> str:
    return _style(text, "32")


# Libellés des étapes signalées par le pipeline (src/progress.py)
STAGE_LABELS = {
    "graph_base": "assemblage du graphe",
    "persons_db": "fusion des homonymes",
    "patents_db": "brevets connus",
    "coauthors_openalex": "profils des co-auteurs (OpenAlex)",
    "institutions": "institutions",
    "coauthor_patents": "brevets des co-auteurs",
    "industry": "liens avec l'industrie",
    "render": "génération de la carte",
}
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Step:
    """
    One phase of the analysis, shown as a single live line in a terminal:
    spinner, current sub-step, a bar when the sub-step is countable, elapsed time.

    The line is redrawn by a background thread so it keeps moving during long
    network calls. Outside a terminal (pipe, CI) it falls back to plain lines.
    """

    def __init__(self, title: str):
        self.title = title
        self.stage: str | None = None
        self.done: int | None = None
        self.total: int | None = None
        self.live = sys.stdout.isatty()
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def __enter__(self) -> "Step":
        self.started = time.time()
        if self.live:
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()
        else:
            print(f"> {self.title}", flush=True)
        progress.set_listener(self.update)
        return self

    def update(self, stage: str, done: int | None = None, total: int | None = None) -> None:
        with self._lock:
            if stage != self.stage:
                # Un thread d'une étape précédente peut encore signaler : on l'ignore
                if done is not None and self.stage is not None and stage in STAGE_LABELS \
                        and list(STAGE_LABELS).index(stage) < list(STAGE_LABELS).index(self.stage):
                    return
                self.stage, self.done, self.total = stage, done, total
                if not self.live and stage in STAGE_LABELS:
                    print(f"  - {STAGE_LABELS[stage]}", flush=True)
            elif done is not None:
                self.done, self.total = done, total

    def _line(self, frame: int) -> str:
        elapsed = f"{time.time() - self.started:.0f} s"
        parts = [blue(SPINNER[frame % len(SPINNER)]), self.title]
        with self._lock:
            stage, done_, total = self.stage, self.done, self.total
        if stage in STAGE_LABELS:
            parts.append(dim("·") + " " + STAGE_LABELS[stage])
        if total:
            width = 20
            filled = round(width * min(done_ or 0, total) / total)
            parts.append("[" + blue("█" * filled) + dim("░" * (width - filled)) + f"] {done_}/{total}")
        parts.append(dim(elapsed))
        return " ".join(parts)

    def _animate(self) -> None:
        frame = 0
        while not self._stop.wait(0.1):
            columns = shutil.get_terminal_size((100, 20)).columns
            line = self._line(frame)
            # Ne jamais dépasser la largeur, sinon \r ne ramène plus en début de ligne
            visible = len(_ANSI.sub("", line))
            if visible > columns - 1:
                line = _ANSI.sub("", line)[: columns - 2] + "…"
            sys.stdout.write("\r\033[K" + line)
            sys.stdout.flush()
            frame += 1

    def __exit__(self, exc_type, exc, tb) -> None:
        progress.set_listener(None)
        elapsed = time.time() - self.started
        if self.live:
            self._stop.set()
            self._thread.join()
            sys.stdout.write("\r\033[K")
        mark = green("✓") if exc_type is None else _style("✗", "31")
        if self.live:
            print(f"{mark} {self.title} {dim(f'{elapsed:.0f} s')}", flush=True)
        else:
            print(f"  {'terminé' if exc_type is None else 'échec'} en {elapsed:.0f} s", flush=True)


def fail(message: str) -> None:
    print(_style(f"Erreur : {message}", "31"), file=sys.stderr)
    sys.exit(1)


# ── Étapes ────────────────────────────────────────────────────────────────────

def search_candidates(name: str) -> tuple[list[dict], bool]:
    """Up to 5 OpenAlex author profiles for the name, and whether they are approximate."""
    from src.pathfinding.author_search import search_author_candidates
    from src.pathfinding.openalex_client import OpenAlexClient

    authors, approximate = search_author_candidates(name, OpenAlexClient())
    candidates = []
    for author in authors:
        affiliations = [
            a.get("institution", {}).get("display_name", "")
            for a in author.get("affiliations", [])
            if a.get("institution", {}).get("display_name")
        ]
        candidates.append({
            "openalex_id": author.get("id", ""),
            "name": author.get("display_name", ""),
            "works_count": author.get("works_count", 0),
            "cited_by_count": author.get("cited_by_count", 0),
            "affiliations": affiliations[:2],
        })
    return candidates, approximate


def choose_candidate(candidates: list[dict], auto: bool) -> dict:
    print()
    for i, c in enumerate(candidates, 1):
        affil = " · ".join(c["affiliations"]) or "affiliation inconnue"
        print(f"  {bold(str(i))}. {bold(c['name'])}")
        print(f"     {affil}")
        print(dim(f"     {c['works_count']} publications · {c['cited_by_count']} citations"))
    print()

    if auto or len(candidates) == 1:
        print(f"Profil retenu : {bold(candidates[0]['name'])}")
        return candidates[0]

    while True:
        answer = input(f"Quel profil analyser ? [1-{len(candidates)}, q pour quitter] ").strip().lower()
        if answer in ("q", "quit", "exit"):
            sys.exit(0)
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        print("Réponse invalide.")


def init_database() -> None:
    from src.database.database import create_all_tables

    create_all_tables()


def run_pipeline(researcher_name: str, openalex_id: str, quick: bool) -> Path:
    from scripts.modules.phase1_data_collection import collect_all_data
    from scripts.modules.phase2_database_storage import store_all_to_database
    from scripts.modules.phase3_graph_generation import generate_complete_graph
    from src.helpers import slug

    with Step("Collecte : publications, co-auteurs, brevets, essais cliniques, paiements déclarés"):
        data = collect_all_data(
            researcher_name=researcher_name,
            max_publications=50 if quick else 100,
            max_patents=5 if quick else 10,
            max_coauthors_ct=10 if quick else 30,
            max_coauthors_ts=15 if quick else 50,
            min_amount_ts=0.0,
            use_db_only=False,
            openalex_id=openalex_id,
        )
    if not data.get("scholar"):
        fail(f"aucune publication trouvée pour « {researcher_name} » sur OpenAlex.")

    with Step("Déduplication et stockage"):
        store_all_to_database(researcher_name=researcher_name, data=data)

    with Step("Construction de la carte du réseau"):
        generate_complete_graph(
            researcher_name=researcher_name,
            scholar_data=data["scholar"],
            patents_data=data.get("patents"),
            enrich_persons=not quick,
            discover_coauthor_patents_api=not quick and bool(os.getenv("SERPAPI_KEY")),
        )

    generated = ROOT / f"{slug(researcher_name).replace('-', '_')}_network.html"
    if not generated.exists():
        fail("le graphe n'a pas été généré (voir --verbose).")
    return generated


def export_graph(generated: Path) -> Path:
    """Copy the graph to output/ as a self-contained file."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    html = generated.read_text(encoding="utf-8")

    # Le HTML pyvis référence lib/bindings/utils.js en relatif : on l'inline
    # pour que le fichier s'ouvre de n'importe où.
    utils = ROOT / "lib" / "bindings" / "utils.js"
    tag = '<script src="lib/bindings/utils.js"></script>'
    if tag in html and utils.exists():
        html = html.replace(tag, f"<script>{utils.read_text(encoding='utf-8')}</script>")

    target = OUTPUT_DIR / generated.name
    target.write_text(html, encoding="utf-8")
    generated.unlink()
    return target


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cartographie le réseau scientifique et industriel d'un chercheur.",
    )
    parser.add_argument("name", nargs="*", help="nom du chercheur (demandé si absent)")
    parser.add_argument("--quick", action="store_true",
                        help="analyse allégée : moins de publications et de co-auteurs, sans enrichissement")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="prendre le premier profil proposé sans demander")
    parser.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("-v", "--verbose", action="store_true", help="afficher les logs du pipeline")
    args = parser.parse_args()

    if not args.verbose:
        # Les erreurs attendues (clé absente, source indisponible) sont résumées
        # par la CLI elle-même ; --verbose montre tout
        logging.disable(logging.ERROR)

    print(bold("Scholarmap") + dim(" — cartographie du réseau d'un chercheur"))
    if not os.getenv("SERPAPI_KEY"):
        print(dim("SERPAPI_KEY absent : les brevets seront ignorés. Clé gratuite : voir README, section SerpAPI."))
    if not os.getenv("OPENAI_API_KEY"):
        print(dim("OPENAI_API_KEY absent : pas de reclassement IA des entités."))
    print()

    name = " ".join(args.name).strip()
    while not name:
        try:
            name = input("Nom du chercheur : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

    try:
        with Step(f"Recherche de « {name} » sur OpenAlex"):
            candidates, approximate = search_candidates(name)
    except Exception as e:  # réseau, maintenance OpenAlex
        fail(f"OpenAlex est injoignable ({e}).")
    if not candidates:
        fail(f"aucun profil trouvé pour « {name} », même en orthographe approchée.\n"
             "Essayez le nom de famille seul, ou le nom tel qu'il apparaît dans ses publications.")
    if approximate:
        print(f"Pas de profil exact pour « {name} » : voici les plus proches.")

    try:
        chosen = choose_candidate(candidates, args.yes)
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    print()

    init_database()
    started = time.time()
    try:
        generated = run_pipeline(chosen["name"], chosen["openalex_id"], args.quick)
    except KeyboardInterrupt:
        print("\nAnalyse interrompue.")
        sys.exit(130)
    target = export_graph(generated)

    print()
    print(bold(f"Carte prête en {(time.time() - started) / 60:.1f} min : ") + str(target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target))
    print(dim("Filtres en haut de la carte ; cliquez sur une entreprise pour voir le chemin qui la relie au chercheur."))
    if os.getenv("SERPAPI_KEY"):
        from src.api.serpapi_client import SerpAPIClient
        print(dim(f"{SerpAPIClient.real_calls} requête(s) SerpAPI consommée(s) "
                  "(les réponses sont gardées en cache : relancer la même analyse ne coûte rien)."))
    if not args.no_open:
        webbrowser.open(target.as_uri())



if __name__ == "__main__":
    main()
