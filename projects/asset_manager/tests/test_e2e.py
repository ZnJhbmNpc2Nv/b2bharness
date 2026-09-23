import pytest
import os
from projects.asset_manager.src.scanner import AssetScanner
from projects.asset_manager.src.hash_service import HashService
from projects.asset_manager.src.dao import AssetDAO
from projects.asset_manager.src.report_generator import ReportGenerator

def test_full_pipeline(tmp_path):
    # Setup
    db_path = tmp_path / "test.db"
    root_path = tmp_path / "assets"
    root_path.mkdir()
    
    # Create test files
    f1 = root_path / "file1.txt"
    f1.write_text("hello")
    f2 = root_path / "file2.txt"
    f2.write_text("hello") # Duplicate
    
    # 1. Scan & Hash
    scanner = AssetScanner(str(root_path))
    files = scanner.scan()
    dao = AssetDAO(str(db_path))
    
    for f in files:
        h = HashService.calculate_hash(f)
        dao.upsert_asset(f, h)
        
    # 2. Report
    report_path = tmp_path / "report.json"
    reporter = ReportGenerator(dao)
    reporter.generate_duplicate_report(str(report_path))
    
    # Assert
    assert report_path.exists()
    import json
    with open(report_path, "r") as f:
        report = json.load(f)
    assert len(report) == 1
    assert len(report[0]["files"]) == 2
