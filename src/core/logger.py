from enum import Enum, auto
from datetime import datetime
import json
import os

class LogLevel(Enum):
    INFO = auto()
    WARNING = auto()
    ERROR = auto()

class Logger:
    def __init__(self, log_file="data/dev_log.json"):
        self.log_file = log_file
        if not os.path.exists("data"):
            os.makedirs("data")

    def log(self, stage: str, message: str, level: LogLevel = LogLevel.INFO):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "message": message,
            "level": level.name
        }
        
        # Keep it as a JSON array of logs
        logs = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r") as f:
                    logs = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                logs = []
        
        logs.append(entry)
        
        with open(self.log_file, "w") as f:
            json.dump(logs, f, indent=4)
