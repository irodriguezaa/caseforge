from datetime import date, datetime

from pydantic import BaseModel, Field


class QcMatrixSummary(BaseModel):
    id: int
    code: str
    version: str
    name: str
    status: str
    generated_on: date | None = None
    published_at: datetime | None = None
    published_by: str | None = None
    module_count: int = 0
    device_count: int = 0
    case_count: int = 0


class QcMatrixModuleRead(BaseModel):
    module_key: str
    group_name: str
    name: str
    description: str
    related: list[str] = Field(default_factory=list)


class QcMatrixDeviceRead(BaseModel):
    code: str
    label: str
    screen: str
    mdp_mx: list[str] = Field(default_factory=list)
    mdp_other_regions: list[str] = Field(default_factory=list)


class QcMatrixCaseRead(BaseModel):
    id: int
    base_id: str | None = None
    module_key: str
    title: str
    steps: str
    expected: str
    severity: str
    smoke: bool
    region: str | None = None
    platforms: list[str] = Field(default_factory=list)
    platform_notes: dict[str, str] = Field(default_factory=dict)


class QcMatrixPreviewRequest(BaseModel):
    platform: str = ""
    validation_type: str | None = None
    touched_modules: list[str] | None = None
    template_values: dict[str, str] | None = None
    raw_analysis: dict | None = None
    release_id: int | None = None


class QcMatrixCasePreview(BaseModel):
    base_id: str | None = None
    module_key: str
    title: str
    steps: str
    expected: str
    severity: str
    smoke: bool
    region: str | None = None
    provider: str | None = None
    pending_templates: list[str] = Field(default_factory=list)


class QcMatrixPreviewModule(QcMatrixModuleRead):
    device_case_count: int = 0


class QcMatrixSuggestionRead(BaseModel):
    module_key: str
    matched_words: list[str] = Field(default_factory=list)


class QcMatrixPreview(BaseModel):
    platform: str
    device_code: str
    matrix_code: str
    matrix_version_id: int | None = None
    matrix_version: str
    matrix_status: str
    region: str
    validation_type: str
    suggested_modules: list[str]
    suggestions: list[QcMatrixSuggestionRead] = Field(default_factory=list)
    touched_modules: list[str]
    related_modules: list[str]
    payment_methods_mx: list[str]
    transactions_included: bool
    template_values: dict[str, str]
    providers_applied: list[str] = Field(default_factory=list)
    modules: list[QcMatrixPreviewModule] = Field(default_factory=list)
    case_count: int
    cases: list[QcMatrixCasePreview]
    note: str
    impact_summary: str = ""
    show_module_selector: bool = False
    deduplicated: bool = False


class QcMatrixSelectionUpdate(BaseModel):
    touched_modules: list[str] | None = None
    template_values: dict[str, str] | None = None


class QcMatrixDetail(QcMatrixSummary):
    modules: list[QcMatrixModuleRead]
    devices: list[QcMatrixDeviceRead]
    cases: list[QcMatrixCaseRead]
