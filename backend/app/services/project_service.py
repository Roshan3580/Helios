from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project


def get_or_create_project(
    db: Session,
    slug: str,
    name: str | None = None,
    environment: str = "production",
) -> Project:
    project = db.scalar(select(Project).where(Project.slug == slug))
    if project:
        return project

    project = Project(
        slug=slug,
        name=name or slug.replace("-", " ").title(),
        environment=environment,
    )
    db.add(project)
    db.flush()
    return project


def list_projects(db: Session) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.asc())))
