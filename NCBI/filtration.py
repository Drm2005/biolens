import asyncio
import json
import os

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel, Field


class ArticleAnalysis(BaseModel):
    article_id: str
    summary: str
    relevance_score: int = Field(ge=0, le=100)
    relevance_justification: str
    mesh_keywords: list[str]


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI API KEY is not found")

client = genai.Client(api_key=api_key)


async def analyse_batch(batch: pd.DataFrame) -> list[ArticleAnalysis]:
    """
    Analyse plusieurs abstracts dans une seule requête API.
    """

    articles_text = "\n\n".join(
        f"""
    ARTICLE_ID: {row["pmid"]}

    ABSTRACT:
    {row["abstract"]}
    """
        for _, row in batch.iterrows()
    )

    prompt = f"""
    Tu es un expert en biologie, pharmacologie et indexation MeSH.

    THÈME :
    [INSÈRE TON THÈME]

    Analyse chaque article indépendamment en utilisant uniquement les informations de son abstract.

    Pour chaque ARTICLE_ID :

    - produire un résumé scientifique fidèle ;
    - attribuer un score de pertinence entier entre 0 et 100 ;
    - justifier brièvement ce score ;
    - extraire les principaux termes MeSH officiels lorsqu'ils existent ;
    - ne jamais inventer d'information.

    RÈGLES OBLIGATOIRES :

    - répondre UNIQUEMENT avec un tableau JSON valide ;
    - un objet par ARTICLE_ID ;
    - conserver exactement l'ARTICLE_ID fourni ;
    - respecter exactement les noms des champs ;
    - ne retourner aucun texte avant ou après le JSON ;
    - ne retourner aucun Markdown ;
    - ne jamais utiliser ```json.

    Format attendu :

    [
    {{
        "article_id": "...",
        "summary": "...",
        "relevance_score": 0,
        "relevance_justification": "...",
        "mesh_keywords": ["..."]
    }}
    ]

    ARTICLES :

    {articles_text}
    """
    logger.info(f"Analyse de {len(batch)} articles with a total of {len(prompt)} token")
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemma-4-31b-it",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=list[ArticleAnalysis],
                ),
            )

            logger.info(f"analyse start with{len(prompt)}token")
            if not response.text:
                raise ValueError("response empty")

            raw_results = json.loads(response.text or "[]")
            results = [ArticleAnalysis.model_validate(result) for result in raw_results]
            excepted = set(batch["pmid"].astype(str))
            returned = {r.article_id for r in results}
            if excepted != returned:
                raise ValueError("not all article in the batch has been analyse")
            if any(not r.summary for r in results):
                raise ValueError("Empty summary")
            if any(not r.mesh_keywords for r in results):
                logger.warning(f"{'empty key word'}")

            return results
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"erreur json format{e}")
            await asyncio.sleep(2**attempt)
    logger.info("echec apres 3 tentative")
    return []
