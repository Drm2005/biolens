import asyncio
from pathlib import Path

import httpx
import pandas as pd
from loguru import logger

from NCBI.config import BATCH, CSV_FILE, HEADERS, QUERY_GROUPS, final_csv
from NCBI.filtration import analyse_batch
from NCBI.pubmed_article import (
    fetch_article,
    read_pmid,
    save_pmid,
    save_result,
    search_pmid,
)


def create_csv_file():
    pass


def check_csv(path=CSV_FILE):
    file = Path(path)
    if file.exists():
        return file


# ---------------------------------------------
# MAIN
# ---------------------------------------------


async def main():
    semaphore = asyncio.Semaphore(2)
    seen_pmids = read_pmid()

    async def limited(client, chunk):
        async with semaphore:
            result = await fetch_article(client, chunk)
        await asyncio.sleep(1)
        return result

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
                await asyncio.sleep(8)

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
            logger.success("gemini analyse starts")

            async def limit_analyse(df):
                async with semaphore:
                    result = await analyse_batch(df)
                return df, result

            works = []
            for df in pd.read_csv(CSV_FILE, encoding="utf-8", sep="|", chunksize=20):
                df["pmid"] = df["pmid"].astype(str)
                if "summary" not in df.columns:
                    df["summary"] = None
                    df["relevance_score"] = None
                    df["relevance_justification"] = None
                    df["mesh_keywords"] = None

                works.append(asyncio.create_task(limit_analyse(df)))
            for work in asyncio.as_completed(works):
                df, end_part = await work
                for par in end_part:
                    pmid = par.article_id
                    mask = df["pmid"] == pmid
                    df.loc[mask, "summary"] = par.summary
                    df.loc[mask, "relevance_score"] = par.relevance_score
                    df.loc[mask, "relevance_justification"] = (
                        par.relevance_justification
                    )
                    df.loc[mask, "mesh_keywords"] = ",".join(par.mesh_keywords)

                df.to_csv(
                    final_csv,
                    mode="a",
                    header=not Path(final_csv).exists(),
                    sep="|",
                    encoding="utf-8",
                    index=False,
                )
                logger.info(f"part with {BATCH} saved in {final_csv}")


if __name__ == "__main__":
    asyncio.run(main())
