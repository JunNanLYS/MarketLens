@echo off
cd /d D:\Project\MarketLens
.venv\Scripts\python.exe -m streamlit run ui\app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false > D:\Project\MarketLens\data\ui.out.log 2> D:\Project\MarketLens\data\ui.err.log
