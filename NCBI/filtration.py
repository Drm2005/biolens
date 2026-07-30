import json
import os

import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from models import ArticleAnalysis

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
Tu es un expert en analyse de la littérature scientifique,
 en biologie, pharmacologie et indexation biomédicale MeSH.

THÈME DE RECHERCHE :
[INSÈRE TON THÈME DE RECHERCHE ICI]

Tu dois analyser chaque article indépendamment.

RÈGLES IMPORTANTES :

1. Analyse chaque article séparément.
2. Ne mélange jamais les informations entre différents articles.
3. Utilise uniquement les informations présentes dans l'abstract.
4. N'invente aucune information.
5. Retourne exactement un objet JSON pour chaque ARTICLE_ID.
6. Conserve exactement l'ARTICLE_ID fourni.
7. Le score de pertinence doit être un nombre entier entre 0 et 100.

Pour chaque article :

- Produis un résumé scientifique fidèle et informatif.
- Conserve les informations importantes concernant :
  maladies, molécules, médicaments, plantes, organismes,
  mécanismes biologiques, cibles moléculaires, méthodes,
  résultats et conclusions.
- Donne un score de pertinence par rapport au thème de recherche.
- Donne une justification courte du score.
- Identifie les mots-clés biomédicaux importants.
- Utilise les termes MeSH officiels lorsqu'un terme MeSH approprié existe.
- N'invente jamais de terme MeSH.
- Évite les doublons et les synonymes redondants.

FORMAT JSON OBLIGATOIRE :

[
  {{
    "article_id": "ARTICLE_ID",
    "summary": "Résumé scientifique fidèle",
    "relevance_score": 0,
    "relevance_justification": "Justification courte",
    "mesh_keywords": [
      "Keyword 1",
      "Keyword 2"
    ]
  }}
]

IMPORTANT :

- Retourne uniquement du JSON valide.
- Ne retourne aucun Markdown.
- Ne retourne pas ```json.
- Ne retourne aucune explication avant ou après le JSON.

ARTICLES À ANALYSER :

{articles_text}
"""

    response = client.models.generate_content(
        model="gemma-4-26b-a4b-it",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            top_p=0.95,
            top_k=20,
        ),
    )

    raw_results = json.loads(response.text or "[]")

    results = [ArticleAnalysis.model_validate(result) for result in raw_results]
    return results
