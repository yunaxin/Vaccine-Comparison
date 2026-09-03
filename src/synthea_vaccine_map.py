"""
synthea_vaccine_map.py

Synthea's immunizations.csv uses full CDC/CVX-style vaccine descriptions
(e.g., "Influenza  split virus  trivalent  PF"), not the short codes used
in vaccine_mapping.json (e.g., "Flu"). This is a translation layer,
distinct from transform.py's strip_dose_suffix() -- that handles suffix
noise (like "#1", "(YF-VAX)"); this handles an entirely different naming
convention from a different data source.

Built by manually reviewing the 25 unique DESCRIPTION values found in
synthea_sample_100_dataset/immunizations.csv against vaccine_mapping.json's
keys. Extend this dict if new Synthea description values show up.
"""

SYNTHEA_TO_MAPPING_NAME = {
    "Influenza  split virus  trivalent  PF": "Flu",
    "meningococcal MCV4P": "MCV4",
    "COVID-19  mRNA  LNP-S  PF  30 mcg/0.3 mL dose": "COVID-19",
    "Td (adult)  5 Lf tetanus toxoid  preservative free  adsorbed": "Td",
    "Hep B  adult": "HepB",
    "zoster vaccine  live": "ZVL",
    "COVID-19  mRNA  LNP-S  PF  100 mcg/0.5mL dose or 50 mcg/0.25mL dose": "COVID-19",
    "Tdap": "Tdap",
    "HPV  quadrivalent": "HPV",
    "Hep B  adolescent or pediatric": "HepB",
    "Hib (PRP-OMP)": "Hib",
    "rotavirus  monovalent": "RV1",
    "IPV": "IPV",
    "DTaP": "DTaP",
    "Pneumococcal conjugate PCV 13": "PCV13",
    "varicella": "Varicella",
    "MMR": "MMR",
    "Hep A  ped/adol  2 dose": "HepA",
    "Hep A  adult": "HepA",
    "COVID-19 vaccine  vector-nr  rS-Ad26  PF  0.5 mL": "COVID-19",
    "zoster vaccine recombinant": "RZV",
    "tetanus toxoid  reduced diphtheria toxoid  and acellular pertussis vaccine  adsorbed": "Tdap",
    "meningococcal polysaccharide (groups A  C  Y and W-135) diphtheria toxoid conjugate vaccine (MCV4P)": "MCV4",
    "pneumococcal polysaccharide vaccine  23 valent": "PPSV23",
}


def translate_synthea_vaccine_name(description: str) -> str:
    """
    Returns the short mapping-file key for a Synthea DESCRIPTION value.
    Returns the original description unchanged if not found in the map --
    this makes unmapped entries visible (they'll show up in unmapped_records
    downstream) rather than silently guessing or dropping them.
    """
    return SYNTHEA_TO_MAPPING_NAME.get(description, description)