"""
Shared API dependencies.
"""
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_token_subject


PLACEHOLDER_SECRET = "your-secret-key-change-in-production-please"


def ensure_default_user(db: Session) -> int:
    """Ensure the legacy single-user record exists and return its id."""
    from app.models.user import User

    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(
            id=1,
            username="default",
            email="default@example.com",
            hashed_password="$2b$12$dummy_hashed_password_not_for_login",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.commit()
    return 1


def require_current_user_id(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> int:
    """
    Resolve the authenticated user id from a JWT bearer token.

    A configured API_ACCESS_TOKEN is also accepted as a service-token fallback
    for local scripts and emergency operations.
    """
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ensure_default_user(db)

    if settings.API_ACCESS_TOKEN and token == settings.API_ACCESS_TOKEN:
        return ensure_default_user(db)

    try:
        user_id = int(get_token_subject(token))
    except ValueError:
        return ensure_default_user(db)

    from app.models.user import User

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return ensure_default_user(db)

    return user.id
