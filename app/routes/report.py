"""Informe técnico de la medición en PDF (CU-10, RF-28)."""

from fastapi import APIRouter, HTTPException, Response, status

from app.core.deps import CurrentUserDep, DbDep
from app.services.project_service import NotFoundError
from app.services.report_service import ReportService

router = APIRouter(tags=["Informe técnico"])


@router.get(
    "/surveys/{survey_id}/report.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Informe técnico en PDF"}},
)
async def survey_report_pdf(survey_id: int, db: DbDep, user: CurrentUserDep) -> Response:
    """Informe técnico: datos, método, plano, resultados con incertidumbre, validación y coordenadas."""
    try:
        content = await ReportService(db, user).pdf(survey_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado") from None
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="metrik_informe_{survey_id}.pdf"'},
    )
