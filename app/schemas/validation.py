from pydantic import BaseModel, Field


class WallReferenceIn(BaseModel):
    wall_index: int = Field(ge=0, description="Índice del muro (0 = primer muro del recorrido)")
    readings_m: list[float] = Field(min_length=1, max_length=5, description="Lecturas de wincha en metros")
    notes: str | None = Field(default=None, max_length=255)


class ReferencesIn(BaseModel):
    walls: list[WallReferenceIn] = Field(min_length=1)
    real_area_m2: float | None = Field(default=None, gt=0)


class WallComparisonOut(BaseModel):
    wall_index: int
    measured_m: float
    real_m: float
    error_m: float
    abs_error_m: float
    rel_error_pct: float
    readings_m: list[float]
    needs_extra_reading: bool


class ErrorReportOut(BaseModel):
    n: int
    mae_m: float
    rmse_m: float
    bias_m: float
    std_m: float
    mean_rel_error_pct: float
    max_abs_error_m: float
    max_rel_error_pct: float
    area_error_pct: float | None
    meets_target: bool
    target_pct: float
    walls: list[WallComparisonOut]


class SurveyValidationOut(BaseModel):
    survey_id: int
    survey_name: str
    report: ErrorReportOut
    warnings: list[str]


class ProjectValidationOut(BaseModel):
    project_id: int
    surveys_validated: int
    report: ErrorReportOut
