import json
from projects.asset_manager.src.dao import AssetDAO

class ReportGenerator:
    def __init__(self, dao: AssetDAO):
        self.dao = dao

    def generate_duplicate_report(self, output_path: str):
        duplicates = self.dao.get_duplicates()
        report = []
        for file_hash, paths in duplicates:
            report.append({
                "hash": file_hash,
                "files": paths.split(',')
            })
        
        with open(output_path, "w") as f:
            json.dump(report, f, indent=4)
