"""
Coauthor Binary Matcher using OpenAI.

Validates whether a candidate (found on TS/CT/Patents) is the SAME person
as a coauthor from OpenAlex. Returns strict yes/no only.

Uses OpenAI GPT-5.4-mini for semantic comparison.
Caches results to avoid redundant API calls.
"""

import os
from openai import OpenAI
from src.logger import logger


class CoauthorMatcherOpenAI:
    """Binary coauthor matcher: same person or not (cached)."""

    def __init__(self):
        """Initialize OpenAI client."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set — CoauthorMatcher will not work")

        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.cache = {}  # (candidate_name, candidate_year, context[:40]) → bool

    def is_same_person(
        self,
        oa_name: str,
        oa_domains: list,
        oa_years_min: int,
        oa_years_max: int,
        candidate_name: str,
        candidate_year: int,
        candidate_context: str
    ) -> bool:
        """
        Binary validation: Is this the SAME person?

        Args:
            oa_name: Name from OpenAlex
            oa_domains: Research domains from OpenAlex (e.g., ["Neurology", "Alzheimer's"])
            oa_years_min: Earliest publication year
            oa_years_max: Latest publication year
            candidate_name: Name from TS/CT/Patents
            candidate_year: Year found on secondary source
            candidate_context: Context string (e.g., "Sector: Pharmacology")

        Returns:
            True if same person, False if different person
        """

        # Check cache first
        cache_key = (candidate_name, candidate_year, candidate_context[:40])
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Fallback if no API key
        if not self.client:
            logger.warning(f"No OpenAI API key — cannot validate {candidate_name}, assume different")
            return False

        # Detailed prompt to catch domain mismatches
        prompt = f"""Is this the SAME person? Be strict about domain compatibility.

Person A (OpenAlex):
- Name: {oa_name}
- Research domains: {', '.join(oa_domains)}
- Active years: {oa_years_min}-{oa_years_max}

Person B (Candidate):
- Name: {candidate_name}
- Year: {candidate_year}
- Evidence: {candidate_context}

Requirements for YES:
1. Names match (accounting for spelling/format)
2. Activity years overlap or are close
3. Research domains are COMPATIBLE (not just one keyword match)
   - Similar field = YES (e.g. neurology + immunology both medical)
   - Different field = NO (e.g. biochemistry vs robotics)
4. No strong contradictions

Be conservative: if domains seem mismatched, answer NO.

Answer ONLY: yes or no"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=1
            )

            answer = response.choices[0].message.content.strip().lower()
            result = "yes" in answer

            # Cache and return
            self.cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"OpenAI validation error for '{candidate_name}': {e}")
            # Conservative: assume different person to avoid false positives
            return False
