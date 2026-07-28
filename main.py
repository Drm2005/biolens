import asyncio

import httpx
import pandas as pd
from loguru import logger

from NCBI.config import BATCH, CSV_FILE, HEADERS, QUERY_GROUPS
from NCBI.pubmed_article import (
    fetch_article,
    read_pmid,
    save_pmid,
    save_result,
    search_pmid,
)

# ---------------------------------------------
# MAIN
# ---------------------------------------------


async def main():
    semaphore = asyncio.Semaphore(2)
    seen_pmids = read_pmid()

    async def limited(client, chunk):
        async with semaphore:
            await asyncio.sleep(0.1)
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
                await asyncio.sleep(1)

            all_pmids = list(dict.fromkeys(all_pmids))

            if not all_pmids:
                logger.error(f"[{group}] aucun PMID, skip")
                continue

            chunks = [all_pmids[i : i + BATCH] for i in range(0, len(all_pmids), BATCH)]
            tasks = [limited(client, chunk) for chunk in chunks]
            for task in asyncio.as_completed(tasks):
                results = await task
                save_result(results)
                save_pmid({a.pmid for a in results})

    df = pd.read_csv(CSV_FILE, encoding="utf-8", sep="|", chunksize=30)

    df["pmid"] = df["pmid"].astype(str)


if __name__ == "__main__":
    asyncio.run(main())
