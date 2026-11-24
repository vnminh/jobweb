from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_account, hash_password, make_token, verify_password
from ..db import get_db
from ..models import Account, Company, SeekerProfile

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=64)
    full_name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(seeker|recruiter)$")
    company_name: str | None = None
    state: str | None = None


def account_out(a: Account) -> dict:
    d = {"id": a.id, "email": a.email, "role": a.role, "full_name": a.full_name, "active": a.active}
    if a.seeker:
        d["seeker_id"] = a.seeker.id
    if a.company:
        d["company_id"] = a.company.id
        d["company_name"] = a.company.name
    return d


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    acc = db.query(Account).filter(Account.email == body.email.strip().lower()).first()
    if acc is None or not verify_password(body.password, acc.password_hash):
        raise HTTPException(401, "Email hoặc mật khẩu không đúng")
    if not acc.active:
        raise HTTPException(403, "Tài khoản đã bị khoá")
    return {"token": make_token(acc), "account": account_out(acc)}


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.query(Account).filter(Account.email == email).first():
        raise HTTPException(400, "Email đã được sử dụng")
    acc = Account(email=email, password_hash=hash_password(body.password), role=body.role, full_name=body.full_name.strip())
    db.add(acc)
    db.flush()
    if body.role == "seeker":
        db.add(SeekerProfile(account_id=acc.id, window_id=7, state=body.state, country="US", degree_type="None", degree_ord=0))
    else:
        db.add(Company(account_id=acc.id, name=(body.company_name or body.full_name).strip(), state=body.state))
    db.commit()
    db.refresh(acc)
    return {"token": make_token(acc), "account": account_out(acc)}


@router.get("/me")
def me(acc: Account = Depends(current_account)):
    return account_out(acc)
