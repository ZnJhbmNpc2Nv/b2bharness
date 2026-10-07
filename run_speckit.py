#!/usr/bin/env python3
"""
Corporate Spec-Kit: Standalone Specification-Driven Development (SDD) Instance.
Runs on any corporate PC / intranet server with standard Python 3.8+.
ZERO DEPENDENCIES: No uv, no venv, no pip install, no npm required.
"""
import sys
import os
import argparse
import webbrowser
import threading
import time
from http.server import ThreadingHTTPServer

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from server.db import SpecDatabase
from server.lineage import LineageEngine
from server.markdown_sync import MarkdownSync
from server.ai_bridge import AIBridge
from server.app import SpecKitRequestHandler
from modules.manager import ModuleManager


BANNER = r"""
================================================================================
   ______                               __         _____                  __ __ _  __ 
  / ____/___  _________  ____  _________ _/ /____     / ___/____  ___  _____/ //_/(_)/ /_
 / /   / __ \/ ___/ __ \/ __ \/ ___/ __ `/ __/ _ \    \__ \/ __ \/ _ \/ ___/ ,<  / // __/
/ /___/ /_/ / /  / /_/ / /_/ / /  / /_/ / /_/  __/   ___/ / /_/ /  __/ /__/ /| |/ // /_  
\____/\____/_/  / .___/\____/_/   \__,_/\__/\___/   /____/ .___/\___/\___/_/ |_/_/ \__/  
               /_/                                      /_/                               
================================================================================
   * Mode: 100% Zero-Dependency Standalone (Standard Python Library Only)
   * Storage: Local SQLite WAL + Spec-Kit Markdown Bundles
   * Traceability: Full Lineage Graph ("Откуда что родилось") + Audit Diffs
================================================================================
"""


def main():
    parser = argparse.ArgumentParser(description="Corporate Spec-Kit Localhost Server")
    parser.add_argument("--port", type=int, default=8470, help="HTTP port to listen on (default: 8470)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--data-dir", type=str, default="specs_storage", help="Data directory for SQLite and bundles")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser on startup")
    args = parser.parse_args()

    print(BANNER)

    data_dir = os.path.join(current_dir, args.data_dir)
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "speckit.db")
    static_dir = os.path.join(current_dir, "static")

    print(f"[*] Initializing SQLite database at: {db_path}")
    db = SpecDatabase(db_path)
    modules = ModuleManager(db, modules_dir=os.path.join(current_dir, "modules"))
    lineage = LineageEngine(db, module_manager=modules)
    sync = MarkdownSync(db, output_base_dir=data_dir)
    ai = AIBridge(db)

    # Inject dependencies into request handler
    SpecKitRequestHandler.db = db
    SpecKitRequestHandler.lineage = lineage
    SpecKitRequestHandler.sync = sync
    SpecKitRequestHandler.ai = ai
    SpecKitRequestHandler.modules = modules
    SpecKitRequestHandler.static_dir = static_dir

    server_address = (args.host, args.port)
    try:
        httpd = ThreadingHTTPServer(server_address, SpecKitRequestHandler)
    except OSError as e:
        print(f"[!] Error binding to {args.host}:{args.port} - {e}")
        print(f"[!] Try running with a different port, e.g.: python run_speckit.py --port 8475")
        sys.exit(1)

    url = f"http://{args.host}:{args.port}"
    print(f"[+] Server started successfully!")
    print(f"[+] Web Interface available at: {url}")
    print(f"[+] Press Ctrl+C to stop.\n")

    if not args.no_browser:
        def open_browser():
            time.sleep(0.8)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down Corporate Spec-Kit server gracefully...")
        httpd.shutdown()
        print("[*] Server stopped.")


if __name__ == "__main__":
    main()
