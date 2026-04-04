import asyncio
from pathlib import Path

import httpx
import pandas as pd
from parsel import Selector
from pydantic import BaseModel, Field, field_validator


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


async def read_pmid(path="pmid_list.txt"):
    file = Path(path)

    if not file.exists():
        return set()

    return set(file.read_text(encoding="utf-8").splitlines())


async def save_pmid(pmids: set[str], path="pmid_list.txt"):
    with open(path, "a", encoding="utf-8") as f:
        for pmid in pmids:
            f.write(pmid + "\n")


# partie pmid consiste a la rechercher enregistrement puis le stockage pour eviter de retomber sur les meme la prochiane relance
async def search_pmid(max_result: int = 1):
    seen_pmids = await read_pmid()
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    query: str = input("entré votre rechercher: ")
    params = {"db": "pubmed", "term": query, "retmax": max_result, "retmode": "json"}
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; PubMedBot/1.0)"}
    ) as client:
        result = await client.get(base_url, params=params)
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

    title = art.xpath(".//ArticleTitle/text()").get()
    abstract_to_clean = art.xpath(".//AbstractText//text()").getall()
    abstract = "".join(abstract_to_clean).strip()
    authors = art.xpath(".//AuthorList//Author/text()").getall()
    pmid = art.xpath(".//PMID/text()").get() or "N/A"
    doi = art.xpath(".//ArticleId[@IdType='doi']/text()").get()

    return Article(title=title, abstract=abstract, authors=authors, pmid=pmid, doi=doi)


async def fetch_article(client: httpx.AsyncClient, pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml", "rettype": "abstract"}

    response = await client.get(url, params=params)
    response.raise_for_status()

    return parse_article(response.text)


def save_result(result):
    path = Path("article.csv")
    file_exist = path.exists()
    df = pd.DataFrame((a.model_dump()) for a in result)
    df.to_csv(
        path, mode="a", header=not file_exist, sep="|", encoding="utf-8", index=False
    )
    print(f"{len(result)} article --> {path}")


async def main():

    semaphore = asyncio.Semaphore(2)
    pmids = await search_pmid()

    async def limited(client, pmid):
        async with semaphore:
            await asyncio.sleep(0.85)
            return await fetch_article(client, pmid)

        if not pmids:
            raise ValueError("Aucun PMID trouvé pour cette query")

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = [limited(client=client, pmid=pmid) for pmid in pmids]
        results = await asyncio.gather(*tasks)
        valid = [r for r in results if r is not None]
        await save_pmid({a.pmid for a in valid})
        return save_result(valid)


if __name__ == "__main__":
    result = asyncio.run(main())
