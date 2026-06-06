"""WeStockProvider._run_cli SKILL_006 冷启动自动重试测试。

测试目标：
1. SKILL_006 首次失败 → 第二次成功（验证重试逻辑）
2. SKILL_006 重试 3 次仍失败（验证重试次数限制）
3. TimeoutExpired 触发重试
4. 非 SKILL_006 错误（如数据为空）不重试
5. 非零退出码不重试

mock 模式：与 test_westock_extended.py 一致 ——
patch("backend.collectors.westock.subprocess.run") + side_effect 控制
多次调用返回不同结果。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _skill_006_stderr() -> str:
    """构造 westock CLI SKILL_006 错误的 stdout。

    _detect_error 用正则 r"执行失败\\s*\\[(\\w*\\d*)\\]\\s*[:：]\\s*"
    捕获，下面 stdout 含 SKILL_006 标签。
    """
    return "执行失败 [SKILL_006]: 查询热门板块首页失败：未找到数据\n"


def _success_stdout() -> str:
    """构造 westock CLI 成功返回的 markdown 表格 stdout。"""
    return """| code | name | type |
| --- | --- | --- |
| sh600519 | 贵州茅台 | GP-A |
"""


@pytest.mark.asyncio
async def test_retry_skill006_then_success() -> None:
    """首次 SKILL_006 失败 + 第二次成功 → 重试机制有效。"""
    from backend.collectors.westock import WeStockProvider

    p = WeStockProvider(name="westock", timeout=5)
    fail_proc = MagicMock(stdout=_skill_006_stderr(), returncode=0)
    ok_proc = MagicMock(stdout=_success_stdout(), returncode=0)

    with (
        patch("backend.collectors.westock.subprocess.run", side_effect=[fail_proc, ok_proc]) as mock_run,
        patch("backend.collectors.westock.asyncio.sleep", new=AsyncMock()) as _,
    ):
        tables, err = await p._run_cli("search 贵州茅台")

    assert err is None, f"重试后应成功，实际 err={err}"
    assert len(tables) == 1, f"应解析 1 张表，实际 {len(tables)}"
    assert tables[0][0]["code"] == "sh600519"
    assert mock_run.call_count == 2, f"应调用 2 次，实际 {mock_run.call_count}"


@pytest.mark.asyncio
async def test_retry_exhausted_returns_last_error() -> None:
    """3 次都 SKILL_006 → 返回非 None 错误，不崩溃。"""
    from backend.collectors.westock import WeStockProvider

    p = WeStockProvider(name="westock", timeout=5)
    fail_proc = MagicMock(stdout=_skill_006_stderr(), returncode=0)

    with (
        patch("backend.collectors.westock.subprocess.run", return_value=fail_proc) as mock_run,
        patch("backend.collectors.westock.asyncio.sleep", new=AsyncMock()) as _,
    ):
        tables, err = await p._run_cli("search 贵州茅台")

    assert err is not None, "应返回错误信息"
    assert "SKILL_006" in err
    assert tables == []
    # _MAX_RETRIES = 2, 总尝试 = 3 次
    assert mock_run.call_count == 3, f"应调用 3 次（2 次重试），实际 {mock_run.call_count}"


@pytest.mark.asyncio
async def test_retry_timeout_then_success() -> None:
    """TimeoutExpired 触发重试 → 第二次成功。"""
    import subprocess

    from backend.collectors.westock import WeStockProvider

    p = WeStockProvider(name="westock", timeout=5)
    ok_proc = MagicMock(stdout=_success_stdout(), returncode=0)

    with (
        patch(
            "backend.collectors.westock.subprocess.run",
            side_effect=[subprocess.TimeoutExpired(cmd=["npx"], timeout=5), ok_proc],
        ) as mock_run,
        patch("backend.collectors.westock.asyncio.sleep", new=AsyncMock()) as _,
    ):
        tables, err = await p._run_cli("search 贵州茅台")

    assert err is None
    assert len(tables) == 1
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_retry_timeout_exhausted() -> None:
    """TimeoutExpired 重试 3 次仍超时 → 返回超时错误。"""
    import subprocess

    from backend.collectors.westock import WeStockProvider

    p = WeStockProvider(name="westock", timeout=5)

    with (
        patch(
            "backend.collectors.westock.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["npx"], timeout=5),
        ) as mock_run,
        patch("backend.collectors.westock.asyncio.sleep", new=AsyncMock()) as _,
    ):
        tables, err = await p._run_cli("search 贵州茅台")

    assert err is not None
    assert "超时" in err
    assert tables == []
    assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_no_retry_on_data_empty_error() -> None:
    """数据为空（业务错误）不触发重试——立即返回。"""
    from backend.collectors.westock import WeStockProvider

    p = WeStockProvider(name="westock", timeout=5)
    # "数据为空" 走 _detect_error 但不含 SKILL_006 → 不重试
    fail_proc = MagicMock(stdout="数据为空，未找到匹配数据\n", returncode=0)

    with (
        patch("backend.collectors.westock.subprocess.run", return_value=fail_proc) as mock_run,
        patch("backend.collectors.westock.asyncio.sleep", new=AsyncMock()) as _,
    ):
        tables, err = await p._run_cli("search 不存在的股票")

    assert err is not None
    assert "未找到" in err or "数据为空" in err
    assert tables == []
    # 数据为空不是 SKILL_006 → 立即返回，1 次调用
    assert mock_run.call_count == 1, f"业务错误不应重试，实际 {mock_run.call_count}"


@pytest.mark.asyncio
async def test_no_retry_on_nonzero_returncode() -> None:
    """非零退出码不重试。"""
    from backend.collectors.westock import WeStockProvider

    p = WeStockProvider(name="westock", timeout=5)
    fail_proc = MagicMock(stdout="", stderr="some error", returncode=1)

    with (
        patch("backend.collectors.westock.subprocess.run", return_value=fail_proc) as mock_run,
        patch("backend.collectors.westock.asyncio.sleep", new=AsyncMock()) as _,
    ):
        tables, err = await p._run_cli("bad command")

    assert err is not None
    assert tables == []
    assert mock_run.call_count == 1, f"非零退出不应重试，实际 {mock_run.call_count}"


@pytest.mark.asyncio
async def test_no_retry_on_unexpected_exception() -> None:
    """非超时/非 SKILL_006 异常（如 OSError）不重试。"""
    from backend.collectors.westock import WeStockProvider

    p = WeStockProvider(name="westock", timeout=5)

    with (
        patch(
            "backend.collectors.westock.subprocess.run",
            side_effect=OSError("npx not found"),
        ) as mock_run,
        patch("backend.collectors.westock.asyncio.sleep", new=AsyncMock()) as _,
    ):
        tables, err = await p._run_cli("search test")

    assert err is not None
    assert "npx not found" in err
    assert tables == []
    assert mock_run.call_count == 1
