"""LLM 配置与预检(OpenAI 兼容协议,默认智谱 BigModel 编程端点)."""

from __future__ import annotations

import os

from crewai import LLM

MODEL_NAME = os.getenv("OPENAI_MODEL", "GLM-5.2")
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"


def get_llm() -> LLM:
    """惰性构造 LLM(避免 import 时因缺 key 报错,校验交给预检)."""
    return LLM(
        model=f"openai/{MODEL_NAME}",
        base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def preflight_llm_check() -> None:
    """kickoff 前的最小连通性检查,把平台业务错误翻译成清晰提示."""
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "✗ OPENAI_API_KEY 未设置\n"
            "  请在项目根目录 .env 中填入 API Key\n"
            "  智谱获取地址: https://open.bigmodel.cn/usercenter/apikeys"
        )

    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
    )
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": "只回复两个字:在线"}],
    )
    if not resp.choices:
        code = getattr(resp, "code", None)
        msg = getattr(resp, "msg", None)
        raise SystemExit(
            f"✗ LLM 服务返回错误: code={code} msg={msg}\n"
            "  常见原因:\n"
            "  1. Key 无效或已过期(检查 .env 中的 OPENAI_API_KEY)\n"
            "  2. shell 中残留旧的环境变量会优先于 .env,先执行: unset OPENAI_API_KEY\n"
            f"  3. 模型名不可用(当前: {MODEL_NAME},注意大小写)"
        )
    print(f"✓ LLM 预检通过: {resp.model}")
