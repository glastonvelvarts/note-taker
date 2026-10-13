import os
import shutil
import subprocess
from pathlib import Path

from .paths import data_dir

CHROME_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def find_chrome() -> str:
    for candidate in (os.getenv("CHROME_PATH"), *CHROME_CANDIDATES):
        if candidate and (path := shutil.which(candidate)):
            return path
    raise FileNotFoundError("Google Chrome not found, set CHROME_PATH to its executable")


def login(profile: str) -> Path:
    """Open real Chrome so the user can sign in to Google; the session is kept in the profile."""
    profile_dir = data_dir("profiles") / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            find_chrome(),
            f"--user-data-dir={profile_dir}",
            "https://accounts.google.com/signin",
        ]
    )
    input("Sign in to Google in the Chrome window, close it, then press Enter... ")
    return profile_dir
