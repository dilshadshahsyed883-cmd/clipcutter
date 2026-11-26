"""Transport-independent request contract; no host paths or credentials in job JSON."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

class Options(StrictModel):
    threshold: float = Field(default=0.40, ge=0, le=1)
    scan_quality: Literal["rapid", "balanced", "thorough"] = "balanced"
    mode: Literal["copy", "accurate"] = "accurate"
    stitched: bool = False
    include_audio: bool = True
    quality: int = Field(default=100, ge=50, le=100)
    max_short_side: Literal[0,720,1080,1440] = 0
    framing: Literal["whole","dynamic","landscape","portrait","square"] = "whole"
    minimum_ms: int | None = Field(default=None, ge=100, le=600000)
    maximum_ms: int | None = Field(default=None, ge=100, le=600000)

    @model_validator(mode="after")
    def limits_valid(self):
        if (self.minimum_ms is None) != (self.maximum_ms is None):
            raise ValueError("Both clip limits must be provided")
        if self.minimum_ms is not None:
            if self.minimum_ms > self.maximum_ms:
                raise ValueError("Minimum exceeds maximum")
            if self.framing != "whole" or self.stitched:
                raise ValueError("Strict clip limits require separate whole-picture output")
            if self.mode != "accurate":
                raise ValueError("Strict clip limits require accurate cutting")
        return self

class Range(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    @model_validator(mode="after")
    def valid_range(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("Clip end must exceed start")
        return self

class ScanManifest(StrictModel):
    options: Options = Field(default_factory=Options)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    references_sha256: list[str] = Field(min_length=1, max_length=12)
    @model_validator(mode="after")
    def valid_digests(self):
        import re
        if any(not re.fullmatch(r"[a-f0-9]{64}", x) for x in self.references_sha256):
            raise ValueError("Invalid reference digest")
        return self

class ReviewManifest(StrictModel):
    options: Options = Field(default_factory=Options)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    ranges: list[Range] = Field(min_length=1, max_length=1000)
    references_sha256: list[str] = Field(default_factory=list, max_length=12)
    @model_validator(mode="after")
    def valid_review(self):
        import re
        if any(not re.fullmatch(r"[a-f0-9]{64}", x) for x in self.references_sha256):
            raise ValueError("Invalid reference digest")
        if self.framing_requested and not self.references_sha256:
            raise ValueError("Person framing requires reference images")
        ordered = sorted(self.ranges, key=lambda r:r.start_ms)
        if any(a.end_ms > b.start_ms for a,b in zip(ordered, ordered[1:])):
            raise ValueError("Overlapping reviewed ranges")
        return self
    @property
    def framing_requested(self):
        return self.options.framing != "whole"
