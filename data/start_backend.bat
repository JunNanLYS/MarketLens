@echo off
cd /d D:\Project\MarketLens
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --log-level warning > D:\Project\MarketLens\data\backend.out.log 2> D:\Project\MarketLens\data\backend.err.log
