import asyncio
from pathlib import Path

import httpx
import pandas as pd
from loguru import logger
from parsel import Selector
from pydantic import ValidationError

from NCBI.config import BATCH, CSV_FILE, EFETCH, ESEARCH, FILE, HEADERS, QUERY_GROUPS
from NCBI.models import Article

logger.add(
    "logs/app.log",
    rotation="10 MB",  # rotation automatique
    retention="10 days",  # suppression auto
    compression="zip",  # compression
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> |"
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    "- <level>{message}</level>",
    enqueue=True,
)

logger.level("Data_GAP", no=38, color="<yellow><bold>")

# ─────────────────────────────────────────
# PMID FILE GESTION
# ─────────────────────────────────────────


def read_pmid(path=FILE):
    file = Path(path)
    if file.exists():
        return set(file.read_text(encoding="utf-8").splitlines())
    return set()


def save_pmid(pmids: set[str], path=FILE):
    with open(path, "a", encoding="utf-8") as f:
        for pmid in pmids:
            f.write(pmid + "\n")


#           f.flush()


# ─────────────────────────────────────────
# RECHERCHE & FETCH PUBMED
# ─────────────────────────────────────────


async def search_pmid(
    client: httpx.AsyncClient, query, seen_pmids, max_result: int = 40
):
    logger.info(f"Debut du scraping pour la query : {query}")
    search_pmid_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_result,
        "retmode": "json",
        "sort": "relevance",
    }

    result = await client.get(ESEARCH, params=search_pmid_params)
    result.raise_for_status()
    data = result.json()
    pmids = data["esearchresult"]["idlist"]
    new_pmid = []
    for pmid in pmids:
        if pmid not in seen_pmids:
            seen_pmids.add(pmid)
            new_pmid.append(pmid)
    return new_pmid


async def fetch_article(client: httpx.AsyncClient, chunk, retry=3):
    for attempt in range(retry):
        try:
            id_pmids = ",".join(chunk)
            fetch_params = {
                "db": "pubmed",
                "id": id_pmids,
                "retmode": "xml",
                "rettype": "abstract",
            }
            response = await client.get(EFETCH, params=fetch_params)

            if response.status_code == 429:
                time = int(response.headers.get("Retry-After", 2))
                logger.warning("to many request")
                await asyncio.sleep(time)
                continue

            response.raise_for_status()
            logger.info(f"Fetch réussi | Status : {response.status_code}")

            return parse_article(response.text)

        except httpx.TimeoutException as e:
            logger.error(f"Connection timeout: {e}")
            await asyncio.sleep(2 * (attempt + 1))

    logger.error("fail chunk skipped")
    return []


def score_article(abstact: str):
    score = 0
    if not abstact:
        return None
    if len(abstact) > 150:
        score += 0.4
    if len(abstact) > 400:
        score += 0.3
        pass


def parse_article(response: str):

    sel = Selector(text=response, type="xml")
    arts = sel.xpath("//PubmedArticle")
    if not arts:
        return []

    articles = []
    for art in arts:
        authors_list = [
            f"{a.xpath('ForeName/text()').get('')} {a.xpath('LastName/text()').get('')}".strip()
            for a in art.xpath(".//AuthorList/Author")
        ]

        if not authors_list:
            logger.warning("authors_liste is not presente")
        title = art.xpath(".//ArticleTitle/text()").get()
        abstract = (
            "".join(art.xpath(".//Abstract/AbstractText//text()").getall()).strip()
            or None
        )
        pmid = art.xpath(".//PMID/text()").get("N/A")
        doi = art.xpath(".//ArticleId[@IdType='doi']/text()").get()

        try:
            articles.append(
                Article(
                    title=title,
                    abstract=abstract,
                    authors=authors_list,
                    pmid=pmid,
                    doi=doi,
                )
            )
        except ValidationError as e:
            pmid = art.xpath(".//PMID/text()").get("inconnu")
            logger.log("Data_GAP", f"[skip] PMID {pmid} — {e.error_count()} erreur(s)")

            continue  # on passe à l'article suivant
    return articles


# ---------------------------------------------
# SAVE CSV
# ---------------------------------------------


def save_result(result):

    file_exist = CSV_FILE.exists()
    df = pd.DataFrame((a.model_dump()) for a in result)
    df.to_csv(
        CSV_FILE,
        mode="a",
        header=not file_exist,
        sep="|",
        encoding="utf-8",
        index=False,
    )
    logger.info(f"{len(result)} article --> {CSV_FILE}")


# ---------------------------------------------
# MAIN
# ---------------------------------------------


async def main():
    semaphore = asyncio.Semaphore(2)
    seen_pmids = read_pmid()

    async def limited(client, chunk):
        async with semaphore:
            await asyncio.sleep(1)
            return await fetch_article(client, chunk)

    for group, queries in QUERY_GROUPS.items():
        logger.info(f"\n── Groupe : {group} ──")
        all_pmids = []  # reset à chaque groupe

        async with httpx.AsyncClient(headers=HEADERS) as client:
            for query in queries:
                pmids = await search_pmid(client, query, seen_pmids)
                if len(pmids) == 0:
                    logger.error("No pmids find")
                logger.info(f"number of pmids : {len(pmids)}")
                all_pmids.extend(pmids)
                await asyncio.sleep(10)

            all_pmids = list(dict.fromkeys(all_pmids))

            if not all_pmids:
                logger.error(f"[{group}] aucun PMID, skip")
                continue

            chunks = [all_pmids[i : i + BATCH] for i in range(0, len(all_pmids), BATCH)]
            tasks = [limited(client, chunk) for chunk in chunks]
            results = await asyncio.gather(*tasks)

            valid = [article for batch in results if batch for article in batch]
            save_pmid({a.pmid for a in valid})
            save_result(valid)


if __name__ == "__main__":
    asyncio.run(main())
