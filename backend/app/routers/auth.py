from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginIn, SignupIn, TokenOut, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id, user.role), user=UserOut.model_validate(user))


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong email or password.")
    return user


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(data: SignupIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    # every new account is a normal user. admins can only be made by another admin
    user = User(name=data.name.strip(), email=email, password_hash=hash_password(data.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    return _token_response(_authenticate(db, data.email, data.password))


@router.post("/token", response_model=TokenOut, include_in_schema=True)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Same as /login but takes form data, this is what the Authorize button on /docs uses.
    Put the email in the username field."""
    return _token_response(_authenticate(db, form.username, form.password))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
