"""设置路由。

从config.yaml和.env读取配置，支持修改并持久化到user_config.yaml。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("ashare-x.api.settings")

router = APIRouter(prefix="/api", tags=["settings"])

USER_CONFIG_PATH = Path("config/user_config.yaml")


class SettingsModel(BaseModel):
    llm_provider: str = "deepseek"
    base_url: str = ""
    quick_think_model: str = "deepseek-chat"
    deep_think_model: str = "deepseek-reasoner"
    api_key: str = ""
    debate_rounds: int = 2
    risk_rounds: int = 2
    output_language: str = "zh"
    custom_prompt: str = ""
    default_analysts: list[str] = ["market", "fundamentals", "news", "sentiment"]
    monthly_budget_rmb: int = 100
    email_sender: str = ""
    email_password: str = ""
    email_recipient: str = ""
    email_smtp_host: str = "smtp.qq.com"
    email_smtp_port: int = 465
    email_use_ssl: bool = True


class SendTestEmailRequest(BaseModel):
    recipient: str | None = None


def _load_settings() -> SettingsModel:
    """从配置文件和环境变量加载设置。"""
    import os

    from core.config import Config

    config = Config()

    settings = SettingsModel(
        llm_provider=config.get("llm.quick_think.provider", "deepseek"),
        base_url=config.get("llm.quick_think.base_url", ""),
        quick_think_model=config.get("llm.quick_think.model", "deepseek-chat"),
        deep_think_model=config.get("llm.deep_think.model", "deepseek-reasoner"),
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        debate_rounds=config.get("debate.investment.max_rounds", 2),
        risk_rounds=config.get("debate.risk.max_rounds", 2),
        output_language=config.get("log.lang", "zh"),
        monthly_budget_rmb=config.get("llm.monthly_budget_rmb", 100),
        email_sender=config.get("email.sender", ""),
        email_recipient=config.get("email.recipient", ""),
        email_smtp_host=config.get("email.smtp_host", "smtp.qq.com"),
        email_smtp_port=int(config.get("email.smtp_port", 465)),
        email_use_ssl=bool(config.get("email.use_ssl", True)),
    )
    # 加载用户自定义配置
    if USER_CONFIG_PATH.exists():
        try:
            import yaml

            with open(USER_CONFIG_PATH, encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            if user_cfg:
                settings = SettingsModel(**{**settings.model_dump(), **user_cfg})
        except Exception as e:
            logger.warning("加载用户配置失败: %s", e)

    # 邮箱授权码: 环境变量优先级最高, 其次是用户配置文件
    env_email_password = os.getenv("ASHARE_X_EMAIL_PASSWORD")
    if env_email_password:
        settings.email_password = env_email_password

    return settings


@router.get("/settings")
async def get_settings():
    """获取配置。"""
    settings = _load_settings()
    # 隐藏API Key中间部分
    api_key = settings.api_key
    if api_key and len(api_key) > 8:
        masked = api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
    else:
        masked = "***" if api_key else ""
    # 隐藏邮箱授权码
    email_password = settings.email_password
    email_masked = "***" if email_password else ""
    data = settings.model_dump()
    data["api_key"] = masked
    data["email_password"] = email_masked
    data["has_api_key"] = bool(api_key)
    data["has_email_password"] = bool(email_password)
    return data


@router.put("/settings")
async def update_settings(settings: SettingsModel):
    """更新配置（持久化到user_config.yaml）。"""
    try:
        import yaml

        from core.config import Config

        USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # 不保存API Key到文件（安全考虑）, 邮箱授权码可保存到本地文件
        save_data = settings.model_dump()
        save_data.pop("api_key", "")

        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(save_data, f, allow_unicode=True, default_flow_style=False)

        # 同步更新内存中的 email 配置, 使发送服务立即生效
        cfg = Config()
        cfg._set_nested("email.sender", settings.email_sender)
        cfg._set_nested("email.recipient", settings.email_recipient)
        cfg._set_nested("email.smtp_host", settings.email_smtp_host)
        cfg._set_nested("email.smtp_port", settings.email_smtp_port)
        cfg._set_nested("email.use_ssl", settings.email_use_ssl)
        if settings.email_password:
            cfg._set_nested("email.password", settings.email_password)

        logger.info("设置已保存到 %s", USER_CONFIG_PATH)
        return {"status": "ok", "message": "设置已保存"}
    except Exception as e:
        logger.error("保存设置失败: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/settings/send-test-email")
async def send_test_email(req: SendTestEmailRequest):
    """发送测试邮件验证邮箱配置。"""
    try:
        from services.email_sender import EmailSender

        sender = EmailSender()
        return sender.send_test_email(recipient=req.recipient)
    except Exception as e:
        logger.error("发送测试邮件失败: %s", e)
        return {"ok": False, "error": str(e)}
