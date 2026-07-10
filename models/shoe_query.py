from pydantic import BaseModel, model_validator
from typing import Optional, Literal


class ShoeQuery(BaseModel):
    brand: Optional[str] = None
    model_name: Optional[str] = None          # renamed from "model" — Pydantic reserves that word
    size: Optional[float] = None               # float, not int — some sizes are e.g. 9.5
    size_unit: Optional[Literal["US", "UK", "EU"]] = None
    condition_score: Optional[int] = None      # 1–10
    source: Literal["text", "photo"]
    confidence: Optional[float] = None         # 0.0–1.0, only relevant when source == "photo"
    raw_input: str

    @model_validator(mode="after")
    def must_have_brand_or_model(self):
        if not self.brand and not self.model_name:
            raise ValueError("Cannot create ShoeQuery without at least a brand or model.")
        return self
