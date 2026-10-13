#!/usr/bin/env python3
"""
Central configuration for target corporate entities.

This file contains the master list of corporate entities to detect across
ALL modules (clinical trials, patents, affiliations, etc.).

Usage:
    from src.config.target_corporates import TARGET_CORPORATES, PRODUCT_TO_CORPORATE

    # In any module
    for corporate in TARGET_CORPORATES:
        # Search for this corporate...
"""

# =============================================================================
# TARGET CORPORATES
# =============================================================================
# Main list of corporate entities to detect.
# These are normalized (lowercase) for case-insensitive matching.
#
# ⚠️ IMPORTANT: Add new corporates here to make them searchable across all modules
# =============================================================================

TARGET_CORPORATES = [
    # Medical Devices - Cardiovascular
    "medtronic",
    "boston scientific",
    "abbott",
    "edwards lifesciences",
    "cook medical",
    "terumo",
    "c.r. bard",
    "cr bard",
    "c r bard",
    "bard",
    "lemaitre vascular",
    "endologix",
    "gore medical",
    "w.l. gore",
    "merit medical",
    "silk road medical",
    "penumbra",
    "microvention",

    # Medical Devices - Imaging & Diagnostics
    "ge healthcare",
    "general electric",
    "siemens",
    "philips",
    "olympus",
    "pentax",
    "fujifilm",
    "hologic",

    # Medical Devices - Surgical & Orthopedic
    "stryker",
    "zimmer biomet",
    "johnson & johnson",
    "j&j",
    "intuitive surgical",
    "getinge",
    "teleflex",

    # Medical Devices - General
    "bd",
    "becton dickinson",
    "cardinal health",
    "baxter",
    "fresenius",
    "biosensors",
    "merit",

    # Pharmaceuticals - Major
    "pfizer",
    "novartis",
    "roche",
    "sanofi",
    "merck",
    "gsk",
    "glaxosmithkline",
    "astrazeneca",
    "eli lilly",
    "bristol myers squibb",
    "bms",
    "amgen",
    "gilead",
    "biogen",
    "regeneron",
    "vertex",
    "alexion",

    # Biotechnology
    "genentech",
    "celgene",
    "illumina",
    "10x genomics",
    "thermo fisher",
    "agilent",
    "danaher",
    "bio-rad",

    # ========================================================================
    # CUSTOM TARGET CORPORATES - Organized by Category
    # ========================================================================

    # Medtech & Dispositifs Médicaux (Additional)
    "smith+nephew",
    "smith nephew",
    "siemens healthineers",
    "canon medical",
    "fujifilm healthcare",

    # Pharma & Biotech (Additional)
    "takeda",
    "bayer",
    "moderna",
    "msd",  # Merck Sharp & Dohme
    "otsuka pharmaceuticals",
    "otsuka",
    "boehringer ingelheim",
    "click therapeutics",
    "click",

    # Diagnostic In Vitro & Life Sciences Tools
    "roche diagnostics",
    "abbott diagnostics",
    "beckman coulter",
    "cepheid",
    "radiometer",
    "qiagen",
    "exact sciences",
    "bruker",
    "perkinelmer",
    "revvity",
    "sartorius",
    "merck kgaa",
    "milliporesigma",

    # Éditeurs Logiciels Santé & Data
    "epic systems",
    "epic",
    "oracle health",
    "cerner",
    "dedalus",
    "intersystems",
    "meditech",
    "iqvia",
    "veeva systems",
    "veeva",
    "veradigm",
    "change healthcare",
    "optum",
    "health catalyst",
    "flatiron health",
    "flatiron",
    "tempus",
    "komodo health",

    # Big Tech & Conglomérats
    "alphabet",
    "google health",
    "microsoft",
    "nuance",
    "amazon",
    "one medical",
    "apple",
    "samsung medtech",
    "sony medical",

    # CROs & Services Cliniques
    "ppd",
    "icon",
    "parexel",
    "medpace",
    "syneos health",
    "syneos",
    "labcorp drug development",
    "labcorp",

    # Payeurs & Assureurs
    "unitedhealth group",
    "unitedhealth",
    "cvs health",
    "cvs",
    "cigna",
    "evernorth",
    "humana",
    "anthem",
    "elevance",
    "axa health",
    "axa",
    "allianz care",
    "allianz",

    # Groupes Hospitaliers & Réseaux Privés
    "hca healthcare",
    "hca",
    "mayo clinic",
    "cleveland clinic",
    "kaiser permanente",
    "kaiser",
    "ramsay health care",
    "ramsay",
    "orpea",
    "clariane",

    # Private Equity Health
    "tpg healthcare",
    "tpg",
    "kkr health",
    "kkr",
    "bain capital life sciences",
    "bain capital",
    "advent international",
    "advent",
    "carlyle healthcare",
    "carlyle",
    "eqt health",
    "eqt",
    "hg",

    # ========================================================================
    # INDUSTRIEL & ÉNERGIE
    # ========================================================================

    # Électrique & Automation
    "hitachi energy",
    "hitachi",
    "abb",
    "abb technology",
    "abb ltd",
    "schneider electric",
    "schneider",
    "siemens energy",
    "ge power",
    "general electric power",
    "eaton",
    "emerson electric",
    "emerson",
    "rockwell automation",
    "rockwell",
    "honeywell",
    "yokogawa",
    "mitsubishi electric",
    "mitsubishi heavy industries",

    # Énergie & Utilities
    "ge vernova",
    "alstom",
    "vestas",
    "siemens gamesa",
    "nordex",
    "enercon",
    "engie",
    "edf",
    "total energies",
    "totalenergies",
    "shell",
    "bp",
    "equinor",
    "schlumberger",
    "halliburton",
    "baker hughes",

    # Construction & Ingénierie
    "vinci",
    "bouygues",
    "eiffage",
    "aecom",
    "jacobs",
    "fluor",
    "kbr",
    "bechtel",
    "skanska",
    "strabag",

    # ========================================================================
    # TELECOM & NETWORKING
    # ========================================================================

    # Opérateurs Telecom
    "orange",
    "orange sa",
    "vodafone",
    "deutsche telekom",
    "bt group",
    "bt",
    "telefonica",
    "telenor",
    "swisscom",
    "proximus",
    "telstra",
    "at&t",
    "verizon",
    "t-mobile",

    # Équipementiers Telecom
    "nokia",
    "nokia networks",
    "ericsson",
    "huawei",
    "zte",
    "cisco",
    "cisco systems",
    "juniper networks",
    "juniper",
    "arista networks",
    "arista",
    "ciena",
    "infinera",
    "adtran",

    # Semiconducteurs & Composants
    "qualcomm",
    "broadcom",
    "nvidia",
    "intel",
    "amd",
    "arm",
    "mediatek",
    "texas instruments",
    "ti",
    "analog devices",
    "nxp semiconductors",
    "nxp",
    "infineon",
    "stmicroelectronics",
    "st micro",
    "renesas",
    "microchip",
    "maxim integrated",

    # ========================================================================
    # AEROSPACE & DÉFENSE
    # ========================================================================

    # Aéronautique Civile
    "airbus",
    "boeing",
    "bombardier",
    "embraer",
    "comac",
    "dassault aviation",
    "dassault",
    "gulfstream",
    "textron aviation",
    "textron",

    # Motoristes Aéronautiques
    "safran",
    "ge aerospace",
    "rolls-royce",
    "rolls royce",
    "pratt & whitney",
    "pratt whitney",
    "cfm international",
    "cfm",
    "mtu aero engines",
    "mtu",

    # Défense & Systèmes
    "thales",
    "lockheed martin",
    "lockheed",
    "northrop grumman",
    "northrop",
    "raytheon",
    "raytheon technologies",
    "rtx",
    "bae systems",
    "bae",
    "leonardo",
    "l3harris",
    "l3",
    "harris",
    "general dynamics",
    "rheinmetall",
    "saab",
    "rafael",
    "iai",
    "israel aerospace industries",

    # Spatial
    "spacex",
    "space x",
    "blue origin",
    "arianespace",
    "ariane group",
    "avio",
    "virgin galactic",
    "virgin orbit",
    "rocket lab",
    "relativity space",

    # ========================================================================
    # AUTOMOTIVE
    # ========================================================================

    # Constructeurs Automobiles - Premium
    "tesla",
    "bmw",
    "mercedes-benz",
    "mercedes benz",
    "mercedes",
    "audi",
    "porsche",
    "volkswagen",
    "vw",
    "volvo",
    "jaguar land rover",
    "jaguar",
    "land rover",

    # Constructeurs - Volume
    "renault",
    "peugeot",
    "citroen",
    "stellantis",
    "fiat",
    "opel",
    "vauxhall",
    "ford",
    "ford motor",
    "general motors",
    "gm",
    "chevrolet",
    "toyota",
    "honda",
    "nissan",
    "hyundai",
    "kia",
    "mazda",
    "subaru",
    "mitsubishi motors",

    # Constructeurs - Chinois
    "byd",
    "nio",
    "xpeng",
    "li auto",
    "geely",
    "great wall motors",
    "saic motor",

    # Équipementiers Automobiles (Tier 1)
    "bosch",
    "continental",
    "denso",
    "magna international",
    "magna",
    "valeo",
    "zf friedrichshafen",
    "zf",
    "aptiv",
    "lear corporation",
    "lear",
    "faurecia",
    "forvia",
    "autoliv",
    "borgwarner",
    "schaeffler",
    "mahle",
    "hella",
    "marelli",
    "visteon",
    "yazaki",

    # Mobilité & Services
    "uber",
    "lyft",
    "waymo",
    "cruise",
    "argo ai",
    "mobileye",
    "aurora",
    "zoox",

]

# =============================================================================
# PRODUCT TO CORPORATE MAPPING
# =============================================================================
# Maps product/device names to their manufacturer.
# Used primarily in clinical trials to detect corporates via product usage.
#
# Format: "product_name": "Corporate Name"
#
# ⚠️ IMPORTANT: Product names are normalized (lowercase) for matching
# ⚠️ IMPORTANT: Corporate names should match entries in TARGET_CORPORATES
# =============================================================================

PRODUCT_TO_CORPORATE = {
    # -------------------------------------------------------------------------
    # Medtronic Products
    # -------------------------------------------------------------------------
    "in.pact": "Medtronic",
    "inpact": "Medtronic",
    "resolute": "Medtronic",
    "endeavor": "Medtronic",
    "corevalve": "Medtronic",
    "evolut": "Medtronic",
    "valiant": "Medtronic",
    "endurant": "Medtronic",

    # -------------------------------------------------------------------------
    # Boston Scientific Products
    # -------------------------------------------------------------------------
    "taxus": "Boston Scientific",
    "promus": "Boston Scientific",
    "synergy": "Boston Scientific",
    "watchman": "Boston Scientific",
    "ranger": "Boston Scientific",

    # -------------------------------------------------------------------------
    # Abbott Products
    # -------------------------------------------------------------------------
    "xience": "Abbott",
    "absorb": "Abbott",
    "mitraclip": "Abbott",
    "portico": "Abbott",

    # -------------------------------------------------------------------------
    # C.R. Bard / BD Products
    # -------------------------------------------------------------------------
    "lutonix": "C.R. Bard",
    "bard": "C.R. Bard",

    # -------------------------------------------------------------------------
    # Edwards Lifesciences Products
    # -------------------------------------------------------------------------
    "sapien": "Edwards Lifesciences",
    "carpentier": "Edwards Lifesciences",

    # -------------------------------------------------------------------------
    # Gore Products
    # -------------------------------------------------------------------------
    "excluder": "W.L. Gore",
    "gore-tex": "W.L. Gore",

    # ========================================================================
    # ADD YOUR CUSTOM PRODUCT MAPPINGS BELOW THIS LINE
    # ========================================================================
    # Example format:
    # "product_name": "Corporate Name",  # Description (optional comment)

}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_target_corporates() -> list[str]:
    """
    Get the list of target corporate entities.

    Returns:
        List of corporate names (normalized/lowercase).
    """
    return TARGET_CORPORATES.copy()


def get_product_mappings() -> dict[str, str]:
    """
    Get the product → corporate mapping dictionary.

    Returns:
        Dictionary mapping product names to corporate names.
    """
    return PRODUCT_TO_CORPORATE.copy()


def add_target_corporate(corporate_name: str) -> None:
    """
    Add a new corporate to the target list (runtime only, not persisted).

    Args:
        corporate_name: Name of the corporate entity to add.
    """
    normalized = corporate_name.lower()
    if normalized not in TARGET_CORPORATES:
        TARGET_CORPORATES.append(normalized)


def add_product_mapping(product_name: str, corporate_name: str) -> None:
    """
    Add a new product → corporate mapping (runtime only, not persisted).

    Args:
        product_name: Name of the product/device.
        corporate_name: Name of the manufacturing corporate.
    """
    normalized_product = product_name.lower()
    PRODUCT_TO_CORPORATE[normalized_product] = corporate_name


# =============================================================================
# VALIDATION
# =============================================================================

def validate_configuration() -> tuple[bool, list[str]]:
    """
    Validate the configuration for common issues.

    Returns:
        Tuple of (is_valid, list_of_warnings).
    """
    warnings = []

    # Check for duplicates in TARGET_CORPORATES
    seen = set()
    duplicates = []
    for corp in TARGET_CORPORATES:
        if corp in seen:
            duplicates.append(corp)
        seen.add(corp)

    if duplicates:
        warnings.append(f"Duplicate corporates found: {', '.join(duplicates)}")

    # Check that product mappings reference valid corporates
    mapped_corporates = set(PRODUCT_TO_CORPORATE.values())
    target_corporates_set = set(TARGET_CORPORATES)

    for corp in mapped_corporates:
        corp_lower = corp.lower()
        if corp_lower not in target_corporates_set:
            warnings.append(
                f"Product maps to '{corp}' but '{corp_lower}' not in TARGET_CORPORATES"
            )

    is_valid = len(warnings) == 0
    return is_valid, warnings


if __name__ == "__main__":
    # Print summary when run directly
    print("=" * 80)
    print("TARGET CORPORATES CONFIGURATION")
    print("=" * 80)
    print(f"Total target corporates: {len(TARGET_CORPORATES)}")
    print(f"Total product mappings: {len(PRODUCT_TO_CORPORATE)}")

    # Validate
    is_valid, warnings = validate_configuration()

    if is_valid:
        print("\n✅ Configuration is valid")
    else:
        print("\n⚠️  Configuration has warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    # Show first 10 corporates
    print(f"\nFirst 10 corporates:")
    for i, corp in enumerate(TARGET_CORPORATES[:10], 1):
        print(f"  {i}. {corp}")

    if len(TARGET_CORPORATES) > 10:
        print(f"  ... and {len(TARGET_CORPORATES) - 10} more")
