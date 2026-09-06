from pydantic import BaseModel, Field


class MaterialSummary(BaseModel):
    file_id: int
    name: str
    revision: str
    kind: str
    total_parts: int
    indexed_chars: int
    partial: bool
    warnings: list[str]


class MaterialPart(BaseModel):
    part: int
    location: str
    text: str
    citation: str
    target_path: str


class MaterialRead(BaseModel):
    document: MaterialSummary
    parts: list[MaterialPart]
    next_call: dict | None
    boundary: str


class MaterialHit(BaseModel):
    file_id: int
    name: str
    part: int
    location: str
    revision: str
    excerpt: str
    score: int
    next_call: dict


class MaterialSearch(BaseModel):
    query: str
    hits: list[MaterialHit]
    errors: list[dict]
    documents: list[MaterialSummary]
    coverage: dict
    next_call: dict | None
    boundary: str


class SourceReference(BaseModel):
    source_id: int = Field(gt=0)
    part: int = Field(gt=0)
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    quote: str = Field(min_length=1, max_length=500)
