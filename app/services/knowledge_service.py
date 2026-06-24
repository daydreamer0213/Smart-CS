"""Knowledge base service — SQL CRUD. Phase 2 adds vector sync."""

from sqlalchemy.orm import Session

from app.models.knowledge import Category, KnowledgeItem
from app.schemas.knowledge import (
    CategoryCreate,
    KnowledgeCreate,
    KnowledgeListParams,
    KnowledgeUpdate,
)


def create_knowledge(db: Session, tenant_id: str, data: KnowledgeCreate) -> KnowledgeItem:
    item = KnowledgeItem(
        tenant_id=tenant_id,
        category_id=data.category_id,
        question=data.question,
        answer=data.answer,
        keywords=data.keywords or "",
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_knowledge(db: Session, item_id: str, data: KnowledgeUpdate) -> KnowledgeItem | None:
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if item is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def delete_knowledge(db: Session, item_id: str) -> KnowledgeItem | None:
    item = db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()
    if item is None:
        return None
    item.status = "archived"
    db.commit()
    db.refresh(item)
    return item


def get_knowledge(db: Session, item_id: str) -> KnowledgeItem | None:
    return db.query(KnowledgeItem).filter(KnowledgeItem.id == item_id).first()


def list_knowledge(
    db: Session, tenant_id: str, params: KnowledgeListParams
) -> tuple[list[KnowledgeItem], int]:
    query = db.query(KnowledgeItem).filter(
        KnowledgeItem.tenant_id == tenant_id,
        KnowledgeItem.status != "archived",
    )
    if params.q:
        like = f"%{params.q}%"
        query = query.filter(
            KnowledgeItem.question.ilike(like) | KnowledgeItem.keywords.ilike(like)
        )
    if params.category_id:
        query = query.filter(KnowledgeItem.category_id == params.category_id)
    if params.status:
        query = query.filter(KnowledgeItem.status == params.status)

    total = query.count()
    items = (
        query.order_by(KnowledgeItem.updated_at.desc())
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
        .all()
    )
    return items, total


def create_category(db: Session, tenant_id: str, data: CategoryCreate) -> Category:
    cat = Category(
        tenant_id=tenant_id,
        name=data.name,
        description=data.description or "",
        sort_order=data.sort_order or 0,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def list_categories(db: Session, tenant_id: str) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.tenant_id == tenant_id)
        .order_by(Category.sort_order.asc())
        .all()
    )
