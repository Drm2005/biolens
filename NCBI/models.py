from pydantic import BaseModel, Field, field_validator


class Article(BaseModel):
    title: str | None = Field(default=None, min_length=5)
    abstract: str | None  # optional car souvent absent
    authors: list[str] = Field(default_factory=list)
    pmid: str  # PMID reste str (c'est un ID, pas un nombre à calculer)
    doi: str | None = None

    @field_validator("title", "abstract", "pmid", "doi", mode="before")
    @classmethod
    def verify(cls, v):
        if v is None:
            return None
        return str(v).strip()
