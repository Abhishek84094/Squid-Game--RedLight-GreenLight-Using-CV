"""
Red Light, Green Light — Web Application Entry Point.
Runs the FastAPI + WebSocket server on port specified by cloud environment (Railway/Render) or 8000 locally.
"""

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Red Light Green Light Web Server on 0.0.0.0:{port}...")
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, log_level="info")
