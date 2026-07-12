import subprocess
import sys
import os
import time

if len(sys.argv) < 2:
    print("Usage: python login_setup.py <user_id>")
    sys.exit(1)

USER_ID = sys.argv[1]
PROFILE_DIR = os.path.abspath(f"profiles/{USER_ID}")
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"  # adjust if needed

os.makedirs(PROFILE_DIR, exist_ok=True)

print(f"[setup] launching real Chrome with profile dir: {PROFILE_DIR}")
proc = subprocess.Popen([
    CHROME_PATH,
    f"--user-data-dir={PROFILE_DIR}",
    "https://accounts.google.com/signin",
])

print("[setup] log in manually in the Chrome window that opened.")
input("[setup] once fully logged in, close that Chrome window, then press Enter here... ")

print(f"[setup] done. Profile saved at {PROFILE_DIR}")
print("[setup] this profile dir is now ready to be used by bot.py")