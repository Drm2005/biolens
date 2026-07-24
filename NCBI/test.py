import asyncio
from pathlib import Path

import httpx
from config import EFETCH, ESEARCH, FILE, HEADERS
from loguru import logger

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


def read_pmids():
    path = Path(FILE)
    if path.exists():
        logger.info(f"{FILE} trouvé")
        with open(FILE, encoding="utf-8") as f:
            return {clean_line for line in f if (clean_line := line.strip())}
    return set()


def save_pmids(pmids: set[str], path=FILE):
    with open(path, "a", encoding="utf-8") as f:
        for pmid in pmids:
            if pmid.strip():
                f.write(pmid + "\n")


async def get_pmids(
    client: httpx.AsyncClient, query: str, seen_pmids, retmax: int = 20
):
    logger.info(f"Debut du scraping pour la query : {query}")
    max_retry = 3
    for attempt in range(max_retry):
        try:
            search_pmids_params = {
                "db": "pubmed",
                "term": query,
                "retmax": retmax,
                "retmode": "json",
                "sort": "relevance",
            }
            result = await client.get(ESEARCH, params=search_pmids_params)
            result.raise_for_status()
            data = result.json()
            pmids = data["esearchresult"]["idlist"]
            return pmids
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(f"Erreur detecter :{exc}")
            if attempt == max_retry - 1:
                logger.warning("dernier tentative")
                raise exc

            wait_time = 2**attempt
            await asyncio.sleep(wait_time)


async def efetch(client: httpx.AsyncClient, chunk):
    logger.info("debut de l'extraction de article ")
    id_list = ",".join(chunk)
    retry = 3
    for attempt in range(retry):
        try:
            eftech_article_param = {
                "db": "pubmed",
                "id": id_list,
                "retmode": "xml",
                "rettype": "abstract",
            }
            response = await client.get(url=EFETCH, params=eftech_article_param)
            response.raise_for_status()
            return parse_article(response)

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code

            if status_code == 429:
                logger.warning(f"Erreur {status_code}: to many request")
                await asyncio.sleep(2 * (attempt + 1))
                continue

            elif 500 <= status_code < 600:
                logger.warning(f"Erreur {status_code}: probléme intern")
                await asyncio.sleep(2**attempt)
                continue

        except httpx.RequestError as exc:
            # Erreurs réseau (timeout, pas d'internet)
            logger.warning(f"Erreur réseau ({exc}). Nouvel essai...")
            await asyncio.sleep(2**attempt)

    logger.error("Tentative échouer réessayer plus tard")
    return []


async def parse_article(response):
    pass


async def main():
    print("merde")
    seen_pmids = read_pmids()
    async with httpx.AsyncClient(headers=HEADERS) as client:
        test = await get_pmids(
            client, query="BRCA1 breast cancer mutation", seen_pmids=seen_pmids
        )

    return print(test)


if __name__ == "__main__":
    asyncio.run(main())
