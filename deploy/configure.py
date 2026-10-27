"""Prepare private deployment values and report missing fields without printing secrets."""
import argparse
import re
import secrets
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def placeholder(value):
    return not value or any(x in value.lower() for x in ('example.com', 'replace', 'change-me', 'changeme', 'your-domain'))


def validate(values, token_path):
    errors = []
    domain = values.get('DOMAIN', '')
    if placeholder(domain) or not re.fullmatch(r'[a-zA-Z0-9.-]+', domain):
        errors.append('DOMAIN: set the real server hostname')
    public = urlsplit(values.get('PUBLIC_URL', ''))
    if public.scheme != 'https' or public.netloc != domain or public.path not in ('', '/'):
        errors.append('PUBLIC_URL: must match https://DOMAIN')
    if not values.get('DASHBOARD_PASSWORD_SCRYPT', '').startswith('scrypt$32768$8$3$'):
        errors.append('DASHBOARD_PASSWORD_SCRYPT: configure the dashboard login')
    if not re.fullmatch(r'[a-fA-F0-9]{32,}', values.get('POSTGRES_PASSWORD', '')):
        errors.append('POSTGRES_PASSWORD: use at least 32 random hex characters')
    if values.get('SESSION_COOKIE_SECURE') != 'true':
        errors.append('SESSION_COOKIE_SECURE: must be true for HTTPS deployment')
    if values.get('GOOGLE_CHAT_SPACE') and not token_path.is_file():
        errors.append('GOOGLE_CHAT_TOKEN_FILE: copy the OAuth token into deploy/secrets')
    if not values.get('GOOGLE_CHAT_WEBHOOK'):
        errors.append('GOOGLE_CHAT_WEBHOOK: configure issue notifications')
    if not values.get('GOOGLE_CHAT_SPACE'):
        errors.append('GOOGLE_CHAT_SPACE: configure HTML delivery')
    return errors


def configure(root, from_local=False, domain=None):
    template = dotenv_values(root / '.env.server.example', interpolate=False)
    existing = dotenv_values(root / '.env.server', interpolate=False)
    values = {k: existing.get(k, v) or '' for k, v in template.items()}
    if placeholder(values['POSTGRES_PASSWORD']):
        values['POSTGRES_PASSWORD'] = secrets.token_hex(32)
    if domain:
        if not re.fullmatch(r'[a-zA-Z0-9.-]+', domain):
            raise ValueError('Use a hostname without a protocol or path')
        values.update(DOMAIN=domain, PUBLIC_URL='https://' + domain)
    values['SESSION_COOKIE_SECURE'] = 'true'
    values['GOOGLE_CHAT_TOKEN_FILE'] = '/secrets/google-chat-token.json'
    target = root / 'deploy' / 'secrets' / 'google-chat-token.json'
    if from_local:
        local = dotenv_values(root / '.env.local', interpolate=False)
        for key in ('DASHBOARD_USER', 'DASHBOARD_PASSWORD_SCRYPT', 'GOOGLE_CHAT_WEBHOOK', 'GOOGLE_CHAT_SPACE'):
            if local.get(key) and (not values.get(key) or placeholder(values[key])):
                values[key] = local[key]
        source = Path(local.get('GOOGLE_CHAT_TOKEN_FILE') or '__missing__')
        if not source.is_absolute():
            source = root / source
        if source.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o600)
    path = root / '.env.server'
    # Quote hashes and URLs to stop Compose from expanding dollar signs.
    content = '# Private deployment values. Do not commit.\n'
    content += ''.join(k + "='" + v.replace('\\', '\\\\').replace("'", "\\'") + "'\n" for k, v in values.items())
    temporary = root / '.env.server.tmp'
    temporary.write_text(content, encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)
    return validate(values, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-local', action='store_true', help='Reuse local login and Chat credentials')
    parser.add_argument('--domain')
    parser.add_argument('--check', action='store_true', help='Validate without changing files')
    args = parser.parse_args()
    errors = (validate(dotenv_values(ROOT / '.env.server', interpolate=False), ROOT / 'deploy/secrets/google-chat-token.json')
              if args.check else configure(ROOT, args.from_local, args.domain))
    print('Deployment configuration checked.' if args.check else 'Private deployment configuration prepared.')
    for error in errors:
        print('Required: ' + error)
    if errors:
        raise SystemExit(1)
    print('Configuration ready. Verify server DNS, TLS, browser logins and Chat delivery on Linux.')


if __name__ == '__main__':
    main()
