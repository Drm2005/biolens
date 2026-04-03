# 🔬 biolens

> Async Python pipelines for scientific & biomedical data — from raw API responses to structured, analysis-ready datasets.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-brightgreen?style=flat-square)]()
[![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet?style=flat-square)](https://github.com/astral-sh/uv)

A growing collection of asynchronous scraping pipelines targeting open scientific databases (NCBI, Europe PMC, ClinicalTrials…). Built with clean architecture, API rate-limit compliance, and a clear data path toward **BigQuery analytics** and **Neo4j graph exploration**.

---

## 🗺️ Data Architecture

```
NCBI API
   └─→ Async Scraper (httpx + asyncio)
           └─→ Structured JSON / CSV
                   ├─→ BigQuery  ──→  Looker Studio  (trends, keyword stats)
                   └─→ Neo4j             (graph: authors, citations, MeSH terms)
```

---

## 📌 Current Pipelines

### `NCBI/` — NCBI E-utilities

#### `pubmed_article.py` — PubMed metadata pipeline

Queries the [NCBI E-utilities API](https://www.ncbi.nlm.nih.gov/books/NBK25497/) to retrieve and parse biomedical literature at scale.

| Step | Endpoint | Output |
|------|----------|--------|
| Search by keyword | `esearch` | List of PMIDs |
| Fetch article data | `efetch` | XML per PMID |
| Parse fields | `parsel` | title, abstract, PMID, DOI |

**Rate limiting:** `asyncio.Semaphore(3)` — NCBI-compliant (≤3 req/sec without API key)

**Stack:** `httpx` · `asyncio` · `parsel`

---

## 🗂️ Repository Structure

```
biolens/
│
├── NCBI/
│   └── pubmed_article.py     # PubMed async pipeline
│
├── action_article.py         # CLI entry point / post-processing actions
├── .gitignore
├── .python-version
├── pyproject.toml
├── uv.lock
├── LICENSE
└── README.md
```

---

## ⚙️ Installation

```bash
git clone https://github.com/Drm2005/biolens.git
cd scraper
```

> Using `uv` (recommended):
> ```bash
> uv sync
> ```

> Or with pip:
> ```bash
> pip install httpx parsel
> ```

---

## 🚀 Usage

```python
import asyncio
from NCBI.pubmed_article import fetch_many

results = asyncio.run(fetch_many(query="CRISPR gene therapy", max_result=10))

for abstract, title, pmid, doi in results:
    print(f"[{pmid}] {title}")
    print(f"DOI: {doi}\n")
```

---

## 🧠 Design Decisions

| Choice | Reason |
|---|---|
| `httpx` over `requests` | Native async support — essential for concurrent I/O |
| `asyncio.Semaphore(3)` | NCBI rate limit: ≤3 req/sec without API key |
| `parsel` over `BeautifulSoup` | CSS + XPath support; production scraping standard |
| `type="xml"` in Selector | Parsel defaults to HTML mode — explicit XML required for E-utilities |
| Flat functions (current) | Readable at this scale; OOP `BaseScraper` refactor scoped in roadmap |
| `uv` as package manager | Fast, reproducible installs via `pyproject.toml` + `uv.lock` |

---

## 🗺️ Roadmap

**Pipeline hardening**
- [ ] Export to CSV / JSON
- [ ] Retry logic with `tenacity`
- [ ] Structured logging with `logger`
- [ ] Abstract `BaseScraper` class

**Analytics layer**
- [ ] BigQuery ingestion (`google-cloud-bigquery`)
- [ ] Looker Studio dashboard — publication trends, keyword co-occurrence
- [ ] Neo4j graph 

**New sources** *(NCBI-first, then expanding)*
- [ ] NCBI SRA — sequencing experiment metadata
- [ ] ClinicalTrials.gov
- [ ] Europe PMC / bioRxiv

---

## 👤 Author

Built by **Daid** — L3 Biotechnology (USTHB), building at the intersection of data engineering and biomedical research.

- 🧬 Background: pharmacology · genomics · bioinformatics
- 🎯 Focus: async pipelines · BigQuery · graph databases · scientific data
- 📍 Targeting roles in QC / data science — pharma-biotech (FR/CH)

---

## 📄 License

[MIT](LICENSE)
