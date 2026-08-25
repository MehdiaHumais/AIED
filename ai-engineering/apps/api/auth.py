"""AIED Auth - User management, JWT sessions, and email notifications (Neon DB)."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta

import bcrypt
import jwt

_JWT_SECRET_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", ".jwt_secret")

def _get_jwt_secret() -> str:
    env_secret = os.environ.get("AIED_JWT_SECRET", "")
    if env_secret:
        return env_secret
    try:
        if os.path.exists(_JWT_SECRET_FILE):
            return open(_JWT_SECRET_FILE, "r").read().strip()
    except Exception:
        pass
    secret = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(_JWT_SECRET_FILE), exist_ok=True)
        with open(_JWT_SECRET_FILE, "w") as f:
            f.write(secret)
    except Exception:
        pass
    return secret

JWT_SECRET = _get_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72

ADMIN_EMAIL = "britsyncuk@gmail.com"
ADMIN_PASSWORD = "superadmin123"
ADMIN_NAME = "Mehdia"
ADMIN_COMPANY = "Britsync AI Engineering Department"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _create_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def _ensure_admin(memory):
    existing = await memory.get_user_by_email(ADMIN_EMAIL)
    if not existing:
        await memory.create_user({
            "id": secrets.token_hex(16),
            "name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "password_hash": _hash_password(ADMIN_PASSWORD),
            "company_name": ADMIN_COMPANY,
            "status": "approved",
            "is_admin": True,
            "created_at": datetime.utcnow(),
        })


async def init_auth(memory):
    await _ensure_admin(memory)


async def create_user(memory, name: str, email: str, password: str,
                      company_name: str = "", company_role: str = "",
                      company_size: str = "", company_website: str = "") -> dict:
    existing = await memory.get_user_by_email(email)
    if existing:
        return {"error": "An account with this email already exists"}

    user_id = secrets.token_hex(16)
    now = datetime.utcnow()
    user_data = {
        "id": user_id,
        "name": name.strip(),
        "email": email.lower().strip(),
        "password_hash": _hash_password(password),
        "company_name": company_name.strip(),
        "company_role": company_role.strip(),
        "company_size": company_size.strip(),
        "company_website": company_website.strip(),
        "status": "pending",
        "is_admin": False,
        "created_at": now,
        "approved_at": None,
        "rejected_at": None,
    }
    await memory.create_user(user_data)
    token = _create_token(user_id)
    safe = {k: v for k, v in user_data.items() if k != "password_hash"}
    safe["created_at"] = now.isoformat()
    return {"user": safe, "token": token}


async def login_user(memory, email: str, password: str) -> dict:
    user = await memory.get_user_by_email(email)
    if not user:
        return {"error": "No account found with this email"}

    if not _verify_password(password, user["password_hash"]):
        return {"error": "Incorrect password"}

    if user["status"] == "pending":
        return {"error": "Your account is pending admin approval. You will receive an email once approved."}

    if user["status"] == "rejected":
        return {"error": "Your account has been rejected. Please contact support."}

    token = _create_token(user["id"])
    safe = {k: v for k, v in user.items() if k != "password_hash"}
    if hasattr(safe.get("created_at"), "isoformat"):
        safe["created_at"] = safe["created_at"].isoformat()
    return {"user": safe, "token": token}


def get_user_from_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("user_id")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


async def approve_user(memory, user_id: str) -> dict:
    updated = await memory.update_user(user_id, {
        "status": "approved",
        "approved_at": datetime.utcnow(),
    })
    if not updated:
        return {"error": "User not found"}
    safe = {k: v for k, v in updated.items() if k != "password_hash"}
    return {"user": safe}


async def reject_user(memory, user_id: str) -> dict:
    updated = await memory.update_user(user_id, {
        "status": "rejected",
        "rejected_at": datetime.utcnow(),
    })
    if not updated:
        return {"error": "User not found"}
    safe = {k: v for k, v in updated.items() if k != "password_hash"}
    return {"user": safe}


async def delete_user(memory, user_id: str) -> dict:
    deleted = await memory.delete_user(user_id)
    if not deleted:
        return {"error": "User not found"}
    return {"ok": True}


async def get_pending_users(memory) -> list[dict]:
    users = await memory.list_pending_users()
    return [{k: v for k, v in u.items() if k != "password_hash"} for u in users]


async def get_all_users(memory) -> list[dict]:
    users = await memory.list_all_users()
    return [{k: v for k, v in u.items() if k != "password_hash"} for u in users]


def send_approval_email(user_email: str, user_name: str) -> bool:
    try:
        import resend
        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            print(f"[AUTH EMAIL] (no RESEND_API_KEY) Approval email to {user_email}: Welcome {user_name}!")
            return False
        resend.api_key = api_key
        resend.Emails.send({
            "from": "AIED <noreply@britsyncai.com>",
            "to": [user_email],
            "subject": "Your AIED Account Has Been Approved",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #1a73e8;">Welcome to AIED, {user_name}!</h2>
                <p>Your account has been approved by the admin. You can now log in and access the dashboard.</p>
                <a href="http://localhost:5000/login" style="display: inline-block; background: #1a73e8; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; margin: 16px 0;">Login to Dashboard</a>
                <p style="color: #666; font-size: 12px;">If you have any questions, contact us at britsyncuk@gmail.com</p>
            </div>
            """,
        })
        return True
    except Exception as e:
        print(f"[AUTH EMAIL] Failed to send approval email: {e}")
        return False


def send_admin_notification(user_name: str, user_email: str, company_name: str = "") -> bool:
    try:
        import resend
        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            print(f"[AUTH EMAIL] (no RESEND_API_KEY) Admin notification: New signup from {user_name} ({user_email})")
            return False
        resend.api_key = api_key
        company_info = f"<p><strong>Company:</strong> {company_name}</p>" if company_name else ""
        resend.Emails.send({
            "from": "AIED <noreply@britsyncai.com>",
            "to": [ADMIN_EMAIL],
            "subject": f"New Signup Request from {user_name}",
            "html": f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #f59e0b;">New Signup Request</h2>
                <p>A new user has requested access to AIED:</p>
                <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
                    <p><strong>Name:</strong> {user_name}</p>
                    <p><strong>Email:</strong> {user_email}</p>
                    {company_info}
                </div>
                <a href="http://localhost:5000/admin" style="display: inline-block; background: #1a73e8; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; margin: 16px 0;">Review Request</a>
            </div>
            """,
        })
        return True
    except Exception as e:
        print(f"[AUTH EMAIL] Failed to send admin notification: {e}")
        return False
