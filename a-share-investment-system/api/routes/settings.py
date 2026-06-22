"""邮箱设置API — 管理邮件发送配置"""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from shared.logging import emit_log

router = APIRouter()

# Config file paths
_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config"
)
_ENV_FILE = os.path.join(_CONFIG_DIR, ".env")
_YAML_FILE = os.path.join(_CONFIG_DIR, "config.yaml")


class EmailSettings(BaseModel):
    sender: str = ""
    password: str = ""
    receivers: list[str] = []
    sender_name: str = "A股智能投研系统"


class EmailTestRequest(BaseModel):
    to: str = ""


def _load_env_settings() -> dict:
    """Load email settings from .env file"""
    settings = {"sender": "", "password": "", "receivers": [], "sender_name": "A股智能投研系统"}
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "QQ_EMAIL_SENDER":
                        settings["sender"] = v
                    elif k == "QQ_EMAIL_AUTH_CODE":
                        settings["password"] = v
                    elif k == "QQ_EMAIL_RECEIVERS":
                        settings["receivers"] = [r.strip() for r in v.split(",") if r.strip()]
    return settings


def _save_env_settings(settings: EmailSettings):
    """Save email settings to .env file"""
    lines = []
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, encoding="utf-8") as f:
            lines = f.readlines()

    # Remove existing email settings
    new_lines = []
    for line in lines:
        if not any(
            line.strip().startswith(k)
            for k in ["QQ_EMAIL_SENDER", "QQ_EMAIL_AUTH_CODE", "QQ_EMAIL_RECEIVERS"]
        ):
            new_lines.append(line)

    # Add new settings
    new_lines.append("\n# 邮箱配置\n")
    new_lines.append(f"QQ_EMAIL_SENDER={settings.sender}\n")
    new_lines.append(f"QQ_EMAIL_AUTH_CODE={settings.password}\n")
    new_lines.append(f"QQ_EMAIL_RECEIVERS={','.join(settings.receivers)}\n")

    with open(_ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Update os.environ
    os.environ["QQ_EMAIL_SENDER"] = settings.sender
    os.environ["QQ_EMAIL_AUTH_CODE"] = settings.password
    os.environ["QQ_EMAIL_RECEIVERS"] = ",".join(settings.receivers)


@router.get("/email")
def get_email_settings():
    """获取邮箱配置"""
    try:
        settings = _load_env_settings()
        # Mask password for security
        masked = settings.copy()
        if masked["password"]:
            masked["password"] = (
                "***" + masked["password"][-4:] if len(masked["password"]) > 4 else "****"
            )
        return {"ok": True, "settings": masked}
    except Exception as e:
        emit_log("ERROR", "settings", f"获取邮箱配置失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.post("/email")
def save_email_settings(settings: EmailSettings):
    """保存邮箱配置"""
    try:
        # Don't save if password is masked
        if settings.password.startswith("***"):
            # Keep existing password
            existing = _load_env_settings()
            settings.password = existing["password"]

        _save_env_settings(settings)
        emit_log("INFO", "settings", f"邮箱配置已更新: {settings.sender}")
        return {"ok": True, "message": "邮箱配置已保存"}
    except Exception as e:
        emit_log("ERROR", "settings", f"保存邮箱配置失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.post("/email/test")
def test_email(request: EmailTestRequest):
    """发送测试邮件"""
    try:
        from providers.email_sender import EmailSender

        sender = EmailSender()
        to = [request.to] if request.to else None
        ok = sender.send("测试邮件 - A股智能投研系统", "这是一封测试邮件，邮箱配置正常。", to=to)
        if ok:
            emit_log("INFO", "settings", f"测试邮件发送成功: {request.to}")
            return {"ok": True, "message": "测试邮件发送成功"}
        return {"ok": False, "message": "测试邮件发送失败，请检查配置"}
    except Exception as e:
        emit_log("ERROR", "settings", f"测试邮件发送失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}
