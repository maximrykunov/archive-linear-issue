# Archive a Linear issue

One folder. Copy it into the skills directory of the agent you use:

| Agent | Folder |
| --- | --- |
| Cursor, you only | `~/.cursor/skills/archive-linear-issue` |
| Cursor, a repository | `.cursor/skills/archive-linear-issue` |
| Claude Code, you only | `~/.claude/skills/archive-linear-issue` |
| Claude Code, a repository | `.claude/skills/archive-linear-issue` |

The agent needs Python 3 and a shell. It does not need a Linear plugin or extra packages.

## Access

Create a personal API key in Linear: Settings → Account → Security & Access → Personal API keys.

The key needs **Read** and **Write**. Write alone cannot load the issue. Limit it to the teams you archive.

```bash
export LINEAR_API_KEY=lin_api_...
export ARCHIVE_ISSUE=TEAM-123
```

Both are required. `ARCHIVE_ISSUE` is the identifier of the issue whose description holds the table and whose documents hold each archive. The script has no built-in catalog issue.

## Commands

From the skill directory:

```bash
python3 scripts/archive_issue.py DEV-62
python3 scripts/archive_issue.py DEV-62 --trash
```

The first command writes the document and the table row. The second sends the issue to the Linear trash. Trash keeps it for 30 days. Pass `--include-open-children` only when the parent still has open sub-issues and a person has agreed to trash the parent anyway.
