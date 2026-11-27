"""Web request contracts. No media decoding, model loading or execution."""
from typing import Literal, Annotated
from urllib.parse import urlsplit, parse_qs
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True,allow_inf_nan=False)

def drive_link(value):
    try:
        u=urlsplit(value)
        if u.scheme!="https" or u.netloc!="drive.google.com" or u.fragment:
            raise ValueError()
        if re.fullmatch(r"/(?:file/d|drive/(?:u/\d+/)?folders)/[A-Za-z0-9_-]{10,200}(?:/view|/edit)?/?",u.path):
            return value
        if u.path in ("/open","/uc") and len(parse_qs(u.query).get("id",[]))==1 and re.fullmatch(r"[A-Za-z0-9_-]{10,200}",parse_qs(u.query)["id"][0]):
            return value
    except (ValueError,TypeError):
        pass
    raise ValueError("Use an HTTPS Google Drive file or folder link")

def youtube_link(value):
    """Only canonical single-video HTTPS links, never arbitrary URLs or playlists."""
    try:
        u=urlsplit(value)
        if u.scheme!="https" or u.fragment:
            raise ValueError()
        if u.netloc in ("www.youtube.com","youtube.com","m.youtube.com") and u.path=="/watch":
            ids=parse_qs(u.query).get("v",[])
            vid=ids[0] if len(ids)==1 else ""
        elif u.netloc=="youtu.be":
            vid=u.path.removeprefix("/")
        else:
            raise ValueError()
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}",vid):
            raise ValueError()
        return "https://www.youtube.com/watch?v="+vid
    except (TypeError,ValueError,AttributeError):
        raise ValueError("Use a single HTTPS YouTube video link") from None

class Input(Strict):
    source: str=Field(min_length=1,max_length=2048)
    source_kind: Literal["auto","video","zip","folder","youtube"]="video"
    output_folder: str | None=Field(default=None,max_length=2048)
    @field_validator("output_folder")
    @classmethod
    def validate_link(cls,v):
        return drive_link(v) if v is not None else None
    @model_validator(mode="after")
    def kind(self):
        if self.output_folder and "/folders/" not in urlsplit(self.output_folder).path:
            raise ValueError("Output destination must be a Drive folder")
        if self.source_kind=="auto":
            host=urlsplit(self.source).netloc
            if host in ("www.youtube.com","youtube.com","m.youtube.com","youtu.be"):
                self.source_kind="youtube"
            elif "/folders/" in urlsplit(self.source).path:
                self.source_kind="folder"
        if self.source_kind=="youtube":
            self.source=youtube_link(self.source)
            return self
        self.source=drive_link(self.source)
        if ("/folders/" in urlsplit(self.source).path)!=(self.source_kind=="folder"):
            raise ValueError("Source type must match the Drive file or folder link")
        return self

class Range(Strict):
    start_ms: int=Field(ge=0,le=86400000)
    end_ms: int=Field(gt=0,le=86400000)
    @model_validator(mode="after")
    def valid(self):
        if self.end_ms<=self.start_ms: raise ValueError("End must exceed start")
        return self

class Extractor(Strict):
    kind: Literal["extractor"]="extractor"
    mode: Literal["reference","manual"]="reference"
    reference_link: str | None=Field(default=None,max_length=2048)
    reference_uploads: list[Annotated[str,Field(pattern=r"^[a-f0-9]{64}$")]]=Field(default_factory=list,max_length=12)
    threshold: float=Field(default=.40,ge=0,le=1)
    scan_quality: Literal["rapid","balanced","thorough"]="balanced"
    ranges: list[Range]=Field(default_factory=list,max_length=1000)
    gpu_clip_extraction: bool=True
    cut_mode: Literal["accurate","copy"]="accurate"
    stitched: bool=False
    include_audio: bool=True
    quality: int=Field(default=100,ge=50,le=100)
    max_short_side: Literal[0,720,1080,1440]=0
    framing: Literal["whole","dynamic","landscape","portrait","square"]="whole"
    minimum_ms: int | None=Field(default=None,ge=100,le=600000)
    maximum_ms: int | None=Field(default=None,ge=100,le=600000)
    @field_validator("reference_link")
    @classmethod
    def validate_reference(cls,v): return drive_link(v) if v is not None else None
    @model_validator(mode="after")
    def check(self):
        if (self.mode=="reference" or self.framing!="whole") and not (self.reference_link or self.reference_uploads):
            raise ValueError("Reference images required")
        if not self.gpu_clip_extraction and self.framing!="whole":raise ValueError("VPS extraction supports Whole picture framing only; enable GPU for person framing")
        if self.mode=="manual" and not self.ranges: raise ValueError("Manual ranges required")
        if self.mode=="reference" and self.ranges: raise ValueError("Reference scan cannot include manual ranges")
        ordered=sorted(self.ranges,key=lambda r:r.start_ms)
        if any(a.end_ms>b.start_ms for a,b in zip(ordered,ordered[1:])): raise ValueError("Overlapping ranges")
        if (self.minimum_ms is None)!=(self.maximum_ms is None): raise ValueError("Both duration limits required")
        if self.minimum_ms is not None and (self.minimum_ms>self.maximum_ms or self.cut_mode!="accurate" or self.stitched or self.framing!="whole"):
            raise ValueError("Strict limits require accurate separate whole-picture clips and valid bounds")
        return self

class Region(Strict):
    x: float=Field(ge=0,lt=1)
    y: float=Field(ge=0,lt=1)
    w: float=Field(gt=0,le=1)
    h: float=Field(gt=0,le=1)
    @model_validator(mode="after")
    def check(self):
        if self.x+self.w>1.00000001 or self.y+self.h>1.00000001: raise ValueError("Region outside frame")
        return self

class Analyzer(Strict):
    kind: Literal["analyzer"]="analyzer"
    sample_interval_ms: int=Field(default=1000,ge=250,le=10000)
    similarity_threshold: float=Field(default=.50,ge=0,le=1)
    dominant_face_ratio: float=Field(default=2.5,ge=1.1,le=20)
    ignore_background_faces: bool=False
    ignore_static_faces: bool=False
    ignore_regions: list[Region]=Field(default_factory=list,max_length=32)
    reference_link: str | None=Field(default=None,max_length=2048)
    reference_uploads: list[Annotated[str,Field(pattern=r"^[a-f0-9]{64}$")]]=Field(default_factory=list,max_length=12)
    @field_validator("reference_link")
    @classmethod
    def validate_reference(cls,v): return drive_link(v) if v is not None else None

class JobRequest(Strict):
    input: Input
    settings: Annotated[Extractor|Analyzer,Field(discriminator="kind")]
    request_id: str=Field(pattern=r"^[a-f0-9]{32}$")
    @model_validator(mode="after")
    def check(self):
        if self.settings.reference_link and self.settings.reference_uploads:
            raise ValueError("Choose Drive or uploaded references, not both")
        if isinstance(self.settings,Extractor) and self.settings.mode=="manual" and self.input.source_kind not in ("auto","video","youtube"):
            raise ValueError("Manual ranges require a single video source")
        if self.input.source_kind=="youtube" and isinstance(self.settings,Extractor) and self.settings.include_audio:
            raise ValueError("YouTube intake is video-only; select Remove audio")
        return self
