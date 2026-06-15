"""NeoData 金融数据 HTTP 客户端 —— Token 管理与查询请求。"""

import asyncio
import base64
import json
import os
import stat
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

_TOKEN_FILE = Path.home() / ".workbuddy" / ".neodata_token"
_TOKEN_TTL_SECONDS = 12 * 3600
# \u4e0e\u670d\u52a1\u7aef\u65f6\u95f4\u504f\u5dee\u9608\u503c\uff1a\u8d85\u8fc7 1 \u5c0f\u65f6\u89c6\u4e3a\u65f6\u949f\u6f02\u79fb\u8fc7\u5927\uff0c\u5224\u5b9a token \u5931\u6548
_CLOCK_SKEW_TOLERANCE_SECONDS = 3600
_AUTH_ERROR_KEYWORDS = ("token", "auth", "unauthorized", "forbidden")


class TokenManager:
    """Token 管理器（同步，仅涉及本地文件读写）。"""

    def __init__(self, config_token: str | None = None) -> None:
        self._config_token = config_token

    def _read_cache(self) -> tuple[str | None, str]:
        """
        读取本地 token 缓存并校验其有效性。

        安全说明：NeoData 是外部 SaaS，本地不持有服务端公钥，因此无法离线
        验证 JWT 签名。本函数仅做以下「advisory」层面的校验：
        1. 解析 JWT payload 中的 `exp`，判断标准 exp 是否到期；
        2. 若 exp 距离本地时间超过 `_CLOCK_SKEW_TOLERANCE_SECONDS` 视为时钟漂移，判定为无效；
        3. 非 JWT 格式的 token 回退到 `_TOKEN_TTL_SECONDS` 简单 TTL。
        """
        try:
            raw = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError):
            return None, "none"
        if not raw:
            return None, "none"
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None, "none"
        # 优先检查"禁用截止时间"：clear_cache 不再 unlink 文件，而是写入
        # disabled_until；本函数在禁用期内直接返回 None，避免用户新写的
        # token 被静默自删（之前的 unlink 实现是 bug：一旦 auth 错误就
        # 删除用户手写的 token，运维必须反复重写）。
        disabled_until = data.get("disabled_until", 0)
        if isinstance(disabled_until, (int, float)) and time.time() < disabled_until:
            return None, "none"
        saved_at = data.get("saved_at", 0)
        credential = data.get("token", "")
        if not credential:
            return None, "none"
        parts = credential.split(".")
        if len(parts) == 3:
            try:
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(
                    base64.urlsafe_b64decode(payload_b64).decode("utf-8")
                )
                exp = payload.get("exp")
                if isinstance(exp, (int, float)):
                    now = time.time()
                    # exp 尚未到期且与本地时间偏差在容忍范围内
                    if now < exp and (exp - now) >= -_CLOCK_SKEW_TOLERANCE_SECONDS:
                        return credential, "cache"
                    # exp 已过期或偏差过大，视为不可用
                    return None, "none"
            except Exception:
                pass
        if time.time() - saved_at > _TOKEN_TTL_SECONDS:
            return None, "none"
        return credential, "cache"

    def get_token(self) -> tuple[str | None, str]:
        credential, source = self._read_cache()
        if credential is not None:
            return credential, source
        if self._config_token:
            return self._config_token, "config"
        env_token = os.getenv("NEODATA_TOKEN")
        if env_token:
            return env_token, "env"
        return None, "none"

    def save_token(self, credential: str) -> None:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"token": credential.strip(), "saved_at": int(time.time())}
        _TOKEN_FILE.write_text(json.dumps(data), encoding="utf-8")
        try:
            _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    # 30 秒:服务端压力导致的偶发 401,30s 内大概率能恢复;不锁一整天。
    _CLEAR_CACHE_DISABLE_SECONDS = 30

    def clear_cache(self) -> None:
        """把当前缓存 token 标记为禁用 30 秒（不删文件）。

        30s 后 _read_cache 会重新尝试；用户手动重写文件 + 删除
        disabled_until 字段可立即恢复。
        """
        try:
            raw = _TOKEN_FILE.read_text(encoding="utf-8").strip()
            data = json.loads(raw) if raw else {}
        except (FileNotFoundError, PermissionError, json.JSONDecodeError, TypeError):
            return
        data["disabled_until"] = int(time.time()) + self._CLEAR_CACHE_DISABLE_SECONDS
        try:
            _TOKEN_FILE.write_text(json.dumps(data), encoding="utf-8")
            logger.warning(
                "NeoData token 已被禁用 {}s,期间所有请求将跳过 NeoData 源 "
                "(可手改 ~/.workbuddy/.neodata_token 删除 disabled_until 字段立即恢复)",
                self._CLEAR_CACHE_DISABLE_SECONDS,
            )
        except OSError:
            pass

    def get_status(self) -> dict[str, Any]:
        credential, source = self.get_token()
        has_token = credential is not None
        expires_at: str | None = None
        if has_token and source == "cache":
            try:
                raw = _TOKEN_FILE.read_text(encoding="utf-8").strip()
                data = json.loads(raw)
                credential = data.get("token", "")
                parts = credential.split(".") if credential else []
                if len(parts) == 3:
                    try:
                        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                        payload = json.loads(
                            base64.urlsafe_b64decode(payload_b64).decode("utf-8")
                        )
                        exp = payload.get("exp")
                        if isinstance(exp, (int, float)):
                            expires_at = time.strftime(
                                "%Y-%m-%dT%H:%M:%S", time.localtime(exp)
                            )
                    except Exception:
                        pass
                if expires_at is None:
                    saved_at = data.get("saved_at", 0)
                    expires_at = time.strftime(
                        "%Y-%m-%dT%H:%M:%S",
                        time.localtime(saved_at + _TOKEN_TTL_SECONDS),
                    )
            except (
                FileNotFoundError,
                PermissionError,
                json.JSONDecodeError,
                TypeError,
            ):
                pass
        # verified 始终为 False：本地无服务端公钥，未做 JWT 签名验证
        return {
            "has_token": has_token,
            "source": source,
            "expires_at": expires_at,
            "verified": False,
        }


def _is_auth_error(status_code: int | None, body: dict | None) -> bool:
    if status_code in (401, 403):
        return True
    if body is not None:
        code = str(body.get("code", ""))
        msg = str(body.get("msg", "")).lower()
        if code == "40101":
            return True
        if any(kw in msg for kw in _AUTH_ERROR_KEYWORDS):
            return True
    return False


class NeoDataClient:
    """NeoData API 异步客户端。"""

    def __init__(
        self,
        endpoint: str,
        config_token: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._token_manager = TokenManager(config_token=config_token)
        # 懒加载 httpx.AsyncClient：避免 import 阶段在 Windows + Python 3.13 上
        # 因 SSL/连接池初始化阻塞 3.8s+。首次 await 使用时再创建。
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """首次使用时创建 httpx 客户端，后续复用。"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout))
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def query(self, query_text: str, data_type: str = "all") -> dict | None:
        token, source = await asyncio.to_thread(self._token_manager.get_token)
        if token is None:
            logger.warning(
                "NeoData \u65e0\u53ef\u7528\u51ed\u8bc1\uff0c\u8df3\u8fc7\u67e5\u8be2"
            )
            return None
        result = await self._do_request(token, query_text, data_type)
        if result is None:
            return await self._retry_on_auth_error(token, source, query_text, data_type)
        return result

    async def _do_request(
        self, token: str, query_text: str, data_type: str
    ) -> dict | None:
        payload: dict[str, str] = {
            "query": query_text,
            "channel": "neodata",
            "sub_channel": "workbuddy",
        }
        if data_type != "all":
            payload["data_type"] = data_type
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        try:
            client = await self._get_client()
            resp = await client.post(self.endpoint, json=payload, headers=headers)
            if _is_auth_error(resp.status_code, None):
                return None
            resp.raise_for_status()
            body = resp.json()
            if _is_auth_error(resp.status_code, body):
                return None
            return body
        except httpx.TimeoutException:
            logger.warning(
                "NeoData \u8bf7\u6c42\u8d85\u65f6: endpoint={}", self.endpoint
            )
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(
                "NeoData HTTP \u9519\u8bef: status={}", e.response.status_code
            )
            return None
        except Exception as e:
            logger.warning("NeoData \u8bf7\u6c42\u5f02\u5e38: error={}", e)
            return None

    async def _retry_on_auth_error(
        self, used_token: str, source: str, query_text: str, data_type: str
    ) -> dict | None:
        await asyncio.to_thread(self._token_manager.clear_cache)
        new_token, new_source = await asyncio.to_thread(self._token_manager.get_token)
        if new_token is None or new_token == used_token:
            logger.warning(
                "NeoData \u9274\u6743\u5931\u8d25\u4e14\u65e0\u5907\u9009\u51ed\u8bc1"
            )
            return None
        logger.info(
            "NeoData \u9274\u6743\u5931\u8d25\uff0c\u4f7f\u7528\u5907\u9009\u51ed\u8bc1\u91cd\u8bd5 (source={})",
            new_source,
        )
        result = await self._do_request(new_token, query_text, data_type)
        if result is None:
            logger.warning("NeoData \u91cd\u8bd5\u4ecd\u7136\u5931\u8d25")
            return None
        if _is_auth_error(None, result):
            logger.warning("NeoData \u91cd\u8bd5\u9274\u6743\u4ecd\u7136\u5931\u8d25")
            return None
        return result

    def save_token(self, credential: str) -> None:
        self._token_manager.save_token(credential)

    def get_token_status(self) -> dict[str, Any]:
        return self._token_manager.get_status()
