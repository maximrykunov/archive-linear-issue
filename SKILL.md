---
name: archive-linear-issue
description: >-
  Archives a Linear issue onto the catalog issue named by ARCHIVE_ISSUE by running
  scripts/archive_issue.py, then trashes it only after an explicit yes. Use
  when the user asks to archive a Linear issue, says заархивируй, or pairs a
  linear.app issue URL with an archive request. Works in Cursor, Claude, and
  any agent that can run Python 3.
---

# Archive a Linear issue

Run `scripts/archive_issue.py` from this skill directory. Do not recreate the archive with a Linear plugin or by hand. The script is the whole workflow, so Cursor, Claude, and any other agent do the same thing. It uses the Python 3 standard library.

`LINEAR_API_KEY` and `ARCHIVE_ISSUE` must both be in the command's environment. `ARCHIVE_ISSUE` is the identifier of the catalog issue, such as `TEAM-123`. Never archive that issue. The key must allow Read and Write. Do not print the key, `ARCHIVE_ISSUE`, or the file that stores them. If the script says either variable is not set, rerun it in a login shell (`zsh -lic 'python3 …'`) so the user's shell profile loads. Do not print that profile.

## Archive

```bash
python3 "$SKILL_DIR/scripts/archive_issue.py" DEV-62
```

`SKILL_DIR` is the directory of this `SKILL.md`. An issue URL is accepted in place of `DEV-62`.

Read the `status:` line.

- `archived` — the document and the catalog row exist. Show `document` and `catalog` to the user. If `open_sub_issues` is not `none`, list them too. Then ask, in Russian, with the real identifier: `Удалить DEV-62 в корзину Linear? Ответьте «да».` Do not run `--trash` in this turn.
- `already_archived` — stop. Show the existing document link. Do not trash unless the user, in a later message, asks to delete that issue.
- Any failure — stop. The issue stays in Linear. Quote the script's error.

## Trash

Only after a later message that agrees:

```bash
python3 "$SKILL_DIR/scripts/archive_issue.py" DEV-62 --trash
```

If the archive output listed open sub-issues, add `--include-open-children` only when the user agreed to trash the parent anyway. Success is `status: trashed`. Then say the issue is in the team trash for 30 days.

A refusal or any other answer leaves the issue in place. The document and the row stay.
