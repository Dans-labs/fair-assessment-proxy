import hmac
import hashlib
import base64
import requests
import logging
import time
import uuid
import json
import sqlite3
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from fair_assessment_proxy.config import load_service_config

service_config = load_service_config()
bearer_scheme = HTTPBearer(auto_error=False)

logger = logging.getLogger(__name__)

if service_config.egi_env == "production":
    logger.info("Using production EGI AAI endpoints")
    JWKS_URL = "https://aai.egi.eu/auth/realms/egi/protocol/openid-connect/certs"
    USERINFO_URL = "https://aai.egi.eu/auth/realms/egi/protocol/openid-connect/userinfo"
    ISSUER = "https://aai.egi.eu/auth/realms/egi"
    TOKEN_PORTAL = "https://aai.egi.eu/token/"
if service_config.egi_env == "development":
    logger.info("Using development EGI AAI endpoints")
    JWKS_URL = "https://aai-dev.egi.eu/auth/realms/egi/protocol/openid-connect/certs"
    USERINFO_URL = (
        "https://aai-dev.egi.eu/auth/realms/egi/protocol/openid-connect/userinfo"
    )
    ISSUER = "https://aai-dev.egi.eu/auth/realms/egi"
    TOKEN_PORTAL = "https://aai-dev.egi.eu/token/"
if service_config.egi_env == "demo":
    logger.info("Using demo EGI AAI endpoints")
    JWKS_URL = "https://aai-demo.egi.eu/auth/realms/egi/protocol/openid-connect/certs"
    USERINFO_URL = (
        "https://aai-demo.egi.eu/auth/realms/egi/protocol/openid-connect/userinfo"
    )
    ISSUER = "https://aai-demo.egi.eu/auth/realms/egi"
    TOKEN_PORTAL = "https://aai-demo.egi.eu/token/"


ALLOWED_SKEW = 60
NONCE_DB = "cache/nonces.db"  # seconds


def init_nonce_db(path=NONCE_DB):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nonces (
            nonce TEXT PRIMARY KEY,
            expires_at INTEGER
        )
    """)
    conn.commit()
    conn.close()  # token 'iss' claim


# def _generate_admin_token(secret: str) -> str:
#     digest = hmac.new(secret.encode(), b"admin-access", hashlib.sha256).digest()
#     return base64.urlsafe_b64encode(digest).decode()


def generate_admin_token(secret: str, user: str = "admin") -> str:
    timestamp = int(time.time())
    nonce = uuid.uuid4().hex

    payload = {
        "user": user,
        "ts": timestamp,
        "nonce": nonce,
    }

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()

    signature = hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).digest()

    token = base64.urlsafe_b64encode(payload_bytes + b"." + signature)
    return token.decode()


def validate_admin_token(token: str, secret: str, db_path=NONCE_DB):
    logger.debug(f"Validating admin token: {token}")
    try:
        decoded = base64.urlsafe_b64decode(token.encode())
        payload_bytes, signature = decoded.rsplit(b".", 1)
    except Exception as e:
        logger.debug(f"Admin token decoding error: {str(e)}")
        return False

    expected_sig = hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(expected_sig, signature):
        logger.debug("Admin token signature mismatch")
        return False

    payload = json.loads(payload_bytes)
    now = int(time.time())

    if abs(now - payload["ts"]) > ALLOWED_SKEW:
        logger.debug("Admin token expired")
        return False

    nonce = payload["nonce"]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM nonces WHERE expires_at < ?", (now,))
    cursor.execute("SELECT 1 FROM nonces WHERE nonce = ?", (nonce,))
    if cursor.fetchone():
        conn.close()
        logger.debug("Admin token replay detected")
        return False

    cursor.execute(
        "INSERT INTO nonces (nonce, expires_at) VALUES (?, ?)",
        (nonce, now + ALLOWED_SKEW),
    )

    conn.commit()
    conn.close()
    return payload


jwk_client = PyJWKClient(JWKS_URL)


def fetch_user_info(token: str) -> dict:
    try:
        response = requests.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.debug(f"Userinfo fetch error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to fetch user info"
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if not credentials:
        return None
    admin_user = validate_admin_token(
        credentials.credentials, service_config.admin_auth_key
    )
    if admin_user:
        logger.info("Admin token validated successfully")
        return {"user": admin_user["user"], "token_type": "admin"}
    else:
        try:
            token = credentials.credentials
            # fetch signing key from JWKS based on 'kid' in token
            signing_key = jwk_client.get_signing_key_from_jwt(token).key

            # decode and validate
            # payload = jwt.decode(token, signing_key, algorithms=["RS256"], issuer=ISSUER)
            _ = jwt.decode(token, signing_key, algorithms=["RS256"], issuer=ISSUER)
            user_info = fetch_user_info(token)
            # payload["user_info"] = user_info  # attach user info to payload
            return {
                "user": user_info["voperson_id"],
                "token_type": "egi",
            }  # optionally return payload for use in route

        except Exception as e:
            logger.debug(f"Token invalid: {str(e)}")
            return None
    return None


def validate_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    admin_user = validate_admin_token(
        credentials.credentials, service_config.admin_auth_key
    )
    if admin_user:
        logger.info("Admin token validated successfully")
        return {"user": admin_user["user"], "token_type": "admin"}
    return validate_egi_token(credentials)


def validate_egi_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    try:
        token = credentials.credentials
        # fetch signing key from JWKS based on 'kid' in token
        signing_key = jwk_client.get_signing_key_from_jwt(token).key

        # decode and validate
        # payload = jwt.decode(token, signing_key, algorithms=["RS256"], issuer=ISSUER)
        _ = jwt.decode(token, signing_key, algorithms=["RS256"], issuer=ISSUER)
        user_info = fetch_user_info(token)
        # payload["user_info"] = user_info  # attach user info to payload
        return {
            "user": user_info["voperson_id"],
            "token_type": "egi",
            "env": service_config.egi_env,
        }  # optionally return payload for use in route

    except jwt.ExpiredSignatureError as e:
        logger.debug(f"Token expired: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token expired; get a new one from EGI AAI ({TOKEN_PORTAL})",
        )
    except jwt.InvalidTokenError as e:
        logger.debug(f"Token validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token; get a new one from EGI AAI ({TOKEN_PORTAL})",
        )
    except Exception as e:
        logger.debug(f"Token validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token; get a new one from EGI AAI ({TOKEN_PORTAL})",
        )
