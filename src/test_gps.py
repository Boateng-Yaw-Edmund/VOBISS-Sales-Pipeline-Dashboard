import requests

code = "GE-043-1812"

url = "https://mijordie.ghanapostgps.com/user/get_address"

params = {
    "address": code,
    "user_latitude": 5.57,
    "user_longitude": -0.17
}

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, params=params, headers=headers)

print(response.status_code)
print(response.text)