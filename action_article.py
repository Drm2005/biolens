import asyncio
import logging
from typing import Optional

import httpx
import nodriver as uc
import pandas as pd
from parsel import Selector
from pydantic import BaseModel, field_validator


class Article(BaseModel):
    title: str
    url: str
    date: str
    abstract: list[str]

    @field_validator("title", "date", mode="before")
    @classmethod
    def strip_or_defaut(cls, v):
        if v is None:
            return "N/A"
        return str(v).strip()

    def __str__(self):
        return f"{self.date} {self.title}"


class BaseScraper:
    def __init__(
        self,
        output_file: str = "output.csv",
        headless: bool = True,
        max_click: int = 10,
    ):
        self.output_file = output_file
        self.headless = headless
        self.max_click = max_click
        self.browser: Optional[uc.Browser] = None
        self.tab: Optional[uc.Tab]
        self.result: list[Article] = []
        self.browser_args = [
            "--blink-settings=imagesEnabled=false",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

    async def start(self):
        logging.info(f"{self.__class__.__name__} a démmarer le browser")
        self.browser = await uc.start(browser_args=self.browser_args)

    async def scrape(self):
        raise NotImplementedError(
            f"{self.__class__.__name__} doit implementer leur propre scraper"
        )

    async def stop(self):
        if self.browser:
            self.browser.stop()
            logging.info(f"{self.__class__.__name__} a fermer le browser")

    def to_csv(self):
        if not self.result:
            print("aucun résultat ")
            return

        df = pd.DataFrame([a.model_dump() for a in self.result])
        df.to_csv(self.output_file, index=False, encoding="utf_8")
        print(f"{len(self.result)} article --> {self.output_file}")

    async def run(self) -> list[Article]:
        await self.start()
        try:
            self.result = await self.scrape()
        finally:
            await self.stop()
        self.to_csv()
        return self.result

    ## ── CLASSES FILLES ─────────────────────(Fonctions use in both next 2 classes)──────────────────────────────────────

    async def load_all_articles(self, text, selector):
        if self.tab is None:
            # Si c'est None, on arrête tout avec une erreur claire
            raise RuntimeError("L'onglet (tab) n'est pas initialisé !")

        await self.tab.wait_for(text, timeout=12)
        clicks = 0
        while clicks < self.max_click:
            html_before = await self.tab.get_content()
            count_before = html_before.count(selector)

            await self.tab.scroll_down(400)
            await asyncio.sleep(0.5)
            try:
                btn = await self.tab.find(
                    "button.float-right.rounded-md.py-3.text-base", timeout=5
                )
            except Exception:
                logging.info(f"✅ Fin du chargement après {clicks} clicks")
                break

            if not btn:
                break
            await btn.click()
            clicks += 1
            print(f"[CLICK {clicks}] Attente nouveaux articles...")

            for _ in range(10):
                await asyncio.sleep(1)
                html_after = await self.tab.get_content()
                count_after = html_after.count("article")

                if count_after > count_before:
                    print(f"{count_after}--> {count_before} articles")
                    break
            else:
                print("print Timeout end")
                break

    async def fetch_article(
        self, xpath: str, client: httpx.AsyncClient, url: str, title: str, date: str
    ):

        abstract = []
        for attemp in range(3):
            try:
                r = await client.get(url=url)
                r.raise_for_status()
                sel = Selector(text=r.text)
                abstract = sel.xpath(xpath).getall()
                break

            except Exception as e:
                print(f"[ERROR] {url} → {e}")
                if attemp < 3:
                    await asyncio.sleep(attemp * 2)

        return Article(title=title, url=url, date=date, abstract=abstract)


class KitcoScraper(BaseScraper):
    def __init__(
        self, max_click: int = 10, output_file: str = "kitko.csv", headless: bool = True
    ):
        super().__init__(output_file=output_file, headless=headless)
        self.max_click = max_click
        self.base_url = "https://www.kitco.com"

    async def scrape(self) -> list[Article]:
        if self.browser is None:
            raise RuntimeError("le browser n'est pas initialisé !")

        self.tab = await self.browser.get(f"{self.base_url}/news/digest#metals")
        await self.load_all_articles(text="Metals News", selector="article")

        html = await self.tab.get_content()
        sel = Selector(text=html)

        articles_raw = []
        for art in sel.css("div.DigestNews_newItem__K4a83"):
            href = art.css("a::attr(href)").get()
            if not href:
                continue
            url = href if href.startswith("https") else f"{self.base_url}/{href}"
            title = art.xpath(".//h5/text()").get()
            date = art.xpath("./p[contains(@class,'text-gray-500')]//text()").get()
            articles_raw.append((url, title, date))

        print(f"📰 {len(articles_raw)} articles trouvés")

        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True, cookies=None
        ) as client:
            tasks = [
                self.fetch_article(
                    "//div[contains(@id, 'articleBody')]//p//text()", client, u, t, d
                )
                for u, t, d in articles_raw
            ]
            return await asyncio.gather(*tasks)


class InvestingScraper(BaseScraper):
    def __init__(
        self,
        category: str = "commodities",
        output_file: str = "investing.csv",
        headless: bool = False,
    ):
        super().__init__(output_file=output_file, headless=headless)
        self.category = category
        self.base_url = "https://www.investing.com"

    async def scrape(self) -> list[Article]:

        if self.browser is None:
            raise RuntimeError("le browser n'est pas initialisé !")

        self.tab = await self.browser.get(url=self.base_url + self.category)
        await self.load_all_articles(text="Metals News", selector="article")
        html = await self.tab.get_content()
        sel = Selector(text=html)

        articles_raw = []
        for article in sel.css("article"):
            title = article.css("h3::text()").get()
            href = article.css("a::attr(href)").get()
            if not href:
                continue
            url = href if href.startswith("http") else f"{self.base_url}/{href}"
            date = article.css("time::text()").get()

            articles_raw.append((title, url, date))

        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True
        ) as client:
            tasks = [
                self.fetch_article(
                    "//div[contains(@id, 'articleBody')]//p//text()",
                    client,
                    title,
                    url,
                    date,
                )
                for title, url, date in articles_raw
            ]
            self.result = await asyncio.gather(*tasks)
            return self.result


async def main():
    kitko = KitcoScraper(output_file="kitko_investissemnt.csv", headless=True)

    investing = InvestingScraper(
        category="life_science", output_file="investing.csv", headless=True
    )

    for scraping in [kitko, investing]:
        await scraping.run()


if __name__ == "__main__":
    asyncio.run(main())
