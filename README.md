# 🔬 biolens

> Async Python pipeline for biomedical literature — from raw NCBI API responses to structured, LLM-analyzed, analysis-ready datasets.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-brightgreen?style=flat-square)]()
[![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet?style=flat-square)](https://github.com/astral-sh/uv)

An asynchronous scraping and enrichment pipeline targeting PubMed via the NCBI E-utilities API. Articles are scraped, deduplicated, and enriched with LLM-generated summaries, relevance scores, and MeSH keywords — with a resumable design that tolerates partial failures at every stage. Built as a technical proof-of-concept toward RAG-on-graph implementations (Neo4j/GDS) on scientific literature.

---

## 🗺️ Data Architecture

```
NCBI API (esearch / efetch)
   └─→ Async scraper (httpx + asyncio, rate-limited)
           └─→ article.csv (raw articles: title, abstract, authors, PMID, DOI)
                   └─→ Gemini structured analysis (summary, relevance score, MeSH keywords)
                           └─→ complet_article.csv (enriched, analysis-ready dataset)
                                   ├─→ Neo4j        (graph: authors, MeSH terms, citations)
                                   └─→ RAG pipeline  (BioLens core use case)
```

---

## 📌 Current Pipeline

### `NCBI/` — search, fetch, and enrich

| Step | File | What it does |
|---|---|---|
| Search by keyword | `pubmed_article.py` → `search_pmid` | Queries `esearch`, deduplicates against already-seen PMIDs |
| Fetch article data | `pubmed_article.py` → `fetch_article` | Queries `efetch`, XML per PMID chunk, retries on `429`/timeout |
| Parse fields | `pubmed_article.py` → `parse_article` | `parsel` XPath parsing → `title`, `abstract`, `authors`, `pmid`, `doi` (Pydantic-validated) |
| Analyze with LLM | `filtration.py` → `analyse_batch` | Sends batches to Gemini (Gemma) for summary, relevance score (0–100), MeSH keywords — structured JSON output |
| Orchestrate | `main.py` | Runs the full pipeline group by group, resumable across restarts |

**Rate limiting:**
- NCBI fetch: `asyncio.Semaphore(2)` + 1s delay between requests
- Gemini analysis: dedicated `asyncio.Semaphore` shared across all batches (not recreated per call)

**Stack:** `httpx` · `asyncio` · `parsel` · `pydantic` · `google-genai` (Gemma) · `pandas` · `loguru`

---

## 🧠 Design Decisions

| Choice | Reason |
|---|---|
| `httpx.AsyncClient` over `requests` | Native async support — essential for concurrent I/O without blocking |
| `asyncio.Semaphore` (shared instance) | Caps concurrent requests without serializing everything; must be created once and reused, not recreated per call |
| Partial-failure-tolerant batching | A single malformed article in a Gemini response no longer discards the whole batch — only the failed article is retried, on a shrinking `remaining` set |
| `response_schema` + Pydantic validation | `response_schema` constrains generation server-side; Pydantic re-validates client-side as a last line of defense — the two are complementary, not redundant |
| Resumable via PMID diffing | Progress is tracked by comparing `pmid` sets between the raw and the enriched CSV, not by mutating a "done" flag column — safe to interrupt and restart |
| `parsel` over `BeautifulSoup` | CSS + XPath support; production scraping standard |
| `type="xml"` in Selector | Parsel defaults to HTML mode — explicit XML required for E-utilities |
| `uv` as package manager | Fast, reproducible installs via `pyproject.toml` + `uv.lock` |

---

## 🗂️ Repository Structure

```
biolens/
│
├── NCBI/
│   ├── config.py           # constants: endpoints, headers, batch sizes, query groups
│   ├── models.py           # Pydantic models (Article, ArticleAnalysis)
│   ├── pubmed_article.py   # search / fetch / parse (async, rate-limited, retry)
│   ├── filtration.py       # Gemini batch analysis (summary, score, MeSH), partial-retry logic
│   └── test.py             # unit tests
│
├── main.py                 # pipeline orchestration (scrape → enrich → save)
├── article.csv             # raw scraped articles
├── complet_article.csv     # enriched output (summary, relevance_score, mesh_keywords)
├── pmid_list.txt           # seen PMIDs, for dedup across runs
├── logs/                   # rotating logs (loguru)
├── data/, experiments/     # scratch space
├── .env                    # GEMINI_API_KEY
├── pyproject.toml
├── uv.lock
└── LICENSE
```

---

## ⚙️ Installation

```bash
git clone https://github.com/Drm2005/biolens.git
cd biolens
uv sync
```

Create a `.env` file:
```
GEMINI_API_KEY=your_key_here
```

---

## 🚀 Usage

```bash
uv run main.py
```

The pipeline runs per query group defined in `NCBI/config.py`:
1. Searches and fetches new PubMed articles (deduplicated against `pmid_list.txt`).
2. Saves raw results to `article.csv`.
3. Sends unanalyzed articles (diffed against `complet_article.csv`) to Gemini in batches.
4. Appends enriched results to `complet_article.csv`.

Safe to interrupt and rerun — already-enriched articles (matched by PMID) are skipped.

---

## 🗺️ Roadmap

**Pipeline hardening**
- [x] Retry logic with partial-failure recovery (targeted retry on missing/invalid articles only)
- [x] Structured logging with `loguru`
- [x] Resumable pipeline via PMID diffing
- [ ] Unit test coverage for `filtration.py` retry logic (mocked Gemini client)
- [ ] FastAPI wrapper (`POST /search` + `BackgroundTasks` + job polling) for non-CLI usage
- [ ] Dockerize

**Analytics / RAG layer**
- [ ] Neo4j ingestion (GDS-ready graph: authors, MeSH terms, co-citations)
- [ ] RAG-on-graph query layer — the actual sellable deliverable, with BioLens as proof-of-concept
- [ ] BigQuery ingestion for trend analytics (secondary priority)

**New sources** *(NCBI-first, then expanding)*
- [ ] Europe PMC / bioRxiv
- [ ] ClinicalTrials.gov

---

## 👤 Author

Built by **Daid** — Biotechnology graduate (USTHB), building at the intersection of data engineering, biology, and applied LLM/graph pipelines.

- 🧬 Background: pharmacology · genomics · bioinformatics
- 🎯 Focus: async data pipelines · RAG-on-graph · Neo4j · applied LLM structured extraction
- 📍 Targeting: Master BIBS-IA (Paris-Saclay) · hybrid data/AI engineering roles

---

## 📄 License

[MIT](LICENSE)