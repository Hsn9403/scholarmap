#!/usr/bin/env python3
"""
Excel export functionality for researcher reports.

Generates multi-sheet Excel dashboards focused on corporate connections,
with patent details and academic profile as secondary sheets.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from zoneinfo import ZoneInfo

from src.models import ScholarData, PatentsData

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
HEADER_BLUE = "1212AD"
CARD_FILL = "F4F6FF"
MUTED_FILL = "EEF0FF"
ZEBRA_FILL = "F8FAFF"
GRID_COLOR = "D0D3E2"

# Corporate link type colors
COLOR_ASSIGNEE = "0D5C2E"   # dark green - lien direct
COLOR_CITING   = "0D3C6B"   # dark blue  - la société cite les travaux

# Fill backgrounds for each link type
FILL_ASSIGNEE = "D6F0E0"
FILL_CITING   = "D6E8F5"


class ExcelExporter:
    """
    Exports researcher data to styled Excel dashboards.

    3-sheet structure:
    - "Dashboard"   : Corporate connections (main focus)
    - "Brevets"     : Patent details
    - "Publications": Academic publications (secondary)
    """

    def write(
        self,
        out_path: str,
        researcher_name: str,
        scholar: Optional[ScholarData],
        patents: PatentsData,
    ) -> None:
        """Generate a multi-sheet Excel report focused on corporate links."""
        wb = Workbook()
        ws_dash = wb.active
        ws_dash.title = "Dashboard"

        ws_patents = wb.create_sheet("Brevets")
        ws_pubs    = wb.create_sheet("Publications")

        self._build_dashboard(ws_dash, researcher_name, scholar, patents)
        self._build_patents_sheet(ws_patents, patents)
        self._build_publications_sheet(ws_pubs, scholar)

        # Freeze panes on Dashboard only
        ws_dash.freeze_panes = "B5"

        wb.save(out_path)

    # =========================================================================
    # Sheet builders
    # =========================================================================

    def _build_dashboard(self, ws, researcher_name: str,
                         scholar: Optional[ScholarData],
                         patents: PatentsData) -> None:
        """Build the main Dashboard sheet: corporate connections focus."""
        self._set_col_widths(ws, {
            "A": 2.5, "B": 28, "C": 22, "D": 12, "E": 14,
            "F": 52, "G": 22, "H": 22, "I": 2.5,
        })

        # Title bar
        self._merge_bar(ws, 2, "B", "H", "Scholarmap", size=14)

        # Info row
        paris_now = datetime.now(ZoneInfo("Europe/Paris"))
        ws["B3"].value = "Researcher"
        ws["C3"].value = researcher_name
        ws["D3"].value = "Généré (FR)"
        ws["E3"].value = paris_now.strftime("%Y-%m-%d %H:%M:%S")
        for col in "FGH":
            ws[f"{col}3"].value = ""
        self._style_range(ws, "B3:H3", fill=PatternFill("solid", fgColor=MUTED_FILL), bold=True)
        ws["C3"].font = Font(bold=False)
        ws["E3"].font = Font(bold=False)

        # Summary cards — keep exact key-value structure for backward compat
        self._card(ws, 5, "B", "D", 5, "Académique - Synthèse")
        self._card(ws, 5, "F", "H", 5, "Brevets - Synthèse")

        top_patents = (patents.top_patents or [])[:10]
        self._write_scholar_card(ws, scholar)
        self._write_patents_card(ws, patents, top_patents)

        # Corporate analysis
        corporate_links = _build_corporate_analysis(patents)
        bridge_people   = _build_bridge_people(patents, scholar, researcher_name)

        row = 13

        # === Liens Corporates ===
        self._merge_bar(ws, row, "B", "H",
                        f"Liens Corporates ({len(corporate_links)} sociétés identifiées)")
        row += 1

        if corporate_links:
            # Sub-header
            hdrs = [
                ("B", "Société"), ("C", "Type de lien"), ("D", "Force"),
                ("E", "Nb brevets"), ("F", "Explication"), ("G", "Brevets concernés"),
                ("H", "Lien"),
            ]
            for col, label in hdrs:
                ws[f"{col}{row}"].value = label
            self._style_range(
                ws, f"B{row}:H{row}",
                fill=PatternFill("solid", fgColor=HEADER_BLUE),
                bold=True, font_color="FFFFFF", center=True,
            )
            row += 1

            for link in corporate_links:
                ws[f"B{row}"].value = link["company"]
                ws[f"C{row}"].value = link["link_type"]
                ws[f"D{row}"].value = _strength_label(link["strength"])
                ws[f"E{row}"].value = link["strength"]
                ws[f"F{row}"].value = link["explanation"]
                ws[f"G{row}"].value = link["patents"]
                if link.get("url"):
                    self._make_hyperlink(ws[f"H{row}"], link["url"])
                else:
                    ws[f"H{row}"].value = ""

                # Color-code by link type
                fill_hex = {
                    "Assignataire direct": FILL_ASSIGNEE,
                    "Cite les travaux":    FILL_CITING,
                }.get(link["link_type"], ZEBRA_FILL)
                color_hex = {
                    "Assignataire direct": COLOR_ASSIGNEE,
                    "Cite les travaux":    COLOR_CITING,
                }.get(link["link_type"], "111111")

                fill = PatternFill("solid", fgColor=fill_hex)
                for col in "BCDEFGH":
                    cell = ws[f"{col}{row}"]
                    cell.fill = fill
                    cell.border = self._thin_border()
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                ws[f"B{row}"].font = Font(bold=True, color=color_hex)
                ws[f"C{row}"].font = Font(bold=True, color=color_hex)
                ws.row_dimensions[row].height = 44
                row += 1
        else:
            ws[f"B{row}"].value = "Aucun lien corporate identifié dans les brevets analysés."
            ws[f"B{row}"].font = Font(italic=True, color="888888")
            row += 1

        row += 1  # spacing

        # === Personnes-Pont (co-auteurs / co-inventeurs liés à des corporates) ===
        self._merge_bar(ws, row, "B", "H",
                        f"Personnes-Pont - Co-auteurs & Co-inventeurs liés au corporate ({len(bridge_people)})")
        row += 1

        if bridge_people:
            hdrs2 = [
                ("B", "Nom"), ("C", "Rôle"),
                ("D", "Co-publications"), ("E", "Dernière collab."),
                ("F", "Société(s) liée(s)"), ("G", ""), ("H", ""),
            ]
            for col, label in hdrs2:
                ws[f"{col}{row}"].value = label
            self._style_range(
                ws, f"B{row}:H{row}",
                fill=PatternFill("solid", fgColor=HEADER_BLUE),
                bold=True, font_color="FFFFFF", center=True,
            )
            row += 1

            for i, person in enumerate(bridge_people):
                fill = PatternFill("solid", fgColor=ZEBRA_FILL) if i % 2 else None
                ws[f"B{row}"].value = person["name"]
                ws[f"C{row}"].value = person["role"]
                ws[f"D{row}"].value = person["shared_pubs"] if person["shared_pubs"] else ""
                ws[f"E{row}"].value = person["last_year"] or ""
                ws[f"F{row}"].value = person["companies"]
                ws[f"G{row}"].value = ""
                ws[f"H{row}"].value = ""
                for col in "BCDEFGH":
                    cell = ws[f"{col}{row}"]
                    cell.border = self._thin_border()
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    if fill:
                        cell.fill = fill
                ws[f"B{row}"].font = Font(bold=True)
                ws.row_dimensions[row].height = 32
                row += 1
        else:
            ws[f"B{row}"].value = "Aucun co-auteur identifié comme co-inventeur sur brevets corporate."
            ws[f"B{row}"].font = Font(italic=True, color="888888")

    def _build_patents_sheet(self, ws, patents: PatentsData) -> None:
        """Build the Brevets sheet with detailed patent information."""
        self._set_col_widths(ws, {
            "A": 2.5, "B": 28, "C": 22, "D": 20,
            "E": 16, "F": 16, "G": 28, "H": 28, "I": 22, "J": 2.5,
        })

        self._merge_bar(ws, 2, "B", "I", "Brevets - Détail (Top 10)", size=13)

        top_patents = (patents.top_patents or [])[:10]
        if not top_patents:
            ws["B4"].value = "Aucun brevet trouvé."
            ws["B4"].font = Font(italic=True, color="888888")
            return

        header_row = 4
        headers = [
            ("B", "Titre"), ("C", "Lien"), ("D", "Assignataire"),
            ("E", "Sociétés citées"), ("F", "Sociétés citantes"),
            ("G", "Co-inventeurs"), ("H", "Revendication principale"), ("I", "Date"),
        ]
        for col, label in headers:
            ws[f"{col}{header_row}"].value = label
        self._style_range(
            ws, f"B{header_row}:I{header_row}",
            fill=PatternFill("solid", fgColor=HEADER_BLUE),
            bold=True, font_color="FFFFFF", center=True,
        )
        ws.freeze_panes = "B5"

        r = header_row + 1
        for pt in top_patents:
            cited   = [c for c in (pt.cited_assignees or []) if c]
            citing  = [c for c in (pt.citing_assignees or [])
                       if c and c != "no corporate has cited this patent"]
            co_inv  = pt.co_inventors or []
            claim1  = (pt.claims_top3 or [""])[0]

            ws[f"B{r}"].value = pt.title or ""
            self._make_hyperlink(ws[f"C{r}"], pt.link or "")
            ws[f"D{r}"].value = pt.current_assignee or ""
            ws[f"E{r}"].value = "; ".join(cited) if cited else ""
            ws[f"F{r}"].value = "; ".join(citing) if citing else ""
            ws[f"G{r}"].value = "; ".join(co_inv) if co_inv else ""
            ws[f"H{r}"].value = self._truncate(claim1, 200)
            ws[f"I{r}"].value = pt.publication_date or ""
            if claim1:
                self._add_comment(ws[f"H{r}"], claim1)

            ws.row_dimensions[r].height = 60
            r += 1

        self._zebra_table(ws, header_row + 1, r - 1, 2, 9)
        ws.auto_filter.ref = f"B{header_row}:I{r-1}"

    def _build_publications_sheet(self, ws, scholar: Optional[ScholarData]) -> None:
        """Build the Publications sheet (secondary, simplified)."""
        self._set_col_widths(ws, {
            "A": 2.5, "B": 48, "C": 14, "D": 14, "E": 2.5,
        })

        self._merge_bar(ws, 2, "B", "D", "Publications académiques (Top 10)", size=13)

        pubs = (scholar.top_publications if scholar else [])[:10]
        if not pubs:
            ws["B4"].value = "Aucune publication trouvée."
            ws["B4"].font = Font(italic=True, color="888888")
            return

        header_row = 4
        ws[f"B{header_row}"].value = "Titre"
        ws[f"C{header_row}"].value = "Lien"
        ws[f"D{header_row}"].value = "Citations"
        self._style_range(
            ws, f"B{header_row}:D{header_row}",
            fill=PatternFill("solid", fgColor=HEADER_BLUE),
            bold=True, font_color="FFFFFF", center=True,
        )
        ws.freeze_panes = "B5"

        r = header_row + 1
        for p in pubs:
            ws[f"B{r}"].value = p.title or ""
            self._make_hyperlink(ws[f"C{r}"], p.link or "")
            ws[f"D{r}"].value = p.cited_by if p.cited_by is not None else ""
            ws[f"D{r}"].alignment = Alignment(horizontal="center", vertical="top")
            ws.row_dimensions[r].height = 28
            r += 1

        self._zebra_table(ws, header_row + 1, r - 1, 2, 4)
        ws.auto_filter.ref = f"B{header_row}:D{r-1}"

    # =========================================================================
    # Card writers (keep exact structure for backward compat with load_from_excel)
    # =========================================================================

    def _write_scholar_card(self, ws, scholar: Optional[ScholarData]) -> None:
        """Write Scholar summary card — exact key names preserved for load_from_excel."""
        rows_data = [
            ("author_id",    scholar.author_id if scholar else "NOT_FOUND"),
            ("Affiliation",  scholar.affiliation if scholar else ""),
            ("Citations",    scholar.citations_total if scholar and scholar.citations_total is not None else ""),
            ("H-index",      scholar.h_index if scholar and scholar.h_index is not None else ""),
            ("Publications", scholar.publications_total if scholar and scholar.publications_total is not None else ""),
        ]
        for i, (label, value) in enumerate(rows_data):
            row = 6 + i
            ws[f"B{row}"].value = label
            ws[f"C{row}"].value = value
            ws[f"B{row}"].font = Font(bold=True, color="111111")
            ws[f"B{row}"].border = self._thin_border()
            ws[f"C{row}"].border = self._thin_border()
            ws[f"B{row}"].alignment = Alignment(vertical="top")
            ws[f"C{row}"].alignment = Alignment(vertical="top", wrap_text=True)

    def _write_patents_card(self, ws, patents: PatentsData, top_patents: list) -> None:
        """Write Patents summary card — exact key names preserved for load_from_excel."""
        uniq_co, uniq_citing, uniq_cited = set(), set(), set()
        for pt in top_patents:
            for n in (pt.co_inventors or []):
                if n:
                    uniq_co.add(n)
            for c in (pt.cited_assignees or []):
                if c:
                    uniq_cited.add(c)
            for c in (pt.citing_assignees or []):
                if c and c != "no corporate has cited this patent":
                    uniq_citing.add(c)

        data = [
            ("Patents total",    patents.patents_total if patents.patents_total is not None else ""),
            ("Co-inventeurs",    len(uniq_co)),
            ("Soc. citantes",    len(uniq_citing)),
            ("Soc. citées",      len(uniq_cited)),
        ]
        for i, (label, value) in enumerate(data):
            row = 6 + i
            ws[f"F{row}"].value = label
            ws[f"G{row}"].value = value
            ws[f"F{row}"].font = Font(bold=True, color="111111")
            ws[f"F{row}"].border = self._thin_border()
            ws[f"G{row}"].border = self._thin_border()

    # =========================================================================
    # Style helpers
    # =========================================================================

    @staticmethod
    def _thin_border() -> Border:
        thin = Side(style="thin", color=GRID_COLOR)
        return Border(left=thin, right=thin, top=thin, bottom=thin)

    @staticmethod
    def _set_col_widths(ws, widths: dict) -> None:
        for col, w in widths.items():
            ws.column_dimensions[col].width = w

    def _merge_bar(self, ws, row: int, c1: str, c2: str, text: str, size: int = 11) -> None:
        ws.merge_cells(f"{c1}{row}:{c2}{row}")
        cell = ws[f"{c1}{row}"]
        cell.value = text
        cell.fill = PatternFill("solid", fgColor=HEADER_BLUE)
        cell.font = Font(bold=True, color="FFFFFF", size=size)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = self._thin_border()
        ws.row_dimensions[row].height = 32 if size >= 13 else 22

    def _card(self, ws, top_row: int, left: str, right: str, height: int, title: str) -> None:
        self._merge_bar(ws, top_row, left, right, title)
        fill = PatternFill("solid", fgColor=CARD_FILL)
        self._style_range(ws, f"{left}{top_row+1}:{right}{top_row+height}", fill=fill)

    def _style_range(self, ws, cell_range: str, fill=None, bold=False,
                     font_color=None, center=False, wrap=True) -> None:
        border = self._thin_border()
        for row in ws[cell_range]:
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(
                    horizontal="center" if center else "left",
                    vertical="center" if center else "top",
                    wrap_text=wrap,
                )
                if fill:
                    cell.fill = fill
                if bold or font_color:
                    cell.font = Font(bold=bold, color=font_color)

    def _zebra_table(self, ws, start_row: int, end_row: int,
                     start_col: int, end_col: int) -> None:
        border = self._thin_border()
        zebra = PatternFill("solid", fgColor=ZEBRA_FILL)
        for r in range(start_row, end_row + 1):
            is_zebra = ((r - start_row) % 2 == 1)
            for c in range(start_col, end_col + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = border
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if is_zebra:
                    cell.fill = zebra

    @staticmethod
    def _make_hyperlink(cell, url: str, label: str = "Ouvrir") -> None:
        if url:
            cell.value = label
            cell.hyperlink = url
            cell.font = Font(color="0563C1", underline="single")
        else:
            cell.value = ""

    @staticmethod
    def _truncate(s: str, max_len: int = 140) -> str:
        s = " ".join((s or "").split())
        return s if len(s) <= max_len else s[:max_len - 1] + "…"

    @staticmethod
    def _add_comment(cell, text: str, author: str = "Scholarmap") -> None:
        if text and text.strip():
            cell.comment = Comment(text.strip(), author)


# ---------------------------------------------------------------------------
# Corporate analysis helpers
# ---------------------------------------------------------------------------

def _build_corporate_analysis(patents: PatentsData) -> List[Dict[str, Any]]:
    """
    Build ranked list of corporate links from patents data.

    Priority:
      1. Assignataire direct - researcher co-invented, company owns the patent
      2. Cite les travaux    - company cited researcher's patents (actively monitors)

    Note: "cited_assignees" (companies cited BY the researcher) are excluded —
    the signal only matters in the other direction (company cites researcher).
    """
    companies: Dict[str, Dict[str, Any]] = {}

    def _get(name: str) -> Dict[str, Any]:
        if name not in companies:
            companies[name] = {
                "types": set(),
                "patent_titles": [],
                "assignee_count": 0,
                "citing_count": 0,
            }
        return companies[name]

    for pt in (patents.top_patents or []):
        title = pt.title or ""

        # Direct assignee
        if pt.current_assignee and pt.current_assignee.strip():
            rec = _get(pt.current_assignee.strip())
            rec["types"].add("Assignataire direct")
            if title and title not in rec["patent_titles"]:
                rec["patent_titles"].append(title)
            rec["assignee_count"] += 1

        # Citing companies (they cite this researcher's patents - strong signal)
        for co in (pt.citing_assignees or []):
            co = (co or "").strip()
            if co and co != "no corporate has cited this patent":
                rec = _get(co)
                rec["types"].add("Cite les travaux")
                if title and title not in rec["patent_titles"]:
                    rec["patent_titles"].append(title)
                rec["citing_count"] += 1

    result = []
    for name, data in companies.items():
        types = data["types"]

        if "Assignataire direct" in types:
            priority = 1
            link_type = "Assignataire direct"
            n = data["assignee_count"]
            explanation = (
                f"Lien direct fort : {name} est assignataire de {n} brevet(s) "
                f"co-inventé(s) par ce chercheur. Relation IP établie."
            )
        else:
            priority = 2
            link_type = "Cite les travaux"
            n = data["citing_count"]
            explanation = (
                f"{name} a cité {n} brevet(s) de ce chercheur dans ses propres dépôts. "
                f"Signal fort : cette société surveille et s'appuie sur ces travaux."
            )

        strength = len(data["patent_titles"])
        patents_str = "; ".join(data["patent_titles"][:3])
        if len(data["patent_titles"]) > 3:
            patents_str += f" (+{len(data['patent_titles']) - 3} autres)"

        result.append({
            "company":     name,
            "link_type":   link_type,
            "priority":    priority,
            "strength":    strength,
            "explanation": explanation,
            "patents":     patents_str,
            "url":         None,
        })

    result.sort(key=lambda x: (x["priority"], -x["strength"]))
    return result


def _build_bridge_people(
    patents: PatentsData,
    scholar: Optional[ScholarData],
    researcher_name: str = "",
) -> List[Dict[str, Any]]:
    """
    Find people who bridge academic and industrial worlds:
    - Co-inventors on patents assigned to a company
    - Bonus: cross-referenced with co-authors (academic collaboration)
    - Excludes the researcher themselves (name match, case-insensitive)
    """
    # Normalize researcher name for exclusion (last name comparison)
    researcher_parts = researcher_name.strip().lower().split()
    researcher_last = researcher_parts[-1] if researcher_parts else ""
    researcher_full = researcher_name.strip().lower()

    def _is_researcher(inv_name: str) -> bool:
        n = inv_name.strip().lower()
        if n == researcher_full:
            return True
        parts = n.split()
        if parts and parts[-1] == researcher_last and researcher_last:
            return True
        return False

    # Map co-inventor → companies they appear with on patents
    inventor_companies: Dict[str, set] = {}
    for pt in (patents.top_patents or []):
        assignee = (pt.current_assignee or "").strip()
        for inv in (pt.co_inventors or []):
            inv = (inv or "").strip()
            if not inv or _is_researcher(inv):
                continue
            if inv not in inventor_companies:
                inventor_companies[inv] = set()
            if assignee:
                inventor_companies[inv].add(assignee)

    # Build co-author lookup: last_name (lower) → CoAuthor
    coauthor_map: Dict[str, Any] = {}
    if scholar and scholar.coauthors:
        for ca in scholar.coauthors:
            if not ca.name:
                continue
            parts = ca.name.strip().split()
            if parts:
                coauthor_map[parts[-1].lower()] = ca

    result = []
    seen_names: set = set()

    for inv_name, companies in inventor_companies.items():
        if not companies:
            continue
        inv_lower = inv_name.strip().split()
        last = inv_lower[-1].lower() if inv_lower else ""
        coauthor = coauthor_map.get(last)

        if inv_name in seen_names:
            continue
        seen_names.add(inv_name)

        if coauthor:
            role = "Co-auteur + Co-inventeur"
            shared = coauthor.shared_pubs_count
            last_year = coauthor.last_shared_year or ""
            display_name = coauthor.name
        else:
            role = "Co-inventeur (brevet)"
            shared = 0
            last_year = ""
            display_name = inv_name

        result.append({
            "name":       display_name,
            "role":       role,
            "shared_pubs": shared,
            "last_year":  last_year,
            "companies":  "; ".join(sorted(companies)),
        })

    # Sort: co-authors with most shared publications first, then pure co-inventors
    result.sort(key=lambda x: (-x["shared_pubs"], x["name"]))
    return result


def _strength_label(n: int) -> str:
    """Human-readable strength label."""
    if n >= 5:
        return "Très fort"
    if n >= 3:
        return "Fort"
    if n >= 2:
        return "Modéré"
    return "Faible"


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

def write_xlsx(
    out_path: str,
    researcher_name: str,
    scholar: Optional[ScholarData],
    patents: PatentsData,
) -> None:
    """Deprecated: Use ExcelExporter().write() instead."""
    ExcelExporter().write(out_path, researcher_name, scholar, patents)
