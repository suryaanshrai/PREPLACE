from fastapi import APIRouter, Depends

from security import create_auth_token, hash_password, verify_password, verify_auth_token
from schemas import RecruiterRegister, UserCreate, UserLogin
import models
from .common import get_db, log_audit

router = APIRouter()


@router.post("/register", tags=["Auth"])
def register_user(user: UserCreate, db=Depends(get_db)):
    existing = db.query(models.UserDB).filter(models.UserDB.email == user.email).first()
    if existing:
        return {"error": "Email already registered"}

    new_user = models.UserDB(name=user.name, email=user.email, password=hash_password(user.password), role=user.role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    log_audit(db, "user.register", actor_id=new_user.id, target_type="user", target_id=new_user.id, detail=f"role={new_user.role}")
    return {"message": "User saved in database"}


@router.post("/register-recruiter", tags=["Auth"])
def register_recruiter(data: RecruiterRegister, db=Depends(get_db)):
    existing = db.query(models.UserDB).filter(models.UserDB.email == data.email).first()
    if existing:
        return {"error": "Email already registered"}

    new_user = models.UserDB(name=data.name, email=data.email, password=hash_password(data.password), role="recruiter")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    profile = models.RecruiterProfile(
        user_id=new_user.id,
        company_name=data.company_name,
        roles_hiring=data.roles_hiring,
        status="pending",
    )
    db.add(profile)
    db.commit()
    log_audit(db, "recruiter.register", actor_id=new_user.id, target_type="recruiter_profile", target_id=profile.id, detail=f"company={profile.company_name}")
    return {"message": "Recruiter registered successfully. Awaiting admin approval."}


@router.post("/login", tags=["Auth"])
def login(user: UserLogin, db=Depends(get_db)):
    existing_user = db.query(models.UserDB).filter(models.UserDB.email == user.email).first()
    if not existing_user:
        return {"error": "User not found"}
    if not verify_password(user.password, existing_user.password):
        return {"error": "Incorrect password"}

    if not str(existing_user.password).startswith("pbkdf2$"):
        existing_user.password = hash_password(user.password)
        db.commit()

    result = {
        "message": "Login successful",
        "auth_token": create_auth_token(existing_user.id, existing_user.role),
        "user": {
            "id": existing_user.id,
            "name": existing_user.name,
            "email": existing_user.email,
            "role": existing_user.role,
        },
    }

    if existing_user.role == "recruiter":
        profile = db.query(models.RecruiterProfile).filter(models.RecruiterProfile.user_id == existing_user.id).first()
        if profile:
            result["user"]["company_name"] = profile.company_name
            result["user"]["roles_hiring"] = profile.roles_hiring
            result["user"]["status"] = profile.status

    log_audit(db, "auth.login", actor_id=existing_user.id, target_type="user", target_id=existing_user.id, detail=f"role={existing_user.role}")
    return result


@router.get("/auth/validate", tags=["Auth"])
def validate_token(token: str):
    payload = verify_auth_token(token)
    if not payload:
        return {"valid": False}
    return {"valid": True, "payload": payload}
