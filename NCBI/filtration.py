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


def analyse_batch(batch: pd.DataFrame) -> list[ArticleAnalysis]:
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

    Analyse chaque article indépendamment.

    Pour chaque ARTICLE_ID :
    - produire un résumé fidèle ;
    - attribuer un score de pertinence (0-100) ;
    - justifier ce score ;
    - extraire les principaux termes MeSH officiels ;
    - ne rien inventer.

    ARTICLES :

    {articles_text}
    """
    logger.info(f"Analyse de {len(batch)} articles with a total of {len(prompt)} token")
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

    raw_results = json.loads(response.text or "[]")
    results = [ArticleAnalysis.model_validate(result) for result in raw_results]
    return results
