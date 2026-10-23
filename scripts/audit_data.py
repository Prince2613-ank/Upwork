import glob, csv, json, os

print("=== CSV FILES ===")
for f in glob.glob("**/*.csv", recursive=True):
    try:
        with open(f, "r", encoding="utf-8") as fp:
            rows = list(csv.reader(fp))
            print(f"{f}: {len(rows)-1} rows (excl header)")
    except Exception as e:
        print(f"{f}: error {e}")

print("\n=== JSON FILES (Jobs) ===")
for f in glob.glob("**/*.json", recursive=True):
    if any(x in f for x in ["package", "node_modules", ".vscode", "__pycache__", "checkpoint", "errors"]):
        continue
    try:
        with open(f, "r", encoding="utf-8") as fp:
            d = json.load(fp)
            if isinstance(d, dict) and "jobs" in d:
                print(f"{f}: dict with {len(d['jobs'])} jobs")
            elif isinstance(d, list):
                print(f"{f}: list of {len(d)} items")
    except Exception as e:
        pass
