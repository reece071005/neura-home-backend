import requests
import json

url = "http://localhost:8080/completion"
headers = {"Content-Type": "application/json"}
payload = {
    "prompt": "ما هي عاصمة الإمارات؟",
    "n_predict": 128
}

response = requests.post(url, headers=headers, data=json.dumps(payload))

# Print full response
print(response.json()["content"])
