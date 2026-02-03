#!/usr/bin/env python3
"""Launch memory bridge HTTP server on port 5071."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import uvicorn
from memory_bridge_server import create_app

if __name__ == "__main__":
    use_groq = "--no-groq" not in sys.argv
    app = create_app(use_groq=use_groq)
    uvicorn.run(app, host="127.0.0.1", port=5071, log_level="info")
