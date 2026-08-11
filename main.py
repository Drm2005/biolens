import asyncio
import json
import time
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

    # Temps de démarrage
    start_time = time.perf_counter()

    # Compteurs
    total_pmids = 0
    total_articles_fetched = 0
    total_articles_analysed = 0

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

                # Compteur
                total_pmids += len(pmids)

                for pmid in pmids:
                    pmid_to_query[pmid] = query

                all_pmids.extend(pmids)

                await asyncio.sleep(8)

            # Supprime les doublons
            all_pmids = list(dict.fromkeys(all_pmids))

            if not all_pmids:
                logger.error(f"[{group}] aucun PMID, skip")
                continue

            chunks = [all_pmids[i : i + BATCH] for i in range(0, len(all_pmids), BATCH)]

            tasks = [limited(client, chunk) for chunk in chunks]

            for task in asyncio.as_completed(tasks):
                results = await task

                # Compteur d'articles récupérés
                total_articles_fetched += len(results)

                for article in results:
                    article.query = pmid_to_query.get(article.pmid)

                save_result(results)

                save_pmid({a.pmid for a in results})

                logger.info(f"Articles récupérés : {total_articles_fetched}")

    logger.success("gemini analyse starts")

    for attemp in range(3):
        df = pd.read_csv(CSV_FILE, encoding="utf-8", sep="|")

        df = df[df["abstract"].notna()]

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

                    # Compteur d'articles analysés
                    total_articles_analysed += len(results)

                    df_chunk["summary"] = None

                    if "relevance_score" not in df_chunk:
                        df_chunk["relevance_score"] = None

                    df_chunk["genes"] = None

                except Exception as e:
                    logger.exception(e)

                    continue

                df_chunk["summary"] = None
                df_chunk["relevance_score"] = None

                df_chunk["relations"] = df_chunk["relations"].astype("object")

                df_chunk["drugs"] = None

                df_chunk["summary"] = df_chunk["summary"].astype("object")

                df_chunk["drugs"] = df_chunk["drugs"].astype("object")

                for par in results:
                    mask = df_chunk["pmid"] == par.article_id

                    df_chunk.loc[mask, "summary"] = par.summary

                    df_chunk.loc[mask, "relevance_score"] = par.relevance_score

                    df_chunk.loc[mask, "genes"] = ",".join(par.genes)

                    df_chunk.loc[mask, "drugs"] = ",".join(par.drugs)

                    df_chunk.loc[mask, "relations"] = json.dumps(
                        [relation.model_dump() for relation in par.relations],
                        ensure_ascii=False,
                    )

                df["genes"] = ""
                df["proteins"] = ""
                df["drugs"] = ""
                df["relations"] = ""

                df_chunk = df_chunk[df_chunk["summary"].notnull()]

                df_chunk.to_csv(
                    final_csv,
                    mode="a",
                    header=not Path(final_csv).exists(),
                    sep="|",
                    encoding="utf-8",
                    index=False,
                )

                logger.info(f"Articles analysés : {total_articles_analysed}")

        logger.info(f"Part saved in {final_csv}")

    # ---------------------------------------------
    # STATISTIQUES FINALES
    # ---------------------------------------------

    elapsed_time = time.perf_counter() - start_time

    logger.success(
        "\n"
        "══════════════════════════════════════\n"
        "           PROGRAM COMPLETED\n"
        "══════════════════════════════════════\n"
        f"PMIDs found       : {total_pmids}\n"
        f"Articles retrieved  : {total_articles_fetched}\n"
        f"Articles analysed   : {total_articles_analysed}\n"
        f"Total time         : {elapsed_time:.2f} seconds\n"
        f"Total time          : {elapsed_time / 60:.2f} minutes\n"
        "══════════════════════════════════════"
    )


if __name__ == "__main__":
    asyncio.run(main())
