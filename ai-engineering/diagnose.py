"""Direct SSH diagnostic."""
import asyncio, sys, os
sys.path.insert(0, r"D:\sir projectss\Britsync AI Engineering Department (AIED)\ai-engineering")

from deployment.ssh import SSHConnection, decrypt_secret
from deployment.models import VPSServer, AuthMethod

# Load deploy key and check if there are any encrypted credentials stored
from deployment.ssh import _get_fernet

fernet = _get_fernet()

# Check the API logs for VPS password
import json
api_log = r"D:\sir projectss\Britsync AI Engineering Department (AIED)\ai-engineering\data\pipeline_debug.log"
if os.path.exists(api_log):
    with open(api_log) as f:
        content = f.read()
    # Find any credential references
    for line in content.split("\n")[-200:]:
        if "84.247" in line or "mehdia" in line or "decrypt" in line.lower():
            print(line[:200])

# Try to find VPS credentials from the deploy data files
data_dir = r"D:\sir projectss\Britsync AI Engineering Department (AIED)\ai-engineering\data"
for root, dirs, files in os.walk(data_dir):
    for fname in files:
        if fname.endswith('.json'):
            fp = os.path.join(root, fname)
            try:
                with open(fp) as f:
                    content = f.read()
                if "84.247" in content or "mehdia" in content:
                    print(f"\n=== {fp} ===")
                    print(content[:500])
            except:
                pass

print("\nNo VPS password found in stored data. Need user to provide it.")
