from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.ai.base import AIClient, AIUnavailableError
from app.ai.workflow_draft import WorkflowDraftError, generate_workflow_draft
from app.api.deps import get_ai_client
from app.auth.security import get_current_username
from app.schemas.ai import GenerateDraftRequest, GenerateDraftResponse

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(get_current_username)])


@router.post("/generate-draft", response_model=GenerateDraftResponse)
def generate_draft(
    payload: GenerateDraftRequest, ai_client: AIClient = Depends(get_ai_client)
) -> GenerateDraftResponse:
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    default_universe = ",".join(payload.universe) if payload.universe else None
    try:
        if default_universe:
            draft = generate_workflow_draft(ai_client, payload.idea, default_universe=default_universe)
        else:
            draft = generate_workflow_draft(ai_client, payload.idea)
    except AIUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowDraftError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "attempts": exc.attempts},
        ) from exc

    return GenerateDraftResponse(**draft)
