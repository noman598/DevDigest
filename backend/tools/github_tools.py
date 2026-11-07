# backend/tools/github_tools.py
from datetime import datetime, timezone
import re
from typing import Any, Dict, Optional
import httpx
from langchain_core.tools import tool

from config import config
from utils.logger import log


def _clean_repo_identifier(repo_input: str) -> Optional[tuple[str, str]]:
    """
    Extracts (owner, repo) from various string formats:
    - 'owner/repo'
    - 'https://github.com/owner/repo'
    - 'https://github.com/owner/repo.git'
    - 'https://github.com/owner/repo/tree/main'
    """
    if not repo_input:
        return None

    cleaned = repo_input.strip()
    cleaned = re.sub(r"^https?://(www\.)?github\.com/", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\.git$", "", cleaned, flags=re.IGNORECASE)
    parts = [p for p in cleaned.split("/") if p]

    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def fetch_github_repo_raw(repo_name: str) -> Dict[str, Any]:
    """
    Directly fetches metadata from GitHub REST API and raw README.
    Returns structured dict with status, metadata, and error if any.
    """
    parsed = _clean_repo_identifier(repo_name)
    if not parsed:
        return {"success": False, "error": f"Invalid repository format '{repo_name}'. Expected 'owner/repo'."}

    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{owner}/{repo}"

    headers = {
        "User-Agent": getattr(config, "USER_AGENT", "DevSnack-Agent/1.0"),
        "Accept": "application/vnd.github.v3+json",
    }
    github_token = getattr(config, "GITHUB_TOKEN", "")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(api_url)

            if resp.status_code == 404:
                return {"success": False, "error": f"Repository '{owner}/{repo}' not found on GitHub."}
            if resp.status_code == 403:
                return {"success": False, "error": f"GitHub API rate limit exceeded or access forbidden for '{owner}/{repo}'."}
            if resp.status_code != 200:
                return {"success": False, "error": f"GitHub API returned HTTP {resp.status_code}."}

            data = resp.json()

            # License info
            license_data = data.get("license") or {}
            license_spdx = license_data.get("spdx_id") or license_data.get("name") or "None"

            # Compute maintenance activity
            archived = data.get("archived", False)
            pushed_at = data.get("pushed_at")
            maintenance = "Unknown"

            if archived:
                maintenance = "ARCHIVED (read-only, no longer maintained)"
            elif pushed_at:
                try:
                    clean_iso = pushed_at.replace("Z", "+00:00")
                    pushed_dt = datetime.fromisoformat(clean_iso)
                    now = datetime.now(timezone.utc)
                    days = (now - pushed_dt).days
                    if days <= 7:
                        maintenance = f"Very Active (pushed {days} days ago)"
                    elif days <= 30:
                        maintenance = f"Active (pushed {days} days ago)"
                    elif days <= 90:
                        maintenance = f"Moderate (pushed {days // 30} months ago)"
                    else:
                        maintenance = f"Stale/Inactive (pushed {days // 30} months ago)"
                except Exception:
                    maintenance = f"Pushed {pushed_at[:10]}"

            # Fetch a brief README excerpt if description is short or missing
            desc = data.get("description") or ""
            readme_excerpt = ""
            if len(desc) < 60:
                try:
                    readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"
                    readme_resp = client.get(readme_url)
                    if readme_resp.status_code == 200:
                        lines = [
                            line.strip()
                            for line in readme_resp.text.splitlines()
                            if line.strip() and not line.strip().startswith(("#", "[!", "<", "![", "```", "---"))
                        ]
                        if lines:
                            readme_excerpt = " ".join(lines[:3])[:300]
                except Exception as e:
                    log.debug("github_tools.readme_fetch_failed", error=str(e))

            return {
                "success": True,
                "owner": owner,
                "repo": repo,
                "full_name": f"{owner}/{repo}",
                "description": desc,
                "readme_excerpt": readme_excerpt,
                "language": data.get("language") or "Unknown",
                "topics": data.get("topics") or [],
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "license": license_spdx,
                "archived": archived,
                "maintenance_status": maintenance,
                "pushed_at": pushed_at,
            }

    except httpx.RequestError as exc:
        log.warning("github_tools.request_error", repo=f"{owner}/{repo}", error=str(exc))
        return {"success": False, "error": f"Network error contacting GitHub API: {str(exc)}"}


@tool
def inspect_github_repo(repo_name: str) -> str:
    """
    Inspects a GitHub repository to get verified technical metadata.
    Call this tool whenever an item is a GitHub repository to inspect its primary language,
    license, maintenance activity, star count, and real description before finalizing enrichment.

    Args:
        repo_name: The repository identifier, e.g. 'browser-use/browser-use' or 'https://github.com/PostHog/posthog'.

    Returns:
        A concise factual summary of the repository's tech stack, license, health, and purpose (~80 tokens).
    """
    details = fetch_github_repo_raw(repo_name)
    if not details.get("success"):
        return f"Could not inspect GitHub repository '{repo_name}': {details.get('error')}"

    topics = details.get("topics", [])
    topics_str = f" | Topics: {', '.join(topics[:6])}" if topics else ""
    readme_str = f"\nREADME Overview: {details['readme_excerpt']}" if details.get("readme_excerpt") else ""

    return (
        f"Repository: {details['full_name']}\n"
        f"Primary Language: {details['language']}{topics_str}\n"
        f"License: {details['license']}\n"
        f"Maintenance: {details['maintenance_status']}\n"
        f"Stats: {details['stars']:,} stars | {details['forks']:,} forks | {details['open_issues']} open issues\n"
        f"Description: {details['description']}{readme_str}"
    )

