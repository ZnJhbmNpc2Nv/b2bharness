"""Nominee Promoter for Corporate Spec-Kit B2B Harness.

КОНЦЕПТУАЛЬНАЯ ТРИАДА МОДУЛЯ:
- ЗАЧЕМ: Ценный опыт исправления багов и редких краевых условий часто теряется после релиза проекта.
  Следующий разработчик или агент наступает на те же самые грабли снова и снова.
- ЧТО: Движок накопления корпоративного знания (`NomineePromoter`):
  1) Извлекает успешные фиксы из `POST-SDD` и оформляет их в кандидаты требований `nominee-xxx.md`.
  2) Нормализует домены (SECURITY, RESILIENCE, PRIVACY, RELIABILITY).
  3) Обеспечивает 1-клик промоушен кандидата в постоянный Репозиторий Требований (`req_bank`).
- ДЛЯ ЧЕГО: Постоянное автоматическое самообучение и обогащение корпоративной базы знаний:
  каждая решенная проблема навсегда становится стандартом для будущих разработок.

Strict Python 3.8+ standard library implementation; zero external dependencies.
"""
import os
import re
import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union


def get_iso_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class NomineePromoter:
    """Promotes post-sdd hardening rules and invariants into enterprise Requirements Bank templates."""

    DOMAIN_SECURITY = "SECURITY"
    DOMAIN_RESILIENCE = "RESILIENCE"
    DOMAIN_PRIVACY = "PRIVACY"
    DOMAIN_RELIABILITY = "RELIABILITY"
    DOMAIN_COMPLIANCE = "COMPLIANCE"

    VALID_DOMAINS = {
        DOMAIN_SECURITY,
        DOMAIN_RESILIENCE,
        DOMAIN_PRIVACY,
        DOMAIN_RELIABILITY,
        DOMAIN_COMPLIANCE,
    }

    DOMAIN_ALIASES = {
        "auth": DOMAIN_SECURITY,
        "crypto": DOMAIN_SECURITY,
        "tls": DOMAIN_SECURITY,
        "vulnerability": DOMAIN_SECURITY,
        "sast": DOMAIN_SECURITY,
        "timeout": DOMAIN_RESILIENCE,
        "circuit_breaker": DOMAIN_RESILIENCE,
        "circuit-breaker": DOMAIN_RESILIENCE,
        "retry": DOMAIN_RESILIENCE,
        "failover": DOMAIN_RESILIENCE,
        "pii": DOMAIN_PRIVACY,
        "gdpr": DOMAIN_PRIVACY,
        "152-fz": DOMAIN_PRIVACY,
        "masking": DOMAIN_PRIVACY,
        "ha": DOMAIN_RELIABILITY,
        "sre": DOMAIN_RELIABILITY,
        "uptime": DOMAIN_RELIABILITY,
        "fault_tolerance": DOMAIN_RELIABILITY,
        "audit": DOMAIN_COMPLIANCE,
        "iso": DOMAIN_COMPLIANCE,
        "soc2": DOMAIN_COMPLIANCE,
    }

    def normalize_domain(self, domain: Optional[str]) -> str:
        """Map raw domain string or alias to canonical enterprise domain."""
        if not domain:
            return self.DOMAIN_RELIABILITY

        clean = domain.strip().upper()
        if clean in self.VALID_DOMAINS:
            return clean

        clean_lower = domain.strip().lower()
        if clean_lower in self.DOMAIN_ALIASES:
            return self.DOMAIN_ALIASES[clean_lower]

        for alias_key, target in self.DOMAIN_ALIASES.items():
            if alias_key in clean_lower:
                return target

        return self.DOMAIN_RELIABILITY

    def extract_nominee_from_post_sdd(
        self, incident_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract a structured nominee candidate from post-sdd drift, incident, or hardening iteration."""
        incident_id = incident_data.get("incident_id") or incident_data.get("id") or "INC-POST-SDD"
        title = incident_data.get("title") or f"Hardened invariant from {incident_id}"
        domain = self.normalize_domain(
            incident_data.get("domain") or incident_data.get("category")
        )

        # Generate unique nominee ID
        clean_name = re.sub(r"[^A-Za-z0-9]", "", incident_id).upper()
        if len(clean_name) > 10:
            clean_name = clean_name[-10:]
        nominee_id = f"NOM-{domain[:4]}-{clean_name}"

        # Problem and solution synthesis
        problem = incident_data.get("problem") or incident_data.get("drift_summary") or ""
        solution = incident_data.get("solution") or incident_data.get("fix_description") or ""

        description = incident_data.get("description")
        if not description:
            description = (
                f"{solution.strip()}\n\n"
                f"Addresses failure mode observed in {incident_id}: {problem.strip()}."
            ).strip()

        rationale = incident_data.get("rationale")
        if not rationale:
            rationale = (
                f"Discovered during POST-SDD automated verification. Hardens the system against "
                f"unhandled invariants and functional drift in {domain.lower()} scenarios."
            )

        criteria = incident_data.get("acceptance_criteria") or []
        if isinstance(criteria, str):
            criteria = [c.strip("- *").strip() for c in criteria.splitlines() if c.strip()]
        elif not isinstance(criteria, list):
            criteria = [str(criteria)]

        if not criteria:
            criteria = [
                f"When executing scenarios matching {incident_id}, the component handles edge conditions deterministically.",
                f"System adheres to strict {domain} non-functional SLA without regression.",
            ]

        tags = incident_data.get("tags") or []
        if isinstance(tags, str):
            tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            tags_list = list(tags)
        if domain.lower() not in [t.lower() for t in tags_list]:
            tags_list.insert(0, domain.lower())

        compliance_std = (
            incident_data.get("compliance_standard")
            or incident_data.get("standard")
            or "ISO-27001 / SRE Operational Baseline"
        )

        return {
            "nominee_id": nominee_id,
            "domain": domain,
            "title": title,
            "description": description,
            "rationale": rationale,
            "acceptance_criteria": criteria,
            "tags": tags_list,
            "compliance_standard": compliance_std,
            "source_incident": incident_id,
            "version": int(incident_data.get("version", 1)),
            "created_at": get_iso_now(),
        }

    def nominee_to_template(self, nominee_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format candidate requirement into schema required by `modules/req_bank` (req_bank_templates).

        Schema:
        - id TEXT PRIMARY KEY (e.g. 'BANK-SEC-99')
        - domain TEXT NOT NULL
        - title TEXT NOT NULL
        - description TEXT NOT NULL
        - rationale TEXT NOT NULL
        - acceptance_criteria TEXT NOT NULL (JSON string)
        - tags TEXT NOT NULL (comma-separated)
        - compliance_standard TEXT NOT NULL
        - version INTEGER NOT NULL
        """
        nominee_id = nominee_data.get("nominee_id") or nominee_data.get("id") or "NOM-001"
        domain = self.normalize_domain(nominee_data.get("domain"))

        # Map template id for Req Bank
        if nominee_id.startswith("BANK-"):
            template_id = nominee_id
        else:
            # e.g. NOM-SECU-INC01 -> BANK-SECU-INC01
            template_id = f"BANK-{nominee_id.replace('NOM-', '')}"

        title = nominee_data.get("title", "Untitled Hardening Requirement")
        description = nominee_data.get("description", "")
        rationale = nominee_data.get("rationale", "")

        criteria = nominee_data.get("acceptance_criteria", [])
        if isinstance(criteria, list):
            criteria_json = json.dumps(criteria, ensure_ascii=False)
        else:
            # Ensure it's a valid JSON string or list
            try:
                parsed = json.loads(str(criteria))
                criteria_json = json.dumps(parsed, ensure_ascii=False)
            except Exception:
                criteria_json = json.dumps([str(criteria)], ensure_ascii=False)

        tags = nominee_data.get("tags", [])
        if isinstance(tags, list):
            tags_str = ",".join(tags)
        else:
            tags_str = str(tags)

        compliance_std = nominee_data.get(
            "compliance_standard", "Enterprise Engineering Baseline"
        )
        version = int(nominee_data.get("version", 1))

        return {
            "id": template_id,
            "domain": domain,
            "title": title,
            "description": description,
            "rationale": rationale,
            "acceptance_criteria": criteria_json,
            "tags": tags_str,
            "compliance_standard": compliance_std,
            "version": version,
        }

    def export_nominee_markdown(
        self, nominee_data: Dict[str, Any], output_path: str
    ) -> str:
        """Export candidate requirement as a standardized nominee-xxx.md document."""
        out_abs = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)

        nominee_id = nominee_data.get("nominee_id") or nominee_data.get("id") or "NOM-REQ-001"
        domain = self.normalize_domain(nominee_data.get("domain"))
        title = nominee_data.get("title", "Untitled Candidate Requirement")
        desc = nominee_data.get("description", "")
        rationale = nominee_data.get("rationale", "")
        source_inc = nominee_data.get("source_incident", "POST-SDD-HARNESS")
        compliance = nominee_data.get("compliance_standard", "ISO-27001 / OWASP ASVS")
        tags = nominee_data.get("tags", [])
        tags_str = ",".join(tags) if isinstance(tags, list) else str(tags)
        version = nominee_data.get("version", 1)
        created_at = nominee_data.get("created_at", get_iso_now())

        criteria = nominee_data.get("acceptance_criteria", [])
        if isinstance(criteria, str):
            try:
                criteria = json.loads(criteria)
            except Exception:
                criteria = [criteria]

        lines = [
            "---",
            f"id: {nominee_id}",
            f"domain: {domain}",
            "status: CANDIDATE_NOMINEE",
            f"source_incident: {source_inc}",
            f"compliance_standard: {compliance}",
            f"tags: {tags_str}",
            f"version: {version}",
            f"created_at: {created_at}",
            "---",
            "",
            f"# {nominee_id}: {title}",
            "",
            f"> **Domain**: `{domain}` | **Status**: `CANDIDATE NOMINEE` | **Standard**: `{compliance}`",
            "",
            "## 1. Description",
            "",
            desc,
            "",
            "## 2. Architectural Rationale",
            "",
            rationale,
            "",
            "## 3. Acceptance Criteria",
            "",
        ]

        for item in criteria:
            lines.append(f"- [ ] {item}")

        lines.extend([
            "",
            "## 4. Provenance & Adoption Instructions",
            "",
            f"- **Extracted From**: `{source_inc}`",
            "- **Target Module**: `corporate_speckit/modules/req_bank`",
            "- **Adoption Command**: Use `NomineePromoter.promote_to_req_bank(conn, ...)` or 1-click adopt in Requirements Bank UI.",
            "",
        ])

        md_content = "\n".join(lines)
        with open(out_abs, "w", encoding="utf-8") as f:
            f.write(md_content)

        return out_abs

    def promote_to_req_bank(
        self, conn: sqlite3.Connection, nominee_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Directly insert or update candidate requirement in SQLite `req_bank_templates` table."""
        template = self.nominee_to_template(nominee_data)

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS req_bank_templates (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL DEFAULT 'SECURITY',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            rationale TEXT NOT NULL,
            acceptance_criteria TEXT NOT NULL,
            tags TEXT NOT NULL,
            compliance_standard TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );
        """)

        conn.execute(
            """
            INSERT INTO req_bank_templates (
                id, domain, title, description, rationale, acceptance_criteria, tags, compliance_standard, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                domain = excluded.domain,
                title = excluded.title,
                description = excluded.description,
                rationale = excluded.rationale,
                acceptance_criteria = excluded.acceptance_criteria,
                tags = excluded.tags,
                compliance_standard = excluded.compliance_standard,
                version = excluded.version
            """,
            (
                template["id"],
                template["domain"],
                template["title"],
                template["description"],
                template["rationale"],
                template["acceptance_criteria"],
                template["tags"],
                template["compliance_standard"],
                template["version"],
            ),
        )

        return template

    def parse_nominee_markdown(self, file_path_or_text: str) -> Dict[str, Any]:
        """Parse nominee-xxx.md file or string back into structured nominee dictionary."""
        if os.path.exists(file_path_or_text):
            with open(file_path_or_text, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = file_path_or_text

        frontmatter: Dict[str, Any] = {}
        body = content

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if fm_match:
            fm_text, body = fm_match.groups()
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip()

        # Extract title from markdown
        title_match = re.search(r"^#\s+(?:[^:]+:\s*)?(.*)$", body, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else frontmatter.get("title", "")

        # Extract description section
        desc_match = re.search(r"## 1\. Description\s*\n(.*?)(?=\n##|$)", body, re.DOTALL)
        desc = desc_match.group(1).strip() if desc_match else ""

        # Extract rationale section
        rat_match = re.search(r"## 2\. Architectural Rationale\s*\n(.*?)(?=\n##|$)", body, re.DOTALL)
        rat = rat_match.group(1).strip() if rat_match else ""

        # Extract criteria
        criteria = []
        crit_match = re.search(r"## 3\. Acceptance Criteria\s*\n(.*?)(?=\n##|$)", body, re.DOTALL)
        if crit_match:
            for line in crit_match.group(1).splitlines():
                line = line.strip()
                if line.startswith("- [ ]") or line.startswith("- [x]"):
                    criteria.append(line[5:].strip())
                elif line.startswith("- ") or line.startswith("* "):
                    criteria.append(line[2:].strip())

        domain = self.normalize_domain(frontmatter.get("domain"))
        tags = [t.strip() for t in frontmatter.get("tags", "").split(",") if t.strip()]

        return {
            "nominee_id": frontmatter.get("id", "NOM-UNKNOWN"),
            "domain": domain,
            "title": title,
            "description": desc,
            "rationale": rat,
            "acceptance_criteria": criteria,
            "tags": tags,
            "compliance_standard": frontmatter.get("compliance_standard", ""),
            "source_incident": frontmatter.get("source_incident", ""),
            "version": int(frontmatter.get("version", 1)),
            "created_at": frontmatter.get("created_at", get_iso_now()),
        }
