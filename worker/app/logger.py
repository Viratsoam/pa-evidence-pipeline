import json
import sys
from datetime import datetime
from typing import Any, Dict


def log(level: str, message: str, meta: Dict[str, Any] | None = None):
    payload = {"level": level, "message": message, "timestamp": datetime.utcnow().isoformat() + "Z"}
    if meta:
        payload.update(meta)
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


class Logger:
    def info(self, message: str, meta: Dict[str, Any] | None = None):
        log("info", message, meta)

    def error(self, message: str, meta: Dict[str, Any] | None = None):
        log("error", message, meta)

    def warn(self, message: str, meta: Dict[str, Any] | None = None):
        log("warn", message, meta)

    def debug(self, message: str, meta: Dict[str, Any] | None = None):
        log("debug", message, meta)


logger = Logger()
