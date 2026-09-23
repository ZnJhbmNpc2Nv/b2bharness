import json
import os

os.makedirs("data", exist_ok=True)
with open("data/keys.json", "w") as f:
    json.dump({
        "key": "YOUR_API_KEY_HERE",
        "active": True
    }, f)
print("Keys saved successfully.")
