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

# A view's own word on whether its rows are the whole answer. A PARTIAL outcome is still SUCCEEDED,
# so rows read on status alone (or on `data` being there) count a short answer as the realm's: a
# source that failed under load, or a capped page, reads as drift.
SHORT_PUBLIC = ("PARTIAL", "REDUCTION_FAILED", "COMPUTE_FAILED", "PROPERTY_NOT_STORED",
                "AGENTIC_DEGRADED", "RATE_LIMITED", "SOURCE_UNAVAILABLE", "SOURCE_REJECTED",
                "INVALID_FILTER", "UNPUSHED_FILTER", "TOO_BROAD", "FETCH_CAPPED",
                "INDEX_UNAVAILABLE", "ARGUMENT_REFUSED")


def short(body, figure=None):
    """None when the view says its answer is whole; else the line a check prints in place of the
    figure: `REFUSED: <why>` or `PARTIAL <figure>: <the engine's reason>`."""
    tag = "PARTIAL" if figure is None else f"PARTIAL {figure}"
    if body.get("status") != "SUCCEEDED":
        return f"REFUSED: {body.get('status')} {json.dumps(body.get('error'))[:200]}"
    ws = [w for w in body.get("warnings") or [] if isinstance(w, dict) and w.get("code") in SHORT_PUBLIC]
    if body.get("outcome") not in ("OK", "EMPTY") or ws:
        return f"{tag}: " + (f"{ws[0]['code']}: {ws[0].get('message', '')}" if ws else f"outcome {body.get('outcome')}")[:200]
    return None


failures = 0
last_short = None  # what the latest view said about its own rows; the checks that follow read them


def check(name, expected, actual):
    global failures
    if last_short:
        failures += 1
        print(f"  FAIL {name}: expected {str(expected)[:300]}, got {last_short}")
    elif expected == actual:
        print(f"  ok   {name} = {str(expected)[:100]}")
    else:
        failures += 1
        print(f"  FAIL {name}: expected {str(expected)[:300]}, got {str(actual)[:300]}")

def view(name, args):
    global last_short
    req = urllib.request.Request(f"{APPLIANCE}/api/v1/views/{name}/invoke",
                                 json.dumps({"args": args}).encode(), HDR)
    with urllib.request.urlopen(req, timeout=600) as r:
        body = json.load(r)
    if "data" not in body:
        raise SystemExit(f"view {name} answered without data: {json.dumps(body)[:500]}")
    last_short = short(body, len(body["data"] or []))
    return body["data"] or []

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
