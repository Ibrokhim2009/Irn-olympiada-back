import requests
import os
import datetime
from django.core.cache import cache
from environs import Env

env = Env()
env.read_env()

ESKIZ_EMAIL = env.str("ESKIZ_EMAIL", "")
ESKIZ_PASSWORD = env.str("ESKIZ_PASSWORD", "")
ESKIZ_BASE_URL = "https://notify.eskiz.uz/api/"
ESKIZ_TOKEN_CACHE_KEY = f"eskiz_token_{ESKIZ_EMAIL}"

def get_eskiz_headers(token):
    return {
        'Authorization': f'Bearer {token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

def format_eskiz_error(status_code, response_text):
    try:
        import json
        data = json.loads(response_text)
        
        # Check standard error messages
        msg = data.get('message') or data.get('error') or data.get('error_description')
        if not msg and isinstance(data.get('data'), dict):
            inner_data = data.get('data')
            msg = inner_data.get('message') or inner_data.get('error') or inner_data.get('alert')
            
        if msg:
            if isinstance(msg, dict):
                parts = []
                for k, v in msg.items():
                    if isinstance(v, list):
                        parts.append(f"{k}: {', '.join(map(str, v))}")
                    else:
                        parts.append(f"{k}: {v}")
                return "; ".join(parts)
            elif isinstance(msg, list):
                return ", ".join(map(str, msg))
            return str(msg)
            
        # Check validation errors (e.g. {"errors": {"template": ["min=10"]}})
        errors = data.get('errors')
        if not errors and isinstance(data.get('data'), dict):
            errors = data.get('data').get('errors')
            
        if errors and isinstance(errors, dict):
            parts = []
            for k, v in errors.items():
                if isinstance(v, list):
                    parts.append(f"{k}: {', '.join(map(str, v))}")
                else:
                    parts.append(f"{k}: {v}")
            return "; ".join(parts)
    except Exception:
        pass
    
    if response_text and len(response_text) < 150:
        return f"Eskiz API Error {status_code}: {response_text}"
    return f"Eskiz API Error: {status_code}"

def get_eskiz_token():
    token = cache.get(ESKIZ_TOKEN_CACHE_KEY)
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
            cache.set(ESKIZ_TOKEN_CACHE_KEY, token, 60 * 60 * 24 * 29)
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
    headers = get_eskiz_headers(token)
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        print(f"Eskiz send SMS response to {phone}: {response.text}")
        if response.status_code == 401:
            cache.delete(ESKIZ_TOKEN_CACHE_KEY)
        if response.status_code in [200, 201]:
            return response.json()
        else:
            error_msg = format_eskiz_error(response.status_code, response.text)
            return {"status": "error", "message": error_msg}
    except Exception as e:
        print(f"Eskiz send SMS error: {e}")
        return {"status": "error", "message": str(e)}

import json
import time

TEMPLATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sms_templates.json')

def load_local_templates():
    if not os.path.exists(TEMPLATES_FILE):
        return []
    try:
        with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_local_templates(templates):
    try:
        with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(templates, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False

def fetch_eskiz_templates():
    token = get_eskiz_token()
    if not token:
        return []
    
    headers = get_eskiz_headers(token)
    all_templates = []
    page = 1
    
    while True:
        url = f"{ESKIZ_BASE_URL}user/templates?page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 401:
                cache.delete(ESKIZ_TOKEN_CACHE_KEY)
                token = get_eskiz_token()
                if not token:
                    break
                headers = get_eskiz_headers(token)
                continue
                
            if response.status_code != 200:
                break
                
            data = response.json()
            if isinstance(data, list):
                all_templates.extend(data)
                break
                
            if isinstance(data, dict):
                inner_data = data.get('data')
                if isinstance(inner_data, list):
                    all_templates.extend(inner_data)
                    break
                elif isinstance(inner_data, dict):
                    page_templates = inner_data.get('data', [])
                    if isinstance(page_templates, list):
                        all_templates.extend(page_templates)
                    
                    last_page = inner_data.get('last_page')
                    current_page = inner_data.get('current_page')
                    
                    if last_page and current_page and current_page < last_page:
                        page += 1
                    else:
                        break
                else:
                    break
            else:
                break
        except Exception as e:
            print(f"Error fetching Eskiz templates on page {page}: {e}")
            break
            
    return all_templates

def get_templates():
    local_templates = load_local_templates()
    
    # Always include the three standard test templates so that developers using test accounts
    # can test SMS sending functionality in development.
    now_iso = datetime.datetime.utcnow().isoformat() + 'Z'
    all_templates = [
        {
            'id': 'test_uz',
            'text': 'Bu Eskiz dan test',
            'status': 'approved',
            'created_at': now_iso,
            'note': 'Tizim shabloni (uz)',
            'type': 'service'
        },
        {
            'id': 'test_ru',
            'text': 'Test ot Eskiz',
            'status': 'approved',
            'created_at': now_iso,
            'note': 'Sistemnyj shablon (ru)',
            'type': 'service'
        },
        {
            'id': 'test_en',
            'text': 'This is test from Eskiz',
            'status': 'approved',
            'created_at': now_iso,
            'note': 'System template (en)',
            'type': 'service'
        }
    ]
    
    templates_dict = {}
    
    # Process Eskiz templates
    eskiz_templates = fetch_eskiz_templates()
    for t in eskiz_templates:
        text = t.get('template') or t.get('text') or ''
        clean_text = text.strip()
        if not clean_text:
            continue
            
        status = t.get('status') or 'approved'
        status_lower = str(status).lower()
        if 'approve' in status_lower or 'activ' in status_lower or 'одобрен' in status_lower:
            status_mapped = 'approved'
        elif 'moder' in status_lower or 'process' in status_lower or 'модераци' in status_lower or 'процесс' in status_lower:
            status_mapped = 'moderation'
        elif 'reject' in status_lower or 'cancel' in status_lower or 'отклон' in status_lower or 'отказ' in status_lower:
            status_mapped = 'rejected'
        else:
            status_mapped = status_lower
            
        template_obj = {
            'id': t.get('id'),
            'text': text,
            'status': status_mapped,
            'created_at': t.get('created_at') or t.get('created_date') or now_iso,
            'note': t.get('note') or t.get('name') or '',
            'type': 'service'
        }
        
        existing = templates_dict.get(clean_text)
        if not existing:
            templates_dict[clean_text] = template_obj
        else:
            # Prioritize 'approved' status over others
            if template_obj['status'] == 'approved' and existing['status'] != 'approved':
                templates_dict[clean_text] = template_obj
            elif template_obj['status'] == 'moderation' and existing['status'] == 'rejected':
                templates_dict[clean_text] = template_obj
                
    # Process local templates
    for t in local_templates:
        clean_text = t['text'].strip()
        template_obj = t
        
        existing = templates_dict.get(clean_text)
        if not existing:
            templates_dict[clean_text] = template_obj
        else:
            # Prioritize 'approved' status over others
            if template_obj.get('status') == 'approved' and existing['status'] != 'approved':
                templates_dict[clean_text] = template_obj
            elif template_obj.get('status') == 'moderation' and existing['status'] == 'rejected':
                templates_dict[clean_text] = template_obj

    # Add the test templates first
    seen_texts = {t['text'].strip() for t in all_templates}
    
    # Add mapped/deduplicated templates from Eskiz and local storage
    for clean_text, tpl in templates_dict.items():
        if clean_text not in seen_texts:
            seen_texts.add(clean_text)
            all_templates.append(tpl)
            
    # Sort templates by created_at descending (newest first)
    def get_sort_key(tpl):
        dt_str = tpl.get('created_at') or ''
        return dt_str.replace('T', ' ').replace('Z', '')
        
    try:
        all_templates.sort(key=get_sort_key, reverse=True)
    except Exception:
        pass
        
    return all_templates


def get_templates_debug():
    token = get_eskiz_token()
    if not token:
        return {"error": "Failed to get Eskiz token"}
    
    endpoints = ["user/templates", "user/template", "template", "message/sms/template", "nick/me"]
    headers = get_eskiz_headers(token)
    
    results = {}
    for ep in endpoints:
        url = f"{ESKIZ_BASE_URL}{ep}"
        try:
            response = requests.get(url, headers=headers, timeout=35)
            results[ep] = {
                "status_code": response.status_code,
                "body": response.text[:2000]
            }
        except Exception as e:
            results[ep] = {
                "error": str(e)
            }
    return results


def add_template_debug(text):
    token = get_eskiz_token()
    if not token:
        return {"error": "Failed to get Eskiz token"}
    url = f"{ESKIZ_BASE_URL}user/template"
    payload = { 'template': text }
    headers = get_eskiz_headers(token)
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=35)
        return {
            "status_code": response.status_code,
            "body": response.text[:2000]
        }
    except Exception as e:
        return {"error": str(e)}


def add_template(name, text):
    local_templates = load_local_templates()
    
    # Check if template with same text already exists
    for t in local_templates:
        if t['text'] == text:
            return {"status": "error", "message": "Template with this text already exists"}
            
    # Attempt to submit to Eskiz for moderation
    token = get_eskiz_token()
    eskiz_id = None
    if token:
        url = f"{ESKIZ_BASE_URL}user/template"
        payload = { 'template': text }
        headers = get_eskiz_headers(token)
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=15)
            print(f"Eskiz submit template response: {response.status_code} - {response.text}")
            if response.status_code in [200, 201]:
                res_data = response.json()
                inner = res_data.get('data') or res_data
                if isinstance(inner, dict):
                    eskiz_id = inner.get('id')
        except Exception as e:
            print(f"Eskiz submit template error: {e}")
            
    now_iso = datetime.datetime.utcnow().isoformat() + 'Z'
    new_id = eskiz_id or int(time.time() * 1000)
    new_template = {
        'id': new_id,
        'text': text,
        'status': 'moderation' if eskiz_id else 'approved',
        'created_at': now_iso,
        'note': name,
        'type': 'service'
    }
    local_templates.append(new_template)
    if save_local_templates(local_templates):
        return {"status": "success", "message": "Template created successfully", "data": new_template}
    return {"status": "error", "message": "Failed to save template"}

def delete_template(template_id):
    if template_id in ['test_uz', 'test_ru', 'test_en']:
        return {"status": "error", "message": "Cannot delete system test templates"}
        
    local_templates = load_local_templates()
    
    # Filter out the deleted template (handle both string and int ids)
    updated_templates = [t for t in local_templates if str(t['id']) != str(template_id)]
    
    if len(updated_templates) == len(local_templates):
        return {"status": "error", "message": "Template not found"}
        
    if save_local_templates(updated_templates):
        return {"status": "success", "message": "Template deleted successfully"}
    return {"status": "error", "message": "Failed to save template"}


def get_balance():
    """
    Fetches the current SMS account balance from the Eskiz gateway.
    Tries multiple known endpoints for balance/user info.
    Returns a dict with 'balance' (float) or 'error' (str).
    """
    token = get_eskiz_token()
    if not token:
        return {"status": "error", "message": "Failed to get Eskiz token"}

    headers = get_eskiz_headers(token)

    # Eskiz documents 'user/get-limit' as the balance/limit endpoint
    endpoints_to_try = [
        "user/get-limit",
        "auth/user",
        "user",
    ]

    last_error = "Could not retrieve balance from Eskiz API"

    for ep in endpoints_to_try:
        try:
            url = f"{ESKIZ_BASE_URL}{ep}"
            response = requests.get(url, headers=headers)
            print(f"Eskiz GET {ep} status: {response.status_code}, body: {response.text[:300]}")

            if response.status_code == 401:
                cache.delete(ESKIZ_TOKEN_CACHE_KEY)
                last_error = format_eskiz_error(response.status_code, response.text)
                break

            if response.status_code == 200:
                data = response.json()

                # Try to extract balance from various response shapes
                balance = None

                # Shape: {"status":"success","data":{"balance":"1234.56"}}
                inner = data.get('data') or data
                if isinstance(inner, dict):
                    bal = inner.get('balance') or inner.get('sms_count') or inner.get('limit')
                    if bal is not None:
                        try:
                            balance = float(bal)
                        except (ValueError, TypeError):
                            pass

                if balance is not None:
                    return {"status": "success", "balance": balance}
            else:
                last_error = format_eskiz_error(response.status_code, response.text)

        except Exception as e:
            last_error = str(e)
            print(f"Eskiz get_balance error for {ep}: {e}")
            continue

    return {"status": "error", "message": last_error}

