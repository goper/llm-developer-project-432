"""Синхронный обработчик: текст товара на входе, карточка на выходе."""

from fastapi import APIRouter, HTTPException

from app.llm.client import LLMRequestError, LLMUnavailableError, get_llm_client
from app.schemas.cards import Card
from app.schemas.jobs import CardTextRequest
from app.services import pipeline
from app.services.rag_pipeline import text_context
from app.services.structured import StructuredError

router = APIRouter(tags=["cards"])


@router.post("/cards", response_model=Card)
def create_card(body: CardTextRequest) -> Card:
    ctx = text_context(body.text)
    try:
        outcome = pipeline.run_pipeline(get_llm_client(), ctx, body.product_hint, job_id=None)
    except (LLMUnavailableError, LLMRequestError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StructuredError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return outcome.card
