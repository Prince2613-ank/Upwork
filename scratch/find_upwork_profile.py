import sqlite3
import shutil
import os
import glob

base = r'C:\Users\princ\AppData\Local\Google\Chrome\User Data'
for item in os.listdir(base):
    full = os.path.join(base, item)
    if os.path.isdir(full):
        cookie_file = os.path.join(full, 'Network', 'Cookies')
        if os.path.exists(cookie_file):
            tmp = f'output/check_{item}.db'
            try:
                shutil.copyfile(cookie_file, tmp)
                conn = sqlite3.connect(tmp)
                c = conn.cursor()
                rows = c.execute("SELECT name, host_key FROM cookies WHERE host_key LIKE '%upwork%'").fetchall()
                names = [r[0] for r in rows]
                has_auth = any(n in names for n in ['oauth2_global_js_token', 'user_uid', 'zp_user_id'])
                if len(rows) > 0:
                    print(f"Profile: {item} | Upwork Cookies: {len(rows)} | Has Auth: {has_auth}")
                    auth_keys = [n for n in names if any(k in n.lower() for k in ['token', 'user', 'auth', 'login', 'sess'])]
                    print(f"   Auth tokens: {auth_keys[:8]}")
                conn.close()
                os.remove(tmp)
            except Exception as e:
                pass
