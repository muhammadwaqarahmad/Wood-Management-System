"""Run the HTTP API for the React frontend (development).

    ./.venv/Scripts/python.exe run_api.py

Serves on http://localhost:8000 and auto-reloads when backend code changes.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "timber.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["timber"],
    )
