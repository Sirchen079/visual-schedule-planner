# ruff: noqa: B008
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from zhishi.domain.library import reading
from zhishi.domain.library.reading_schemas import MaterialRead, MaterialSearch
from zhishi.server.deps import get_db

router = APIRouter(prefix='/api/materials', tags=['materials'])


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except reading.MaterialConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/search', response_model=MaterialSearch)
def search(request: Request, query: str = Query(min_length=1, max_length=200),
           file_id: int | None = Query(default=None, gt=0), project_id: int | None = Query(default=None, gt=0),
           file_offset: int = Query(default=0, ge=0), limit: int = Query(default=6, ge=1, le=10),
           db: Session = Depends(get_db)):
    return call(reading.search, db, query, request.app.state.storage_root,
        file_id=file_id, project_id=project_id, file_offset=file_offset, limit=limit)


@router.get('/{file_id}', response_model=MaterialRead)
def read(file_id: int, request: Request, part: int = Query(default=1, ge=1),
         count: int = Query(default=3, ge=1, le=5), revision: str | None = None,
         db: Session = Depends(get_db)):
    return call(reading.read, db, file_id, request.app.state.storage_root,
                part=part, count=count, revision=revision)
