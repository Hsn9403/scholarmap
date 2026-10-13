"""
Transparence Santé API client.

Provides access to the French public database of conflicts of interest
for healthcare professionals and pharmaceutical/medical device companies.
"""

import asyncio
import requests
from urllib.parse import quote
from dataclasses import dataclass
from typing import List, Set, Optional
from src.logger import logger


@dataclass
class FinancialDeclaration:
    """
    A financial declaration from Transparence Santé.

    Represents a payment or benefit from a company to a healthcare professional.
    """
    declaration_id: str
    date: str
    company_name: str
    company_siren: str
    sector: str
    amount: float
    declaration_type: str  # "convention", "avantage", etc.
    reason: str  # "Formation", "Autres prestations", etc.
    reason_detail: Optional[str]
    beneficiary_name: str
    beneficiary_first_name: str
    beneficiary_profession: str
    status: str
    publication_date: str

    @property
    def full_beneficiary_name(self) -> str:
        """Return full name (firstname + lastname)."""
        return f"{self.beneficiary_first_name} {self.beneficiary_name}"

    def __repr__(self) -> str:
        return (
            f"<FinancialDeclaration({self.company_name} → {self.full_beneficiary_name}: "
            f"{self.amount:,.2f}€ for {self.reason})>"
        )


@dataclass
class TransparenceSanteSearchResult:
    """Results from a Transparence Santé search."""
    total_declarations: int
    declarations_over_threshold: int
    total_amount: float
    companies_found: Set[str]
    declarations: List[FinancialDeclaration]

    def __repr__(self) -> str:
        return (
            f"<TransparenceSanteSearchResult("
            f"total={self.total_declarations}, "
            f"over_threshold={self.declarations_over_threshold}, "
            f"total_amount={self.total_amount:,.2f}€, "
            f"companies={len(self.companies_found)})>"
        )


class TransparenceSanteClient:
    """
    Client for the Transparence Santé API.

    The API is free and does not require authentication for consultation.
    """

    BASE_URL = "https://www.transparence.sante.gouv.fr/api/explore/v2.1"
    DATASET = "declarations"

    def __init__(self):
        """Initialize the client."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Scholarmap/1.0 (Research Tool)',
            'Accept': 'application/json'
        })

    def search_by_name(
        self,
        last_name: str,
        first_name: str,
        min_amount: float = 10000.0,
        max_results: int = 100
    ) -> TransparenceSanteSearchResult:
        """
        Search for financial declarations for a given person.

        Args:
            last_name: Last name of the person (case-insensitive)
            first_name: First name of the person (case-insensitive)
            min_amount: Minimum amount threshold in euros
            max_results: Maximum number of results to retrieve (API limit: 100)

        Returns:
            TransparenceSanteSearchResult with all declarations over threshold

        Note:
            The API has a hard limit of 100 results per request. If you need
            more results, you'll need to implement pagination or filter more
            strictly (e.g., higher min_amount).
        """
        logger.info(f"Searching Transparence Santé for: {first_name} {last_name} (≥{min_amount}€)")

        # Enforce API limit
        if max_results > 100:
            logger.warning(f"max_results={max_results} exceeds API limit, capping at 100")
            max_results = 100

        url = self._build_url(last_name, first_name, max_results)
        try:
            logger.info(f"[TS] GET {url}")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            result = self._parse_response(response.json(), min_amount)
            logger.info(f"✓ {len(result.companies_found)} companies, {result.total_amount:,.2f}€")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Error querying Transparence Santé API: {e}")
            return TransparenceSanteSearchResult(
                total_declarations=0, declarations_over_threshold=0,
                total_amount=0.0, companies_found=set(), declarations=[]
            )

    def _build_url(self, last_name: str, first_name: str, max_results: int = 100) -> str:
        from src.helpers import strip_accents_basic
        where_clause = (
            f"identite='{strip_accents_basic(last_name).upper()}' AND "
            f"prenom='{strip_accents_basic(first_name).upper()}'"
        )
        return (
            f"{self.BASE_URL}/catalog/datasets/{self.DATASET}/records?"
            f"where={quote(where_clause)}&limit={max_results}&order_by=montant+desc"
        )

    def _parse_response(self, data: dict, min_amount: float) -> "TransparenceSanteSearchResult":
        total_found = data.get('total_count', 0)
        results = data.get('results', [])
        declarations, companies, total_amount = [], set(), 0.0
        for fields in results:
            amount = float(fields.get('montant', 0))
            company = fields.get('raison_sociale', '')
            declarations.append(FinancialDeclaration(
                declaration_id=fields.get('id', ''),
                date=fields.get('date', '')[:10] if fields.get('date') else '',
                company_name=company,
                company_siren=fields.get('numero_siren', ''),
                sector=fields.get('secteur_activite', ''),
                amount=amount,
                declaration_type=fields.get('lien_interet', ''),
                reason=fields.get('motif_lien_interet', '') or 'Non renseigné',
                reason_detail=fields.get('autre_motif'),
                beneficiary_name=fields.get('identite', ''),
                beneficiary_first_name=fields.get('prenom', ''),
                beneficiary_profession=fields.get('profession_libelle', ''),
                status=fields.get('statut', ''),
                publication_date=fields.get('date_publication', '')[:10] if fields.get('date_publication') else '',
            ))
            companies.add(company)
            total_amount += amount
        return TransparenceSanteSearchResult(
            total_declarations=total_found,
            declarations_over_threshold=len(declarations),
            total_amount=total_amount,
            companies_found=companies,
            declarations=declarations,
        )

    async def search_by_name_async(
        self,
        session: "httpx.AsyncClient",
        last_name: str,
        first_name: str,
        min_amount: float = 0.0,
        max_results: int = 100,
    ) -> "TransparenceSanteSearchResult":
        """Async version of search_by_name — uses a shared httpx.AsyncClient."""
        import httpx
        url = self._build_url(last_name, first_name, max_results)
        logger.info(f"[TS] GET {url}")
        try:
            response = await session.get(url, timeout=10)
            response.raise_for_status()
            return self._parse_response(response.json(), min_amount)
        except Exception as e:
            logger.warning(f"[TS async] {first_name} {last_name}: {e}")
            return TransparenceSanteSearchResult(
                total_declarations=0, declarations_over_threshold=0,
                total_amount=0.0, companies_found=set(), declarations=[]
            )

    def get_companies_by_threshold(
        self,
        last_name: str,
        first_name: str,
        min_amount: float = 10000.0
    ) -> Set[str]:
        """
        Get list of companies that paid over a threshold to a person.

        Args:
            last_name: Last name of the person
            first_name: First name of the person
            min_amount: Minimum amount threshold in euros

        Returns:
            Set of company names
        """
        result = self.search_by_name(last_name, first_name, min_amount)
        return result.companies_found
