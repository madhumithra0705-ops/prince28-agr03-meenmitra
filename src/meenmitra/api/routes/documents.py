from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from meenmitra.api.deps import RepoDep
from meenmitra.db.repository import FILTER_KEY

router = APIRouter(prefix="/documents", tags=["documents"])

RESERVED = {"q", "limit", "offset"}


@router.get("")
async def list_documents(
    request: Request,
    repo: RepoDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    filters = {key: value for key, value in request.query_params.items() if key not in RESERVED}

    bad = [key for key in filters if not FILTER_KEY.match(key)]

    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid filter name: {bad[0]}",
        )

    total, items = await repo.list(
        q=q,
        filters=filters,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": filters,
        "items": items,
    }


@router.get("/{doc_id}")
async def get_document(doc_id: str, repo: RepoDep) -> dict:
    record = await repo.get(doc_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No document with id '{doc_id}'.",
        )

    return record
