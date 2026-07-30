from pathlib import Path

final_csv = "complet_article.csv"
FILE = "pmid_list.txt"
CSV_FILE = Path("article.csv")
FINAL_CSV_FILE = Path(final_csv)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PubMedBot/1.0)"}
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


# ---------------------------------------------
# QUERY
# ---------------------------------------------

QUERY_GROUPS = {
    "oncology": [
        "BRCA1 breast cancer mutation",
        "lung cancer immunotherapy PD-1",
        "tumor microenvironment T cells",
    ],
    "immunology": [
        "cytokine storm COVID-19",
        "IL-6 signaling inflammation",
        "CAR-T cell therapy leukemia",
    ],
    "genomics": [
        "CRISPR Cas9 gene editing off-target",
        "single cell RNA sequencing tumor",
        "whole genome sequencing rare disease",
    ],
}

BATCH: int = 30
