import os
import requests
from typing import Optional

class GithubTools:

    def __init__(self):
        self.token = '',

    def fetch_manual_readme(self, repo_url:str)-> Optional[str]:
        try:
            parts = repo_url.rstrip('/').split('/')
            repo_full = f"{parts[-2]}/{parts[-1]}"
            
            api_url = f"https://api.github.com/repos/{repo_full}/readme"
            headers = {
                "Accept": "application/vnd.github.v3.raw",
                "Authorization": f"token {self.token}"
            }
            
            response = requests.get(api_url, headers=headers)
            
            if response.status_code == 200:
                return response.text
            else:
                print(f"GitHub API error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Failed to fetch README: {e}")
            return None





