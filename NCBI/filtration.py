import json
import os

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ServerError
from loguru import logger
from pydantic import ValidationError

from NCBI.models import ArticleAnalysis

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI API KEY is not found")

client = genai.Client(api_key=api_key)


async def analyse_batch(batch: pd.DataFrame, query) -> list[ArticleAnalysis]:
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
    Tu es expert en biologie moléculaire, génétique et pharmacologie.

    THÈME DE RECHERCHE : {query}

    Analyse chaque article indépendamment, en utilisant EXCLUSIVEMENT les informations présentes dans son abstract.

    Pour chaque article :

    1. RÉSUMÉ
    - Résume fidèlement les résultats et objectifs principaux.
    - N'ajoute aucune information absente de l'abstract.

    2. PERTINENCE
    - Attribue un score entier de 0 à 100 selon la pertinence de l'article par rapport au thème.
    - 0 = aucune pertinence ; 100 = directement pertinent.

    3. ENTITÉS
    Extrais uniquement les entités explicitement mentionnées :
    - genes : symboles/noms de gènes explicitement cités ;
    - proteins : protéines explicitement citées ;
    - drugs : médicaments ou molécules explicitement cités.

    4. RELATIONS
    Extrais uniquement les relations explicitement établies dans l'abstract entre les entités extraites.
    Types possibles :
    - gene-disease
    - drug-disease
    - gene-protein
    - drug-protein
    - gene-drug
    - protein-disease

    N'infère aucune relation à partir de connaissances externes.
    Une entité ou une relation non explicitement présente dans l'abstract ne doit jamais être ajoutée.

    RÈGLES DE SORTIE :
    - Retourne uniquement un JSON valide.
    - Un objet par article.
    - Conserve exactement chaque article_id fourni.
    - Respecte exactement les noms et types des champs.
    - genes, proteins, drugs et relations doivent toujours être des listes.
    - Si aucune entité ou relation n'est trouvée, retourne [].
    - relevance_score doit être un entier entre 0 et 100.
    - Aucun Markdown, commentaire ou texte hors JSON.

    STRUCTURE :
    [
        {{
            "article_id": "...",
            "summary": "...",
            "relevance_score": 0,
            "genes": [],
            "proteins": [],
            "drugs": [],
            "relations": [
                {{
                    "entity_1": "...",
                    "entity_2": "...",
                    "relation_type": "..."
                }}
            ]
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

        return valid_result
    except ServerError as e:
        logger.warning(f"Erreur serveur : {e}")

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"erreur json format{e}")
    return []
