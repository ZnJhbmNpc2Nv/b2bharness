import pytest
from projects.log_analyzer.src.analyzer import LogAnalyzer

def test_analyzer_parsing(tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text("INFO: Start\nERROR: Failed\nCRITICAL: Fatal")
    
    analyzer = LogAnalyzer()
    result = analyzer.parse(str(log_file))
    
    assert result["count"] == 2
    assert "ERROR: Failed" in result["errors"]

def test_analyzer_missing_file():
    analyzer = LogAnalyzer()
    with pytest.raises(FileNotFoundError):
        analyzer.parse("")
