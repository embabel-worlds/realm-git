# realm-git

A git repository's history as a graph you can query, read from a clone when a question reaches it.
Nothing is ingested and nothing is stored.

```cypher
MATCH (f:GitFile {key: 'https://github.com/acme/shop@4f2c9e1!src/main/java/com/acme/Cart.java'})-[:HAS_BLAME]->(b:GitBlameRange)
WHERE b.startLine <= 100 AND b.endLine >= 100
RETURN b.sha, b.authorName, b.authorKind, b.title
```

That is the commit that last changed line 100, who wrote it, and whether a coding agent helped.

```
GitProject ─HAS_COMMIT▶ GitCommit ─CHANGED▶ GitFileChange
GitFile    ─HAS_BLAME▶  GitBlameRange
```

## Naming a repository

The same project keys the code realms use:

| key | read from |
|---|---|
| `https://github.com/acme/shop` | the default branch, at the commit it points to now |
| `https://github.com/acme/shop@v2.1` | a tag, branch or commit |
| `projects/shop` | a folder under the world's `data/` that holds a `.git` directory |

A file is `<project key>!<path from the repository root>`.

Any git host works, and so does a repository that exists only on disk: no forge's API is called. A
private repository on github.com is read with the appliance's GitHub token.

## Views

| view | question |
|---|---|
| `GitCommits(project, limit?)` | the recent commits: who, when, with whose help, how many files |
| `GitCommitCharacter(project, limit?)` | what kind of change each commit was: java, documentation, configuration, tests, mixed |
| `GitCharacterMix(project)` | how many commits touched each kind of file, by who wrote them |
| `GitChanges(project, sha)` | the files one commit changed, with kind, language and lines |
| `GitBlame(file)` | one file as runs of lines, each with the commit that last changed it |
| `GitBlameLine(file, line)` | the one commit that last changed one line |

## What a commit is characterised by

The files it touched, by name alone, so no file is read:

- `fileKinds`: the dev vocabulary's kind of each path (source, test, docs, build, config, data,
  other), by the same rule realm-github applies to the files GitHub reports.
- `languages`: the language of each code extension.

`GitCommitCharacter` reduces those to one word. It counts files, not lines; `GitChanges` gives the
lines of one commit.

## The dev vocabulary

A `GitCommit` is a `Commit` and a `GitFileChange` a `FileChange` of
[realm-dev-vocabulary](https://github.com/embabel-worlds/realm-dev-vocabulary), which must be
installed first. A commit's `key` (`github.com/acme/shop@<sha>`) is the key realm-github carries on
the same commit, which is how a line's commit reaches its pull request.

`authorKind` is decided from what git alone records: `assisted` when a `Co-Authored-By` trailer
names a coding agent, `bot` or `agent` when the author's name or address carries `[bot]`, otherwise
`human`. An agent's work committed with no trailer reads as human.

## Limits

- History is read 2,000 commits deep behind the commit a project is read at. A line or a commit
  older than that is reported at the edge of what was read, with `boundary: true`.
- `GitCommits` returns the last 365 days of those commits.
- A merge commit's changes are compared with its first parent.
- A folder is a repository only when it holds a `.git` directory of its own.

## Requires

An Embabel appliance with the `git` producer kind (embabel/me#3990).

## Verify

`GitRealmFaithfulCypherTest` in the appliance's source runs this realm's own types, producers and
views through the engine over a repository of five commits whose answers are known in advance.
