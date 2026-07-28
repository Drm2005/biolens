import asyncio
from pathlib import Path

import httpx
import pandas as pd
from config import CSV_FILE, EFETCH, ESEARCH, FILE
from loguru import logger
from models import Article
from parsel import Selector
from pydantic import ValidationError

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
        f.writelines(pmid + "\n" for pmid in pmids)


#           f.flush()


# ─────────────────────────────────────────
# RECHERCHE & FETCH PUBMED
# ─────────────────────────────────────────


async def safe_get(client: httpx.AsyncClient, url, params, retry=3, s=2):
    for attempt in range(retry):
        try:
            response = await client.get(url, params=params)
            if response.status_code == 429:
                logger.warning("to many request")
                time = int(response.headers.get("Retry-After", 2))
                await asyncio.sleep(time)

            response.raise_for_status()
            logger.info(f" réussi | Status: {response.status_code}")
            return response

        except httpx.TimeoutException:
            waiting = attempt**s
            await asyncio.sleep(waiting)
            logger.info(f"retry N:{retry} in {waiting}S")

        except httpx.HTTPStatusError as e:
            logger.error(f"Erreur HTTP {e.response.status_code} sur {url}")
            raise  # erreurs 4xx/5xx autres que 429 : pas la peine de réessayer

    raise RuntimeError(f"Échec après {retry} tentatives : {url}")


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

    response = await safe_get(client, url=ESEARCH, params=search_pmid_params)
    data = response.json()
    pmids = data["esearchresult"]["idlist"]
    new_pmid = []
    for pmid in pmids:
        if pmid not in seen_pmids:
            seen_pmids.add(pmid)
            new_pmid.append(pmid)
    return new_pmid


async def fetch_article(client: httpx.AsyncClient, chunk):
    id_pmids = ",".join(chunk)
    fetch_params = {
        "db": "pubmed",
        "id": id_pmids,
        "retmode": "xml",
        "rettype": "abstract",
    }
    response = await safe_get(client, EFETCH, params=fetch_params)
    return list(parse_article(response.text))


def parse_article(response: str):

    sel = Selector(text=response, type="xml")
    arts = sel.xpath("//PubmedArticle")
    if not arts:
        return []

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
        pmid: str | None = art.xpath(".//PMID/text()").get("N/A")
        doi = art.xpath(".//ArticleId[@IdType='doi']/text()").get()

        try:
            article = Article(
                title=title,
                abstract=abstract,
                authors=authors_list,
                pmid=pmid,
                doi=doi,
            )
            yield article

        except ValidationError as e:
            pmid = art.xpath(".//PMID/text()").get("inconnu")
            logger.log("Data_GAP", f"[skip] PMID {pmid} — {e.error_count()} erreur(s)")
            continue  # on passe à l'article suivant


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
