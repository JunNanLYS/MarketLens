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
_AUTH_ERROR_KEYWORDS = ("token", "认证", "鉴权", "凭证", "unauthorized", "forbidden")


class TokenManager:

    def __init__(self, config_token: str | None = None) -> None:
        self._config_token = config_token

    def _read_cache(self) -> tuple[str | None, str]:
        """读取缓存凭证，自动识别 JWT 与 tempToken 并分别判断有效期。

        - JWT（三段 Base64）：解码 payload 检查 exp 声明
        - tempToken（非 JWT 格式）：回退到 saved_at + 12h TTL
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

        saved_at = data.get("saved_at", 0)
        credential = data.get("token", "")

        if not credential:
            return None, "none"

        # 尝试解析 JWT exp
        parts = credential.split(".")
        if len(parts) == 3:
            try:
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(
                    base64.urlsafe_b64decode(payload_b64).decode("utf-8")
                )
                exp = payload.get("exp")
                if isinstance(exp, (int, float)) and time.time() < exp:
                    return credential, "cache"
                if isinstance(exp, (int, float)):
                    return None, "none"
            except Exception:
                pass  # 非标准 JWT，继续走 tempToken 逻辑

        # tempToken 回退：12 小时 TTL
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
        data = {
            "token": credential.strip(),
            "saved_at": int(time.time()),
        }
        _TOKEN_FILE.write_text(json.dumps(data), encoding="utf-8")
        try:
            _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def clear_cache(self) -> None:
        try:
            _TOKEN_FILE.unlink()
        except FileNotFoundError:
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
                # 尝试从 JWT exp 获取过期时间
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
                # 非 JWT 则回退到 saved_at + TTL
                if expires_at is None:
                    saved_at = data.get("saved_at", 0)
                    expires_at = time.strftime(
                        "%Y-%m-%dT%H:%M:%S", time.localtime(saved_at + _TOKEN_TTL_SECONDS)
                    )
            except (FileNotFoundError, PermissionError, json.JSONDecodeError, TypeError):
                pass

        return {
            "has_token": has_token,
            "source": source,
            "expires_at": expires_at,
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

    def __init__(
        self,
        endpoint: str,
        config_token: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._token_manager = TokenManager(config_token=config_token)

    def query(self, query_text: str, data_type: str = "all") -> dict | None:
        token, source = self._token_manager.get_token()
        if token is None:
            logger.warning("NeoData 无可用凭证，跳过查询")
            return None

        result = self._do_request(token, query_text, data_type)
        if result is None:
            return self._retry_on_auth_error(token, source, query_text, data_type)

        return result

    def _do_request(
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
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.endpoint, json=payload, headers=headers)

            if _is_auth_error(resp.status_code, None):
                return None

            resp.raise_for_status()
            body = resp.json()

            if _is_auth_error(None, body):
                return None

            return body
        except httpx.TimeoutException:
            logger.warning("NeoData 请求超时: endpoint={}", self.endpoint)
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(
                "NeoData HTTP 错误: status={}", e.response.status_code
            )
            return None
        except Exception as e:
            logger.warning("NeoData 请求异常: error={}", e)
            return None

    def _retry_on_auth_error(
        self,
        used_token: str,
        source: str,
        query_text: str,
        data_type: str,
    ) -> dict | None:
        self._token_manager.clear_cache()

        new_token, new_source = self._token_manager.get_token()
        if new_token is None or new_token == used_token:
            logger.warning("NeoData 鉴权失败且无备选凭证")
            return None

        logger.info("NeoData 鉴权失败，使用备选凭证重试 (source={})", new_source)
        result = self._do_request(new_token, query_text, data_type)

        if result is None:
            logger.warning("NeoData 重试仍然失败")
            return None

        if _is_auth_error(None, result):
            logger.warning("NeoData 重试鉴权仍然失败")
            return None

        return result

    def save_token(self, credential: str) -> None:
        self._token_manager.save_token(credential)

    def get_token_status(self) -> dict[str, Any]:
        return self._token_manager.get_status()
