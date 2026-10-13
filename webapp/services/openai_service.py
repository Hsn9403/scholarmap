"""
Service OpenAI — contextualisation du H-index par discipline et séniorité.
"""
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any

from src.logger import logger

# Cache en mémoire : évite les appels répétés sur la même session
_CACHE: Dict[str, Any] = {}

_SYSTEM_PROMPT = """You are an expert academic research evaluator for venture capital due diligence.
You assess researchers' H-index relative to their specific scientific field and career seniority.
Always respond with valid JSON only, no markdown, no explanation outside JSON."""

_USER_PROMPT_TEMPLATE = """Evaluate this researcher:
- Name: {name}
- Affiliation: {affiliation}
- H-index: {h_index}
- First publication year: {first_pub_year} (approximately {career_years} years of research career)
- Sample publication titles (use these to precisely identify their scientific specialty): {pub_titles}

IMPORTANT COHERENCE RULES — all fields must be consistent with each other:
- "percentile" = rank from the TOP. Lower = better. e.g. 5 means TOP 5% (better than 95% of peers in the same field at the same career stage).
- The percentile, category and scale MUST align:
  * exceptionnel → percentile 1–5
  * excellent     → percentile 6–15
  * bon           → percentile 16–35
  * moyen         → percentile 36–65
  * faible        → percentile 66–100
- Never write "très bon" or "faible" in the scale if the percentile says the opposite.

Return a JSON object with exactly these fields:
{{
  "percentile": <integer between 1 and 100, lower is better>,
  "field": "<researcher's scientific DISCIPLINE (not the disease area studied), inferred primarily from publication titles, in French. Use the methodology/technique domain, e.g. 'Biologie médicale', 'Biochimie', 'Immunologie', 'Biologie computationnelle', 'Microfluidique', 'Pharmacologie'. A researcher publishing on Alzheimer biomarkers is in 'Biologie médicale' or 'Biochimie', NOT 'Neurologie'. A researcher publishing on cancer immunotherapy is in 'Immunologie', NOT 'Oncologie'.>",
  "category": "<one of: exceptionnel | excellent | bon | moyen | faible>",
  "scale": "<2-3 sentences: typical H-index ranges for this field at this career stage, in French, with specific numbers. Must be consistent with the percentile above.>",
  "investment_signal": "<1 sentence for VC investors assessing whether this researcher is a scientific 'star', in French>"
}}"""


def get_h_index_assessment(
    name: str,
    affiliation: Optional[str],
    h_index: int,
    first_pub_year: Optional[int],
    pub_titles: Optional[list] = None,
) -> Optional[Dict[str, Any]]:
    """
    Call OpenAI to contextualise a researcher's H-index within their field and career stage.

    Args:
        name: Researcher full name
        affiliation: Current affiliation (used to infer scientific field)
        h_index: Researcher's H-index
        first_pub_year: Year of first publication (career seniority proxy)

    Returns:
        Dict with keys: percentile, field, category, scale, investment_signal
        None if OpenAI call fails or API key is missing.
    """
    cache_key = f"{name}_{h_index}_v4"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — H-index AI assessment skipped")
        return None

    current_year = datetime.now().year
    career_years = (current_year - first_pub_year) if first_pub_year else "unknown"

    # Up to 5 most-cited titles to anchor the specialty — avoids field confusion on ambiguous names
    titles_str = ""
    if pub_titles:
        titles_str = " | ".join(t for t in pub_titles[:5] if t)
    if not titles_str:
        titles_str = "Not available"

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        name=name,
        affiliation=affiliation or "Not specified",
        h_index=h_index,
        first_pub_year=first_pub_year or "unknown",
        career_years=career_years,
        pub_titles=titles_str,
    )

    # Try gpt-5.4-mini first, fallback to gpt-4o-mini if model not available
    models_to_try = ["gpt-5.4-mini", "gpt-4o-mini"]
    model_used = os.getenv("OPENAI_MODEL")
    if model_used:
        models_to_try = [model_used]

    last_error = None
    for model in models_to_try:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_completion_tokens=400,
            )
            raw = response.choices[0].message.content.strip()
            result = json.loads(raw)

            # Validate required keys
            required = {"percentile", "field", "category", "scale", "investment_signal"}
            if not required.issubset(result.keys()):
                logger.warning(f"OpenAI response missing keys: {required - result.keys()}")
                return None

            logger.info(f"H-index assessment for {name}: Top {result['percentile']}% ({result['field']}) via {model}")
            _CACHE[cache_key] = result
            return result

        except Exception as e:
            last_error = e
            logger.warning(f"OpenAI model {model} failed: {e}")
            continue

    logger.error(f"All OpenAI models failed for {name}: {last_error}")
    return None
