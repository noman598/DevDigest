# backend/tools/cve_tools.py
from typing import Any, Dict, List, Optional
import httpx
from langchain_core.tools import tool

from config import config
from utils.logger import log

OSV_API_URL = "https://api.osv.dev/v1/query"


def query_osv_vulnerabilities(package_name: str, ecosystem: Optional[str] = None) -> Dict[str, Any]:
    """
    Queries Google's Open Source Vulnerability (OSV) database for package vulnerabilities.
    Supported ecosystems: PyPI, npm, Go, crates.io, Maven, NuGet, Packagist, etc.
    """
    clean_pkg = package_name.strip().lower()
    payload: Dict[str, Any] = {"package": {"name": clean_pkg}}
    if ecosystem:
        payload["package"]["ecosystem"] = ecosystem

    headers = {
        "User-Agent": getattr(config, "USER_AGENT", "StackPulse-Agent/1.0"),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=8.0, headers=headers) as client:
            resp = client.post(OSV_API_URL, json=payload)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "package": clean_pkg,
                    "error": f"OSV API returned HTTP {resp.status_code}",
                }

            data = resp.json()
            vulns_raw = data.get("vulns", [])
            if not vulns_raw:
                return {
                    "success": True,
                    "package": clean_pkg,
                    "vulnerable": False,
                    "advisories": [],
                }

            advisories = []
            for v in vulns_raw[:3]:  # Top 3 most relevant advisories
                vuln_id = v.get("id", "Unknown ID")
                summary = v.get("summary") or (v.get("details", "")[:120] + "...")
                severity = "UNKNOWN"

                # Check database specific or CVSS severity
                db_specific = v.get("database_specific", {})
                if db_specific.get("severity"):
                    severity = str(db_specific.get("severity")).upper()
                elif v.get("severity"):
                    severity = str(v["severity"][0].get("score", "REPORTED"))

                # Extract fixed version if present
                fixed_version = None
                for aff in v.get("affected", []):
                    for r in aff.get("ranges", []):
                        for event in r.get("events", []):
                            if "fixed" in event:
                                fixed_version = event["fixed"]
                                break

                advisories.append({
                    "id": vuln_id,
                    "severity": severity,
                    "summary": summary,
                    "fixed_version": fixed_version,
                })

            return {
                "success": True,
                "package": clean_pkg,
                "vulnerable": True,
                "advisories": advisories,
            }

    except Exception as e:
        log.warning("cve_tools.query_failed", package=clean_pkg, error=str(e))
        return {
            "success": False,
            "package": clean_pkg,
            "error": f"Network error contacting OSV API: {str(e)}",
        }


@tool
def check_cve_vulnerabilities(package_name: str, ecosystem: str = "PyPI") -> str:
    """
    Checks Google's OSV open-source vulnerability database for active security CVEs and advisories
    for a specific package or framework (e.g. 'fastapi', 'requests', 'urllib3', 'next', 'express', 'tokio').
    Use this tool whenever an item or user stack mentions an open-source library to verify if any
    high or critical security advisories exist.

    Args:
        package_name: Name of the package, e.g. 'urllib3' or 'fastapi'.
        ecosystem: Package ecosystem: 'PyPI' (default for Python), 'npm' (JavaScript/TypeScript), 'crates.io' (Rust), or 'Go'.

    Returns:
        Concise status with CVE IDs, severity, summary, and fixed version (~60 tokens).
    """
    res = query_osv_vulnerabilities(package_name=package_name, ecosystem=ecosystem)
    if not res.get("success"):
        return f"Could not verify security status for package '{package_name}': {res.get('error')}"

    if not res.get("vulnerable"):
        return f"Package '{package_name}' ({ecosystem}): ✅ No open security vulnerabilities found in OSV database."

    advisories = res.get("advisories", [])
    lines = [f"Package '{package_name}' ({ecosystem}): ⚠️ Found {len(advisories)} Security Advisory(ies):"]
    for adv in advisories:
        fix_str = f" [Fixed in: >= {adv['fixed_version']}]" if adv.get("fixed_version") else " [No fix specified]"
        lines.append(f"- [{adv['severity']}] {adv['id']}: {adv['summary']}{fix_str}")

    return "\n".join(lines)

