from pathlib import Path

final_csv = "complet_article.csv"
FILE = "pmid_list.txt"
CSV_FILE = Path("article.csv")
FINAL_CSV_FILE = Path(final_csv)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PubMedBot/1.0)"}
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BATCH: int = 30

# ---------------------------------------------
# QUERY
# ---------------------------------------------

QUERY_GROUPS = {
    "oncology": [
        # 1. Prédisposition génétique au cancer du sein
        """Breast Neoplasms [MeSH Major Topic] AND (Genetic Predisposition to Disease [MeSH Terms] OR BRCA1 [MeSH Terms] OR BRCA2 [MeSH Terms])""",
        # 2. Génétique du cancer du sein
        """Breast Neoplasms [MeSH Major Topic] AND (genetics [Subheading] OR Genetic Variation [MeSH Terms] OR Genetic Association Studies [MeSH Terms])""",
        # 3. Mutations et cancer du sein
        """Breast Neoplasms [MeSH Major Topic] AND ( Mutation [MeSH Terms] OR Mutations OR genetic mutation )""",
        # 4. BRCA et cancer du sein
        """Breast Neoplasms [MeSH Major Topic] AND (BRCA1 OR BRCA2 OR "BRCA1"[MeSH Terms] OR "BRCA2"[MeSH Terms])""",
        # 5. Gènes impliqués dans le cancer du sein
        """Breast Neoplasms [MeSH Major Topic] AND ( Genes, Neoplasm [MeSH Terms] OR tumor suppressor genes OR oncogenes [MeSH Terms] )""",
        # 6. Hérédité et cancer du sein
        """Breast Neoplasms [MeSH Major Topic] AND ( Hereditary Cancer-Predisposing Syndrome [MeSH Terms] OR hereditary OR inherited OR familial)""",
    ],
}
