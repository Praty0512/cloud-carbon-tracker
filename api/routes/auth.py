"""Authentication routes."""

import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from database.service import UserService, OrganizationService
from database.models import LoginRequest, TokenResponse

router = APIRouter()

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

security = HTTPBearer()


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token and return user info."""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        org_id = payload.get("org_id")
        if user_id is None or org_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": int(user_id), "org_id": int(org_id)}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """Authenticate user and return JWT token."""
    user = UserService.get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify password
    import hashlib
    password_hash = hashlib.sha256(request.password.encode()).hexdigest()
    if password_hash != user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Get user's organization
    organizations = OrganizationService.get_user_organizations(user.id)
    if not organizations:
        raise HTTPException(status_code=400, detail="No organization found for user")
    
    org = organizations[0]  # Use first organization
    
    # Create token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "org_id": str(org.id)}, 
        expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token,
        user=user,
        organization=org
    )


@router.post("/register")
def register(email: str, password: str, full_name: str, org_name: str):
    """Register new user and organization."""
    # Check if user exists
    existing_user = UserService.get_user_by_email(email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    # Create user
    user = UserService.create_user(email, password, full_name)
    
    # Create organization
    org = OrganizationService.create_organization(org_name, user.id, f"Organization for {full_name}")
    
    return {
        "message": "User registered successfully",
        "user_id": user.id,
        "org_id": org.id
    }


# Dependency for protected routes
def get_current_org(token_data: dict = Depends(verify_token)):
    """Get current organization from token."""
    return token_data["org_id"]
