import sqlite3
import shutil
import os

paths = [
    r'C:\Users\princ\chrome_upwork_profile\Default\Network\Cookies',
    r'C:\Users\princ\chrome_upwork_profile_2\Default\Network\Cookies',
    r'C:\Users\princ\chrome_upwork_profile_3\Default\Network\Cookies',
    r'C:\Users\princ\AppData\Local\Google\Chrome\User Data\Profile 3\Network\Cookies',
    r'C:\Users\princ\AppData\Local\Google\Chrome\User Data\Default\Network\Cookies'
]

for path in paths:
    if os.path.exists(path):
        tmp = 'output/tmp_c.db'
        try:
            shutil.copyfile(path, tmp)
            conn = sqlite3.connect(tmp)
            c = conn.cursor()
            rows = c.execute("SELECT name, host_key FROM cookies WHERE host_key LIKE '%upwork%'").fetchall()
            names = [r[0] for r in rows]
            has_auth = any(n in names for n in ['oauth2_global_js_token', 'user_uid', 'zp_user_id', 'master_access_token'])
            print(f"{path}\n  -> Upwork cookies: {len(rows)} | Has auth: {has_auth}")
            auth_names = [n for n in names if any(k in n.lower() for k in ['token', 'user', 'session', 'auth', 'login'])]
            print(f"  -> Key cookies: {auth_names[:10]}\n")
            conn.close()
            os.remove(tmp)
        except Exception as e:
            print(f"{path}\n  -> Error: {e}\n")
