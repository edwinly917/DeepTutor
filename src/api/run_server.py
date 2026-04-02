#!/usr/bin/env python
"""
Uvicorn Server Startup Script
Uses Python API instead of command line to avoid Windows path parsing issues.
"""

import os
import sys

# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # Get project root directory
    project_root = Path(__file__).parent.parent.parent

    # Change to project root to ensure correct module imports
    os.chdir(str(project_root))

    # Ensure project root is in Python path
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Get port from configuration
    from src.services.setup import get_backend_port

    backend_port = get_backend_port(project_root)

    # Configure reload_excludes to skip directories that shouldn't trigger reloads.
    # Uvicorn's reload pattern resolver expects paths relative to cwd.
    reload_excludes = [
        "venv",  # Virtual environment
        ".venv",  # Virtual environment (alternative name)
        "data",  # Data directory (includes knowledge_bases, user data, logs)
        "node_modules",  # Node modules (if any at root)
        "web/node_modules",  # Web node modules
        "web/.next",  # Next.js build
        ".git",  # Git directory
        "scripts",  # Scripts directory - don't reload on launcher changes
    ]

    # Filter out non-existent directories to avoid warnings
    reload_excludes = [d for d in reload_excludes if (project_root / d).exists()]

    # Start uvicorn server with reload enabled
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=backend_port,
        reload=True,
        reload_excludes=reload_excludes,
        log_level="info",
    )
