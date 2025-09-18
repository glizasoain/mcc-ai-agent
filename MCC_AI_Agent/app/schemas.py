from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field


class Website(BaseModel):
	url: Optional[str] = None
	content: Optional[str] = None


class Profile(BaseModel):
	industry: Optional[str] = None
	vertical: Optional[str] = None
	country: Optional[str] = None
	existing_mcc: Optional[str] = None
	avg_ticket: Optional[float] = None
	volume_band: Optional[str] = None


WebsiteInput = Union[str, Website]


class RecommendRequest(BaseModel):
	merchant_id: str
	current_mcc: Optional[str] = None
	profile: Optional[Profile] = None
	website: Optional[WebsiteInput] = None
	websites: Optional[List[WebsiteInput]] = None
	merchant_description: Optional[str] = None
	force: Optional[bool] = False


class Provenance(BaseModel):
	model: Optional[str] = None
	prompt_hash: Optional[str] = None
	mcc_reference_version: Optional[str] = None


class RecommendResponse(BaseModel):
	merchant_id: str
	merchant_name: str
	current_mcc: str
	current_mcc_description: str
	recommended_mcc: str
	recommended_mcc_description: str
	confidence: int = Field(ge=0, le=100)
	business_analysis: str
	misclassification_reason: str
	recommendation_justification: str
	supporting_evidence: str
	needs_review: bool
	website_summary: Optional[str] = ""
	debug_prompt: Optional[str] = None
	agents_involved: Optional[List[str]] = []
	provenance: Provenance


# Additional API contracts (Phase 2 stubs)
class SubmitMerchantRequest(BaseModel):
	merchant_id: str
	merchant_name: str
	website: Optional[Website] = None
	profile: Optional[Profile] = None


class SubmitMerchantResponse(BaseModel):
	submitted: bool
	merchant_id: str


class GetRecommendationRequest(BaseModel):
	merchant_id: str


class GetRecommendationResponse(BaseModel):
	merchant_id: str
	recommendation: Optional[RecommendResponse] = None


class SimulateImpactRequest(BaseModel):
	mcc_from: str
	mcc_to: str
	cohort_size: Optional[int] = 1000


class SimulateImpactResponse(BaseModel):
	cohort_size: int
	summary: str


class ListRunsResponse(BaseModel):
	runs: List[Dict[str, Any]]


class GetRunResponse(BaseModel):
	run: Dict[str, Any]


class IngestProfileRequest(BaseModel):
	merchant_id: str
	profile: Profile


class IngestProfileResponse(BaseModel):
	merchant_id: str
	ingested: bool
