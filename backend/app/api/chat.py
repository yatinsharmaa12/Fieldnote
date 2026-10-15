from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_chat_rate_limit
from app.db.session import get_db
from app.models.user import User
from app.rag.pipeline import answer_question
from app.rag.exceptions import LLMProviderError
from app.repositories.company_repository import get_company_for_user


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


class ChatRequest(BaseModel):
    company_id: int
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def check_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be empty")
        return value


@router.post("")
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    http_request: Request = None,  # type: ignore[assignment]
):
    check_chat_rate_limit(http_request, current_user.id)
    company = get_company_for_user(
        db=db,
        company_id=request.company_id,
        user_id=current_user.id,
    )

    if not company:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    company_id = company.id
    # Release the auth/ownership transaction's pooled connection before the
    # potentially slow model call. Retrieval owns its own short-lived session.
    db.close()
    try:
        return answer_question(
            question=request.question,
            company_id=company_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except LLMProviderError:
        raise HTTPException(
            status_code=502,
            detail="The language model provider is temporarily unavailable. Please try again.",
        )
