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


def check_csv(path=CSV_FILE):
    file = Path(path)
    if file.exists():
        return file


# ---------------------------------------------
# MAIN
# ---------------------------------------------


async def main():
    semaphore = asyncio.Semaphore(2)
    analyse_semaphore = asyncio.Semaphore(5)
    seen_pmids = read_pmid()

    async def limited(client, chunk):
        async with semaphore:
            result = await fetch_article(client, chunk)
        await asyncio.sleep(1)
        return result

    async def limit_analyse(df, query):
        async with analyse_semaphore:
            result = await analyse_batch(df, query)
        logger.success(f"Analyse finished : {len(df)} articles")
        return df, result

    for group, queries in QUERY_GROUPS.items():
        logger.info(f"\n── Groupe : {group} ──")
        all_pmids = []
        pmid_to_query = {}

        async with httpx.AsyncClient(headers=HEADERS) as client:
            for query in queries:
                pmids = await search_pmid(client, query, seen_pmids)
                if not pmids:
                    logger.error("No pmids found")
                logger.info(f"number of pmids : {len(pmids)}")

                for pmid in pmids:
                    pmid_to_query[pmid] = query

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
                for article in results:
                    article.query = pmid_to_query.get(article.pmid)
                save_result(results)
                save_pmid({a.pmid for a in results})

    logger.success("gemini analyse starts")
    for attemp in range(3):
        df = pd.read_csv(CSV_FILE, encoding="utf-8", sep="|")
        df["pmid"] = df["pmid"].astype(str)
        if Path(final_csv).exists():
            dg = pd.read_csv(final_csv, encoding="utf-8", sep="|")
            dg = dg[dg["summary"].notnull()]
            check_pmid = set(dg["pmid"].astype(str))
        else:
            check_pmid = set()
        df = df[~df["pmid"].isin(check_pmid)]
        if df.empty:
            break
        df_queries = df["query"].dropna().unique().tolist()
        for query in df_queries:
            df_querie = df[df["query"] == query].copy()
            works = [
                asyncio.create_task(
                    limit_analyse(df_querie.iloc[i : i + 60].copy(), query)
                )
                for i in range(0, len(df_querie), 60)
            ]

            for work in asyncio.as_completed(works):
                try:
                    df_chunk, results = await work
                    df_chunk["summary"] = None
                    if "relevance_score" not in df_chunk:
                        df_chunk["relevance_score"] = None
                    df_chunk["mesh_keywords"] = None
                except Exception as e:
                    logger.exception(e)
                    continue
                for par in results:
                    mask = df_chunk["pmid"] == par.article_id
                    df_chunk.loc[mask, "summary"] = par.summary
                    df_chunk.loc[mask, "relevance_score"] = par.relevance_score
                    df_chunk.loc[mask, "mesh_keywords"] = ",".join(par.mesh_keywords)

                df_chunk = df_chunk[df_chunk["summary"].notnull()]
                df_chunk.to_csv(
                    final_csv,
                    mode="a",
                    header=not Path(final_csv).exists(),
                    sep="|",
                    encoding="utf-8",
                    index=False,
                )
        logger.info(f"part saved in {final_csv}")


if __name__ == "__main__":
    asyncio.run(main())
