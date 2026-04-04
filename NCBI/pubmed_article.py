import asyncio
from pathlib import Path

import httpx
import pandas as pd
from parsel import Selector
from pydantic import BaseModel, Field, field_validator

# ─────────────────────────────────────────
# MODEL
# ─────────────────────────────────────────


class Article(BaseModel):
    title: str | None = Field(min_length=5)
    abstract: str | None  # optional car souvent absent
    authors: list[str] = Field(default_factory=list)
    pmid: str  # PMID reste str (c'est un ID, pas un nombre à calculer)
    doi: str | None = None

    @field_validator("title", "abstract", "pmid", "doi", mode="before")
    @classmethod
    def verify(cls, v):
        if v is None:
            return "N/A"
        return str(v).strip()


# ─────────────────────────────────────────
# PMID FILE GESTION
# ─────────────────────────────────────────


async def read_pmid(path="pmid_list.txt"):
    file = Path(path)
    if not file.exists():
        return set()
    return set(file.read_text(encoding="utf-8").splitlines())


async def save_pmid(pmids: set[str], path="pmid_list.txt"):
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(f"{pmids}'\n'")


# ─────────────────────────────────────────
# RECHERCHE & FETCH PUBMED
# ─────────────────────────────────────────

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PubMedBot/1.0)"}
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


async def search_pmid(max_result: int = 40):
    seen_pmids = await read_pmid()
    query: str = input("entré votre rechercher: ")
    params = {"db": "pubmed", "term": query, "retmax": max_result, "retmode": "json"}
    async with httpx.AsyncClient(headers=HEADERS) as client:
        result = await client.get(ESEARCH, params=params)
        result.raise_for_status()
        data = result.json()
        pmids = data["esearchresult"]["idlist"]
        new_pmid = []
        for pmid in pmids:
            if pmid not in seen_pmids:
                seen_pmids.add(pmid)
                new_pmid.append(pmid)
        return new_pmid


def parse_article(response):
    sel = Selector(text=response, type="xml")
    art = sel.xpath("//PubmedArticle")

    if not art:
        return None
    authors = sel.xpath(".//AuthorList/Author")
    authors_list = []

    for author in authors:
        lastname = author.xpath("LastName/text()").get("")
        firstname = author.xpath("ForeName/text()").get("")
        authors_list.append((f"{firstname} {lastname}".strip()))

    return Article(
        title=art.xpath(".//ArticleTitle/text()").get(),
        abstract="".join(art.xpath(".//AbstractText//text()").getall()).strip(),
        authors=authors_list,
        pmid=art.xpath(".//PMID/text()").get("N/A"),
        doi=art.xpath(".//ArticleId[@IdType='doi']/text()").get(),
    )


async def fetch_article(client: httpx.AsyncClient, pmid):

    params = {"db": "pubmed", "id": pmid, "retmode": "xml", "rettype": "abstract"}
    response = await client.get(EFETCH, params=params)
    response.raise_for_status()
    return parse_article(response.text)


# ---------------------------------------------
# SAVE CSV
# ---------------------------------------------

CSV_FILE = Path("article.csv")


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
    print(f"{len(result)} article --> {CSV_FILE}")


# ---------------------------------------------
# MAIN
# ---------------------------------------------


async def main():
    pmids = await search_pmid()

    if not pmids:
        raise ValueError("Aucun PMID trouvé pour cette query")

    semaphore = asyncio.Semaphore(2)

    async def limited(client, pmid):
        async with semaphore:
            await asyncio.sleep(0.85)
            return await fetch_article(client, pmid)

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = [limited(client=client, pmid=pmid) for pmid in pmids]
        results = await asyncio.gather(*tasks)
        valid = [r for r in results if r is not None]
        await save_pmid({a.pmid for a in valid})
        return save_result(valid)


if __name__ == "__main__":
    asyncio.run(main())
