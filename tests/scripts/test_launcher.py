import socket
from unittest.mock import patch

import pytest

from scripts.launcher import _is_port_available, _release_port


async def test_is_port_available_true_for_unused_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    assert _is_port_available("127.0.0.1", port) is True


async def test_release_port_terminates_bound_process() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

        with (
            patch("scripts.launcher._port_pids", return_value={1234}) as mock_pids,
            patch("scripts.launcher._terminate_pid") as mock_terminate,
            patch(
                "scripts.launcher._is_port_available",
                side_effect=[False, True],
            ) as mock_available,
        ):
            _release_port("127.0.0.1", port, "FastAPI 后端")

    mock_pids.assert_called_once_with(port)
    mock_terminate.assert_called_once_with(1234, "FastAPI 后端")
    assert mock_available.call_count == 2


async def test_release_port_raises_when_no_pid_found() -> None:
    with patch("scripts.launcher._is_port_available", return_value=False):
        with patch("scripts.launcher._port_pids", return_value=set()):
            with pytest.raises(RuntimeError, match="未找到监听进程"):
                _release_port("127.0.0.1", 8000, "FastAPI 后端")
