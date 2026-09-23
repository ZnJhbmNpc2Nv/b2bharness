import json
import re

class LogAnalyzer:
    def parse(self, file_path):
        if not file_path:
            raise FileNotFoundError("File path empty")
        
        with open(file_path, "r") as f:
            content = f.read()
            
        errors = re.findall(r"(ERROR:.*|CRITICAL:.*)", content)
        return {
            "count": len(errors),
            "errors": errors,
            "status": "success"
        }
