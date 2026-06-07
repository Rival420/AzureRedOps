import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..security import encrypt, decrypt
from ..core.redops import decode_jwt
from .. import models, schemas

router = APIRouter(prefix="/api/assessments/{assessment_id}/tokens", tags=["tokens"],
                   dependencies=[Depends(get_current_user)])


def _to_out(token: models.Token) -> schemas.TokenOut:
    out = schemas.TokenOut.model_validate(token)
    if token.expires:
        out.is_expired = token.expires < int(time.time())
        out.expires_human = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(token.expires))
    return out


@router.get("", response_model=list[schemas.TokenOut])
def list_tokens(assessment_id: int, db: Session = Depends(get_db)):
    tokens = db.query(models.Token).filter(
        models.Token.assessment_id == assessment_id).order_by(models.Token.created_at.desc()).all()
    return [_to_out(t) for t in tokens]


@router.post("", response_model=schemas.TokenOut, status_code=201)
def create_token(assessment_id: int, payload: schemas.TokenCreate,
                 db: Session = Depends(get_db)):
    if not db.query(models.Assessment).get(assessment_id):
        raise HTTPException(404, "Assessment not found")
    claims = {}
    try:
        claims = decode_jwt(payload.access_token)
    except Exception:
        pass
    token = models.Token(
        assessment_id=assessment_id,
        name=payload.name,
        enc_access_token=encrypt(payload.access_token),
        enc_refresh_token=encrypt(payload.refresh_token),
        tenant_id=payload.tenant_id or claims.get("tid"),
        username=payload.username or claims.get("upn") or claims.get("unique_name"),
        scope=claims.get("scp"),
        audience=claims.get("aud"),
        expires=claims.get("exp"),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return _to_out(token)


@router.get("/{token_id}/reveal", response_model=schemas.TokenReveal)
def reveal_token(assessment_id: int, token_id: int, db: Session = Depends(get_db)):
    token = db.query(models.Token).get(token_id)
    if not token or token.assessment_id != assessment_id:
        raise HTTPException(404, "Token not found")
    access = decrypt(token.enc_access_token)
    claims = {}
    try:
        claims = decode_jwt(access)
    except Exception:
        pass
    return schemas.TokenReveal(
        access_token=access,
        refresh_token=decrypt(token.enc_refresh_token),
        claims=claims,
    )


@router.delete("/{token_id}", status_code=204)
def delete_token(assessment_id: int, token_id: int, db: Session = Depends(get_db)):
    token = db.query(models.Token).get(token_id)
    if not token or token.assessment_id != assessment_id:
        raise HTTPException(404, "Token not found")
    db.delete(token)
    db.commit()
