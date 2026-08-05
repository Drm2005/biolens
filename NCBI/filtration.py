import json
import os

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ServerError
from loguru import logger
from pydantic import BaseModel, Field, ValidationError


class ArticleAnalysis(BaseModel):
    article_id: str
    summary: str
    relevance_score: int = Field(ge=0, le=100)
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
    ARTICLE_ID: {pmid}

    ABSTRACT:
    {abstract}
    """
        for pmid, abstract in zip(batch["pmid"], batch["abstract"])
    )

    prompt = f"""
    Tu es un expert en biologie, pharmacologie et indexation MeSH.

    THÈME :
    [INSÈRE TON THÈME]

    Analyse chaque article indépendamment en utilisant uniquement les informations de son abstract.

    Pour chaque ARTICLE_ID :

    - produire un résumé scientifique fidèle ;
    - attribuer un score de pertinence entier entre 0 et 100 ;
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
        "mesh_keywords": ["..."]
    }}
    ]

    ARTICLES :

    {articles_text}
    """
    logger.info(f"Analyse de {len(batch)} articles with a total of {len(prompt)} token")

    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                top_k=20,
                top_p=0.95,
                response_mime_type="application/json",
                response_schema=list[ArticleAnalysis],
            ),
        )

        if not response.text:
            raise ValueError("empty response")

        raw_results = json.loads(response.text)

        results = []
        for r in raw_results:
            try:
                results.append(ArticleAnalysis.model_validate(r))
            except ValidationError as e:
                pmid = (
                    r.get("article_id", "inconnu") if isinstance(r, dict) else "inconnu"
                )
                logger.warning(f"Article {pmid} invalide, ignoré : {e}")

        valid_result = [r for r in results if r.summary]
        for r in results:
            if not r.summary:
                logger.warning(f"Résumé vide pour {r.article_id}, retry prévu")
            if not r.mesh_keywords:
                logger.warning(f"Mots-clés MeSH vides pour {r.article_id}")

        return valid_result
    except ServerError as e:
        logger.warning(f"Erreur serveur : {e}")

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"erreur json format{e}")
    return []
