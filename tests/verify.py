"""realm-git battery. L1: every view answers by name. L2: each figure reconciled exactly
against `git` run over a bare clone of the same pinned commit.

Reads APPLIANCE and AUTH (user:pass; EMBABEL_AUTH is accepted too)."""
import base64, collections, datetime, json, os, subprocess, sys, tempfile, urllib.request

APPLIANCE = os.environ.get("APPLIANCE", "http://127.0.0.1:11043").rstrip("/")
AUTH = os.environ.get("AUTH") or os.environ.get("EMBABEL_AUTH")
if not AUTH:
    sys.exit("set AUTH=user:pass")
REPO = "https://github.com/embabel-worlds/realm-git"
SHA = "b02ef8960b1b961b09dd1308f0a13f10fc3e6d4d"     # v0.1.0
PROJECT = f"{REPO}@{SHA}"
HDR = {"Authorization": "Basic " + base64.b64encode(AUTH.encode()).decode(), "Content-Type": "application/json"}

failures = 0
def check(name, expected, actual):
    global failures
    if expected == actual:
        print(f"  ok   {name} = {str(expected)[:100]}")
    else:
        failures += 1
        print(f"  FAIL {name}: expected {str(expected)[:300]}, got {str(actual)[:300]}")

def view(name, args):
    req = urllib.request.Request(f"{APPLIANCE}/api/v1/views/{name}/invoke",
                                 json.dumps({"args": args}).encode(), HDR)
    with urllib.request.urlopen(req, timeout=600) as r:
        body = json.load(r)
    if "data" not in body:
        raise SystemExit(f"view {name} answered without data: {json.dumps(body)[:500]}")
    return body["data"]

work = tempfile.mkdtemp()
git_dir = os.path.join(work, "repo.git")
subprocess.run(["git", "clone", "-q", "--bare", REPO + ".git", git_dir], check=True)
def git(*a):
    return subprocess.run(["git", "--git-dir", git_dir, *a], check=True, capture_output=True, text=True).stdout

print("== L0: ground truth, from git directly ==")
year_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
log = [l.split("\x1f") for l in git("log", "--format=%H\x1f%aI\x1f%P", SHA).splitlines()]
commits = [(h, datetime.datetime.fromisoformat(at).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), p.split())
           for h, at, p in log]
window = [c for c in commits if c[1] >= year_ago]
churn = collections.Counter()
for h, at, parents in window:
    if len(parents) > 1:
        continue
    names = git("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", h).split()
    for path in names[:100]:
        churn[path] += 1
tip_numstat = {}
for line in git("diff-tree", "--root", "--no-commit-id", "--numstat", "-r", SHA).splitlines():
    a, d, path = line.split("\t")
    tip_numstat[path] = (int(a), int(d))
blame_file = "realm.yml"
blame = {}
for line in git("blame", "--porcelain", SHA, "--", blame_file).splitlines():
    parts = line.split()
    if len(parts) >= 3 and len(parts[0]) == 40 and parts[1].isdigit() and parts[2].isdigit():
        blame[int(parts[2])] = parts[0]
history_file = "views/git.yml"
touched = set(git("log", "--format=%H", SHA, "--", history_file).split())
print(f"  {len(commits)} commits, {len(window)} in the last 365 days; tip changes {len(tip_numstat)} files; "
      f"{blame_file} has {len(blame)} lines")

print("== L1+L2: every view by name, reconciled ==")
rows = view("GitCommits", {"project": PROJECT, "limit": 1000})
check("GitCommits: commits in the window", sorted(c[0] for c in window), sorted(r["sha"] for r in rows))
check("GitCommits: newest first", window[0][0] if window else None, rows[0]["sha"] if rows else None)

rows = view("GitCommitCharacter", {"project": PROJECT, "limit": 1000})
check("GitCommitCharacter: one row per commit", sorted(c[0] for c in window), sorted(r["sha"] for r in rows))
check("GitCommitCharacter: every commit characterised", True, all(r["character"] for r in rows))

rows = view("GitCharacterMix", {"project": PROJECT})
check("GitCharacterMix: commits summed over author kinds", len(window), sum(r["commits"] for r in rows))

rows = view("GitChanges", {"project": PROJECT, "sha": SHA})
check("GitChanges: files of the tip commit", sorted(tip_numstat), sorted(r["path"] for r in rows))
check("GitChanges: lines added and deleted per file", tip_numstat, {r["path"]: (r["added"], r["deleted"]) for r in rows})

rows = view("GitBlame", {"file": f"{PROJECT}!{blame_file}"})
got = {}
for r in rows:
    for n in range(r["fromLine"], r["toLine"] + 1):
        got[n] = r["commit"]
check("GitBlame: every line covered once", sorted(blame), sorted(got))
check("GitBlame: the commit behind each line", {n: s[:7] for n, s in blame.items()}, got)

for line in (1, max(blame)):
    rows = view("GitBlameLine", {"file": f"{PROJECT}!{blame_file}", "line": line})
    check(f"GitBlameLine: line {line}", [blame[line]], [r["sha"] for r in rows])

rows = view("FileChurn", {"project": PROJECT, "limit": 1000})
check("FileChurn: commits per path", dict(churn), {r["path"]: r["commits"] for r in rows})
rows = view("FileChurn", {"project": PROJECT, "under": "views/", "limit": 1000})
check("FileChurn: under is a prefix", {p: n for p, n in churn.items() if p.startswith("views/")},
      {r["path"]: r["commits"] for r in rows})

rows = view("GitLineHistory", {"lines": f"{PROJECT}!{history_file}#1-10"})
check("GitLineHistory: answers", True, len(rows) > 0)
check("GitLineHistory: every change is a commit that touched the file", True, all(r["sha"] in touched for r in rows))
check("GitLineHistory: ends at the commit that wrote the lines", True, bool(rows) and rows[-1]["created"] is True)

if failures:
    print(f"DRIFT FOUND: {failures} check(s) failed")
    sys.exit(1)
print("ALL CHECKS PASS")
