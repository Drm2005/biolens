from pydantic import BaseModel, Field, field_validator


class Article(BaseModel):
    title: str | None = Field(default=None, min_length=5)
    abstract: str | None  # optional car souvent absent
    authors: list[str] = Field(default_factory=list)
    pmid: str  # PMID reste str (c'est un ID, pas un nombre à calculer)
    doi: str | None = None
    key_word: list[str] | str = []
    query: str | None = None

    @field_validator("title", "abstract", "pmid", "doi", mode="before")
    @classmethod
    def verify(cls, v):
        if v is None:
            return None
        return str(v).strip()


class Relation(BaseModel):
    source: str
    relation: str
    target: str


class ArticleAnalysis(BaseModel):
    article_id: str
    summary: str
    relevance_score: int = Field(ge=0, le=100)
    genes: list[str]
    proteins: list[str]
    drugs: list[str]
    relations: list[Relation]
