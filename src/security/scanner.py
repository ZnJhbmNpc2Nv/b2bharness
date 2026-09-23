import ast

class SecurityScanner:
    # Базовый список запрещенных функций или паттернов (OWASP)
    FORBIDDEN_PATTERNS = {
        'os.system', 'subprocess.call', 'subprocess.run', 'subprocess.Popen',
        'eval', 'exec', 'pickle.load', 'yaml.load'
    }
    
    # Можно расширить проверкой на использование небезопасных библиотек или CWE (например, CWE-78)
    CWE_MAPPINGS = {
        'os.system': 'CWE-78',
        'subprocess.call': 'CWE-78',
        'eval': 'CWE-95',
        'exec': 'CWE-95',
        'pickle.load': 'CWE-502'
    }

    def scan_file(self, file_path: str):
        with open(file_path, "r") as f:
            tree = ast.parse(f.read())
            
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._get_func_name(node.func)
                if func_name in self.FORBIDDEN_PATTERNS:
                    cwe = self.CWE_MAPPINGS.get(func_name, "Unknown CWE")
                    issues.append(f"Forbidden function '{func_name}' found (Potential {cwe})")
        
        if issues:
            return False, "; ".join(issues)
        
        return True, "No security issues found"

    def _get_func_name(self, node):
        if isinstance(node, ast.Attribute):
            val = self._get_func_name(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        elif isinstance(node, ast.Name):
            return node.id
        return ""
