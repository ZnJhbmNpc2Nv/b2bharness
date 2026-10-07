"""Diff engine for Corporate Spec-Kit.
Uses Python standard library difflib for zero-dependency diff computation.
"""
import difflib
import html
from typing import Dict, Any, List


def compute_unified_diff(old_text: str, new_text: str, old_label: str = "Before", new_label: str = "After") -> str:
    """Compute standard unified diff."""
    old_lines = (old_text or "").splitlines(keepends=True)
    new_lines = (new_text or "").splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=old_label, tofile=new_label, lineterm="")
    return "".join(diff)


def compute_html_diff(old_text: str, new_text: str) -> str:
    """Generate color-coded inline HTML diff with additions and deletions."""
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    html_lines: List[str] = []
    html_lines.append('<div class="diff-container">')
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                html_lines.append(f'<div class="diff-line diff-equal"><span class="diff-gutter"> </span><span class="diff-text">{html.escape(line)}</span></div>')
        elif tag == "replace":
            for line in old_lines[i1:i2]:
                html_lines.append(f'<div class="diff-line diff-delete"><span class="diff-gutter">-</span><span class="diff-text">{html.escape(line)}</span></div>')
            for line in new_lines[j1:j2]:
                html_lines.append(f'<div class="diff-line diff-insert"><span class="diff-gutter">+</span><span class="diff-text">{html.escape(line)}</span></div>')
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                html_lines.append(f'<div class="diff-line diff-delete"><span class="diff-gutter">-</span><span class="diff-text">{html.escape(line)}</span></div>')
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                html_lines.append(f'<div class="diff-line diff-insert"><span class="diff-gutter">+</span><span class="diff-text">{html.escape(line)}</span></div>')
                
    html_lines.append('</div>')
    return "\n".join(html_lines)


def diff_requirement_payload(old_payload: Dict[str, Any], new_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two requirement snapshots and produce field-level diffs."""
    changes = {}
    keys = ["title", "description", "rationale", "acceptance_criteria", "category", "status"]
    
    for key in keys:
        old_val = old_payload.get(key, "")
        new_val = new_payload.get(key, "")
        
        # Serialize list of criteria if applicable
        if isinstance(old_val, list):
            old_str = "\n".join(f"- {item}" for item in old_val)
        else:
            old_str = str(old_val or "")
            
        if isinstance(new_val, list):
            new_str = "\n".join(f"- {item}" for item in new_val)
        else:
            new_str = str(new_val or "")
            
        if old_str != new_str:
            changes[key] = {
                "before": old_str,
                "after": new_str,
                "unified": compute_unified_diff(old_str, new_str, old_label=f"v{old_payload.get('version', 'old')}", new_label=f"v{new_payload.get('version', 'new')}"),
                "html": compute_html_diff(old_str, new_str)
            }
            
    return changes
