# This is the log of real implimentatoin and trials:

# Step 0: create a virtual environment and install dependencies
```bash
uv venv .venv
source .venv/bin/activate       # activate
uv pip install -r requirements.txt  # now installs into .venv

requirements.txt:
fastapi==0.128.8
uvicorn[standard]==0.39.0
httpx==0.27.2
pydantic==2.41.5

# Step 3 trial: testing the github api

``
python -m pip install requests
```

```python
import requests

# This is ALL it takes to call any API
response = requests.get("https://api.github.com/repos/psf/requests")
data = response.json()         # converts response to a Python dictionary
print(data["description"])     # access any field
```

Step 6:
Create Github_Token and save in .env

**How to create one**
Go to github.com → Settings → Developer settings → Personal access tokens → Tokens (classic)
Click Generate new token
Set expiration (90 days is safe for a project like this)
For scopes: no scopes needed — public repo reads are allowed without any scope
Copy the token immediately (shown only once)
Paste into your .env:

GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

**protect from claude:**

Create or edit .claude/settings.json:

`{
  "permissions": {
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)"
    ]
  }
}`


- run to test: 
`curl -s "http://localhost:8000/debug/repo?owner=psf&repo=requests" | python3 -m json.tool | grep default_branch`

