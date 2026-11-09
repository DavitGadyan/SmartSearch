from pydantic import BaseModel, Field


class ProductOut(BaseModel):
    id: int
    name: str
    product_class: str | None = None
    brand: str | None = None
    price: float
    rating: float | None = None
    review_count: int = 0
    in_stock: bool = True
    is_new: bool = False
    attributes: dict = Field(default_factory=dict)
    image_url: str | None = None
    position: int | None = None
    score: float | None = None
    explanation: dict | None = None


class ProductDetail(ProductOut):
    description: str | None = None
    category_hierarchy: str | None = None
    similar: list[ProductOut] = Field(default_factory=list)


class FacetValue(BaseModel):
    value: str
    count: int


class Facet(BaseModel):
    name: str
    values: list[FacetValue]


class SearchResponse(BaseModel):
    request_id: str
    query: str
    parsed: dict
    total: int
    page: int
    page_size: int
    items: list[ProductOut]
    facets: list[Facet]
    strategy: str
    variant: str | None = None
    experiment_key: str | None = None
    ranking_model_version: str
    retrieval: dict = Field(default_factory=dict)
    latency_ms: float
    explored_product_id: int | None = None


class Suggestion(BaseModel):
    text: str
    kind: str  # query | category | product


class SuggestResponse(BaseModel):
    prefix: str
    suggestions: list[Suggestion]
