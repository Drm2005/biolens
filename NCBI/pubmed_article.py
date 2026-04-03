import asyncio
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


async def search_pmid(max_result: int = 40):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    query: str = input("entré votre rechercher: ")
    params = {"db": "pubmed", "term": query, "retmax": max_result, "retmode": "json"}
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; PubMedBot/1.0)"}
    ) as client:
        result = await client.get(base_url, params=params)
        result.raise_for_status()
        data = result.json()

    return data["esearchresult"]["idlist"]


def parse_article(response):
    sel = Selector(text=response, type="xml")
    art = sel.xpath("//PubmedArticle")

    if not art:
        return None

    title = art.xpath(".//ArticleTitle/text()").get()
    abstract_to_clean = art.xpath(".//AbstractText//text()").getall()
    abstract = "".join(abstract_to_clean).strip()
    authors = art.xpath(".//AuthorList//text()").getall()
    pmid = art.xpath(".//PMID/text()").get("N/A")
    doi = art.xpath(".//ArticleId[@IdType='doi']/text()").get()

    return Article(title=title, abstract=abstract, authors=authors, pmid=pmid, doi=doi)


async def fetch_article(client: httpx.AsyncClient, pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml", "rettype": "abstract"}

    response = await client.get(url, params=params)
    response.raise_for_status()

    return parse_article(response.text)


def save_result(result):
    df = pd.DataFrame((a.model_dump()) for a in result)
    output_file = df.to_csv("article.csv", sep="|", encoding="utf-8", index=False)
    print(f"{len(result)} article --> {output_file}")


async def main():
    semaphore = asyncio.Semaphore(2)
    pmids = await search_pmid()

    async def limited(client, pmids):
        async with semaphore:
            await asyncio.sleep(0.85)
            return await fetch_article(client, pmids)

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        if not pmids:
            raise ValueError("Aucun PMID trouvé pour cette query")

        tasks = [limited(client=client, pmids=pmid) for pmid in pmids]
        result = await asyncio.gather(*tasks)

        return save_result(result)


if __name__ == "__main__":
    result = asyncio.run(main())
