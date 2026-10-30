from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..auth import AuthenticatedUser, get_current_user
from ..database import get_db
from ..models import KnowledgeArticle, KnowledgeTag, Meeting
from ..schemas import (
    KnowledgeArticleCreate,
    KnowledgeArticleResponse,
    KnowledgeArticleUpdate,
)


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def article_response(article: KnowledgeArticle) -> KnowledgeArticleResponse:
    return KnowledgeArticleResponse(
        id=article.id,
        title=article.title,
        content=article.content,
        category=article.category,
        tags=[item.tag for item in article.tags],
        creator_clerk_id=article.creator_clerk_id,
        visibility=article.visibility,
        related_meeting_id=article.related_meeting_id,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


def get_article_or_404(
    article_id: int,
    user: AuthenticatedUser,
    db: Session,
) -> KnowledgeArticle:
    article = db.scalar(
        select(KnowledgeArticle)
        .options(selectinload(KnowledgeArticle.tags))
        .where(KnowledgeArticle.id == article_id)
    )
    if article is None or (
        article.creator_clerk_id != user.clerk_id and article.visibility != "shared"
    ):
        raise HTTPException(status_code=404, detail="Knowledge article not found")
    return article


def filtered_articles(
    user: AuthenticatedUser,
    db: Session,
    q: str | None,
    category: str | None,
    tag: str | None,
) -> list[KnowledgeArticle]:
    statement = (
        select(KnowledgeArticle)
        .options(selectinload(KnowledgeArticle.tags))
        .where(
            or_(
                KnowledgeArticle.creator_clerk_id == user.clerk_id,
                KnowledgeArticle.visibility == "shared",
            )
        )
        .order_by(KnowledgeArticle.updated_at.desc(), KnowledgeArticle.id.desc())
    )
    if q and q.strip():
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                KnowledgeArticle.title.ilike(term),
                KnowledgeArticle.content.ilike(term),
            )
        )
    if category and category.strip():
        statement = statement.where(KnowledgeArticle.category == category.strip())
    if tag and tag.strip():
        statement = statement.where(
            KnowledgeArticle.tags.any(KnowledgeTag.tag == tag.strip().lower())
        )
    return list(db.scalars(statement).all())


def validate_meeting_link(meeting_id: int | None, db: Session) -> None:
    if meeting_id is not None and db.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=404, detail="Related meeting not found")


@router.get("", response_model=list[KnowledgeArticleResponse])
def list_knowledge(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    tag: str | None = Query(default=None, max_length=50),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeArticleResponse]:
    return [
        article_response(article)
        for article in filtered_articles(user, db, q, category, tag)
    ]


@router.get("/search", response_model=list[KnowledgeArticleResponse])
def search_knowledge(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    tag: str | None = Query(default=None, max_length=50),
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeArticleResponse]:
    return list_knowledge(q=q, category=category, tag=tag, user=user, db=db)


@router.post(
    "",
    response_model=KnowledgeArticleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge(
    payload: KnowledgeArticleCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeArticleResponse:
    validate_meeting_link(payload.related_meeting_id, db)
    article = KnowledgeArticle(
        title=payload.title,
        content=payload.content,
        category=payload.category,
        creator_clerk_id=user.clerk_id,
        visibility=payload.visibility,
        related_meeting_id=payload.related_meeting_id,
        tags=[KnowledgeTag(tag=tag) for tag in payload.tags],
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article_response(article)


@router.get("/{article_id}", response_model=KnowledgeArticleResponse)
def get_knowledge(
    article_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeArticleResponse:
    return article_response(get_article_or_404(article_id, user, db))


@router.patch("/{article_id}", response_model=KnowledgeArticleResponse)
def update_knowledge(
    article_id: int,
    payload: KnowledgeArticleUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeArticleResponse:
    article = get_article_or_404(article_id, user, db)
    if article.creator_clerk_id != user.clerk_id:
        raise HTTPException(
            status_code=403,
            detail="Only the article creator can make changes",
        )

    changes = payload.model_dump(exclude_unset=True)
    if "related_meeting_id" in changes:
        validate_meeting_link(changes["related_meeting_id"], db)
    for field, value in changes.items():
        if field == "tags":
            article.tags = [KnowledgeTag(tag=tag) for tag in value or []]
        else:
            setattr(article, field, value)
    db.commit()
    db.refresh(article)
    return article_response(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(
    article_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    article = get_article_or_404(article_id, user, db)
    if article.creator_clerk_id != user.clerk_id:
        raise HTTPException(
            status_code=403,
            detail="Only the article creator can delete this article",
        )
    db.delete(article)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
