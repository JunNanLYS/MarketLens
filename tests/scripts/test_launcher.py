import socket

import pytest

from scripts.launcher import _ensure_port_available, _is_port_available


async def test_is_port_available_true_for_unused_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    assert _is_port_available("127.0.0.1", port) is True


async def test_ensure_port_available_raises_for_bound_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

        with pytest.raises(RuntimeError, match=f"127.0.0.1:{port} 已被占用"):
            _ensure_port_available("127.0.0.1", port, "FastAPI 后端")
