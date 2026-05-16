import requests
import os
from django.core.cache import cache
from environs import Env

env = Env()
env.read_env()

ESKIZ_EMAIL = env.str("ESKIZ_EMAIL", "")
ESKIZ_PASSWORD = env.str("ESKIZ_PASSWORD", "")
ESKIZ_BASE_URL = "https://notify.eskiz.uz/api/"

def get_eskiz_token():
    token = cache.get("eskiz_token")
    if token:
        return token
    
    url = f"{ESKIZ_BASE_URL}auth/login"
    payload = {
        'email': ESKIZ_EMAIL,
        'password': ESKIZ_PASSWORD
    }
    try:
        response = requests.post(url, data=payload)
        data = response.json()
        if response.status_code == 200:
            token = data.get('data', {}).get('token')
            # Token is valid for 30 days, we cache it for 29 days
            cache.set("eskiz_token", token, 60 * 60 * 24 * 29)
            return token
    except Exception as e:
        print(f"Eskiz login error: {e}")
    return None

def send_sms(mobile_phone, message, from_name="4546"):
    token = get_eskiz_token()
    if not token:
        return {"status": "error", "message": "Failed to get token"}
    
    url = f"{ESKIZ_BASE_URL}message/sms/send"
    # Ensure phone number is in correct format (998XXXXXXXXX)
    phone = str(mobile_phone).replace("+", "").replace(" ", "")
    
    payload = {
        'mobile_phone': phone,
        'message': message,
        'from': from_name,
    }
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_templates():
    token = get_eskiz_token()
    if not token:
        return []
    
    # Trying the simplified template endpoint
    url = f"{ESKIZ_BASE_URL}template"
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Eskiz get templates response: {response.text}")
        data = response.json()
        return data if isinstance(data, list) else data.get('data', [])
    except Exception as e:
        print(f"Eskiz get templates error: {e}")
        return []

def add_template(name, text):
    token = get_eskiz_token()
    if not token:
        return {"status": "error", "message": "No token"}
    
    # Trying the simplified template endpoint
    url = f"{ESKIZ_BASE_URL}template"
    payload = {
        'name': name,
        'text': text
    }
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        print(f"Eskiz add template status ({url}): {response.status_code}")
        try:
            return response.json()
        except Exception:
            return {
                "status": "error", 
                "message": f"Eskiz API Error: {response.status_code}",
                "raw_response": response.text[:100]
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}
