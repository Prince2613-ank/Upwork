import glob

for f in glob.glob('**/*.py', recursive=True):
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            for lno, line in enumerate(fp, 1):
                if 'upwork.com/jobs/' in line and any(c in line for c in ['{', '%', '+']):
                    print(f'{f}:{lno}: {line.strip()[:100]}')
    except Exception:
        pass
