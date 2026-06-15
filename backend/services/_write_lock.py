"""SQLite 同步写入共享锁。"""

import threading

# threading.Lock 可跨 APScheduler 的多个 asyncio.run() 事件循环复用。
_WRITE_LOCK: threading.Lock = threading.Lock()
