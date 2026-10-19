#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date

API = "https://api.linear.app/graphql"
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9]+-\d+")
OPEN_STATES = {"completed", "canceled"}


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def dig(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def graphql(key, query, variables=None):
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    request = urllib.request.Request(
        API,
        data=payload,
        headers={"Authorization": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            fail(f"Linear returned a non-JSON response (HTTP {error.code})")
        messages = body.get("errors") or []
        if messages:
            fail("; ".join(error["message"] for error in messages))
        fail(f"Linear returned HTTP {error.code}")
    except json.JSONDecodeError:
        fail("Linear returned a non-JSON response")

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        fail("Linear returned a non-JSON response")
    if body.get("errors"):
        fail("; ".join(error["message"] for error in body["errors"]))
    return body["data"]


def collect(key, issue_id, field, selection):
    nodes = []
    after = None
    query = f"""
      query($id: String!, $after: String) {{
        issue(id: $id) {{
          {field}(first: 50, after: $after) {{
            nodes {{ {selection} }}
            pageInfo {{ hasNextPage endCursor }}
          }}
        }}
      }}
    """
    while True:
        data = graphql(key, query, {"id": issue_id, "after": after})
        issue = data.get("issue")
        if issue is None:
            fail(f"issue not found: {issue_id}")
        page = issue[field]
        nodes.extend(page["nodes"])
        if not dig(page, "pageInfo", "hasNextPage"):
            return nodes
        after = dig(page, "pageInfo", "endCursor")


def load_issue(key, identifier):
    data = graphql(
        key,
        """
        query($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            description
            url
            priorityLabel
            createdAt
            completedAt
            canceledAt
            branchName
            assignee { name }
            creator { name }
            state { name type }
            team { name }
            project { name }
          }
        }
        """,
        {"id": identifier},
    )
    issue = data.get("issue")
    if issue is None:
        fail(f"issue not found: {identifier}")
    return issue


def mentions(text, identifier):
    return re.search(re.escape(identifier) + r"(?!\d)", text or "") is not None


def archive_url(text, identifier):
    escaped = re.escape(identifier)
    wrapped = re.search(r"\[" + escaped + r"\]\(<([^>]+)>\)", text or "")
    if wrapped:
        return wrapped.group(1)
    plain = re.search(r"\[" + escaped + r"\]\(([^)]+)\)", text or "")
    return plain.group(1) if plain else None


def blank(value):
    text = "" if value is None else str(value).strip()
    return text or "—"


def cell(value):
    return re.sub(r"[\r\n]+", " ", blank(value)).replace("|", "·")


def names(nodes):
    found = [node["name"] for node in nodes if node.get("name")]
    return ", ".join(found) if found else "—"


def identifiers(nodes, key):
    found = [dig(node, key, "identifier") for node in nodes]
    found = [item for item in found if item]
    return ", ".join(found) if found else "—"


def open_children(children):
    return [child for child in children if dig(child, "state", "type") not in OPEN_STATES]


def format_children(children):
    if not children:
        return "none"
    return "; ".join(
        f"{child['identifier']} {child['title']} ({dig(child, 'state', 'name')})"
        for child in children
    )


def document_body(issue, comments, attachments, children, blocks, blocked_by, related, duplicate):
    closed = issue.get("completedAt") or issue.get("canceledAt")
    links = [f"- [{item['title']}]({item['url']})" for item in attachments]
    if children:
        child_line = "; ".join(
            f"{child['identifier']} — {child['title']} — {dig(child, 'state', 'name')}"
            for child in children
        )
    else:
        child_line = "—"
    blocks_text = []
    for comment in sorted(comments, key=lambda item: item.get("createdAt") or ""):
        parts = [f"### {comment.get('createdAt')} — {blank(dig(comment, 'user', 'name'))}"]
        quote = (comment.get("quotedText") or "").strip()
        if quote:
            parts.append("> " + quote.replace("\n", "\n> "))
        parts.append(comment.get("body") or "")
        blocks_text.append("\n\n".join(parts))
    comment_text = "\n\n".join(blocks_text)
    return f"""# {issue['identifier']} — {issue['title']}

- Идентификатор: {issue['identifier']}
- Ссылка на задачу: {issue['url']}
- Статус: {blank(dig(issue, 'state', 'name'))}
- Приоритет: {blank(issue.get('priorityLabel'))}
- Исполнитель: {blank(dig(issue, 'assignee', 'name'))}
- Автор: {blank(dig(issue, 'creator', 'name'))}
- Теги: {names(issue['labels'])}
- Команда: {blank(dig(issue, 'team', 'name'))}
- Проект: {blank(dig(issue, 'project', 'name'))}
- Создана: {blank(issue.get('createdAt'))}
- Закрыта: {blank(closed)}
- Ветка: {blank(issue.get('branchName'))}

## Описание

{blank(issue.get('description'))}

## Ссылки

{chr(10).join(links) if links else "—"}

## Связи

- Блокирует: {identifiers(blocks, "relatedIssue")}
- Заблокирована: {identifiers(blocked_by, "issue")}
- Связанные: {related}
- Дубликат: {identifiers(duplicate, "relatedIssue")}
- Подзадачи: {child_line}

## Комментарии

{comment_text or "—"}
"""


def catalog_row(issue, document_url):
    labels = names(issue["labels"])
    cells = [
        date.today().isoformat(),
        issue["identifier"],
        cell(issue.get("title")),
        cell(dig(issue, "assignee", "name")),
        "—" if labels == "—" else cell(labels),
        cell(dig(issue, "state", "name")),
        cell(issue.get("priorityLabel")),
        f"[{issue['identifier']}]({document_url})",
    ]
    return "| " + " | ".join(cells) + " |"


def catalog_issue():
    raw = os.environ.get("ARCHIVE_ISSUE", "").strip()
    if not raw:
        fail("ARCHIVE_ISSUE is not set")
    found = IDENTIFIER.search(raw)
    if not found:
        fail("ARCHIVE_ISSUE must be an issue identifier")
    return found.group(0).upper()


def main():
    key = os.environ.get("LINEAR_API_KEY", "")
    if not key:
        fail("LINEAR_API_KEY is not set")
    catalog_id = catalog_issue()

    args = sys.argv[1:]
    trash = "--trash" in args
    allow_open = "--include-open-children" in args
    args = [arg for arg in args if arg not in {"--trash", "--include-open-children"}]
    if len(args) != 1:
        fail("usage: archive_issue.py IDENTIFIER_OR_URL [--trash] [--include-open-children]")

    found = IDENTIFIER.search(args[0])
    if not found:
        fail(f"no issue identifier in {args[0]}")
    identifier = found.group(0).upper()
    if identifier == catalog_id:
        fail(f"refusing to archive the catalog issue {catalog_id}")

    issue = load_issue(key, identifier)
    issue["labels"] = collect(key, issue["id"], "labels", "name")
    children = collect(key, issue["id"], "children", "identifier title state { name type }")
    opened = open_children(children)
    catalog = load_issue(key, catalog_id)

    if trash:
        if not mentions(catalog.get("description"), identifier):
            fail(f"no catalog row for {identifier}; archive it first")
        if opened and not allow_open:
            fail(
                f"open sub-issues: {format_children(opened)}; "
                "pass --include-open-children to trash the parent"
            )
        result = graphql(
            key,
            "mutation($id: String!) { issueDelete(id: $id) { success } }",
            {"id": issue["id"]},
        )
        if dig(result, "issueDelete", "success") is not True:
            fail("issueDelete did not succeed")
        print("status: trashed")
        print(f"identifier: {identifier}")
        print(f"uuid: {issue['id']}")
        return

    if mentions(catalog.get("description"), identifier):
        print("status: already_archived")
        print(f"identifier: {identifier}")
        print(f"document: {archive_url(catalog.get('description'), identifier) or '—'}")
        print(f"catalog: {catalog['url']}")
        return

    comments = collect(key, issue["id"], "comments", "body createdAt quotedText user { name }")
    attachments = collect(key, issue["id"], "attachments", "title url")
    relations = collect(key, issue["id"], "relations", "type relatedIssue { identifier }")
    inverse = collect(key, issue["id"], "inverseRelations", "type issue { identifier }")
    blocks = [relation for relation in relations if relation.get("type") == "blocks"]
    blocked_by = [relation for relation in inverse if relation.get("type") == "blocks"]
    related_ids = [
        dig(relation, "relatedIssue", "identifier")
        for relation in relations
        if relation.get("type") == "related"
    ] + [
        dig(relation, "issue", "identifier")
        for relation in inverse
        if relation.get("type") == "related"
    ]
    related_ids = [item for item in related_ids if item]
    duplicate = [relation for relation in relations if relation.get("type") == "duplicate"]
    related = ", ".join(related_ids) if related_ids else "—"

    prefix = f"{identifier} — "
    title = issue.get("title") or ""
    if len(prefix) + len(title) > 200:
        title = title[: 200 - len(prefix)].rstrip()
    created = graphql(
        key,
        """
        mutation($input: DocumentCreateInput!) {
          documentCreate(input: $input) {
            success
            document { url }
          }
        }
        """,
        {
            "input": {
                "title": f"{prefix}{title}",
                "content": document_body(
                    issue, comments, attachments, children, blocks, blocked_by, related, duplicate
                ),
                "issueId": catalog["id"],
            }
        },
    )
    if dig(created, "documentCreate", "success") is not True:
        fail("documentCreate did not succeed")
    document_url = dig(created, "documentCreate", "document", "url")
    if not document_url:
        fail("documentCreate returned no url")

    row = catalog_row(issue, document_url)
    current = catalog.get("description") or ""
    if "| Дата | Задача |" in current:
        description = f"{current}{row}\n" if current.endswith("\n") else f"{current}\n{row}\n"
    else:
        description = (
            "| Дата | Задача | Название | Исполнитель | Теги | Статус | Приоритет | Архив |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"{row}\n"
        )

    updated = graphql(
        key,
        """
        mutation($id: String!, $description: String!) {
          issueUpdate(id: $id, input: { description: $description }) {
            success
            issue { description url }
          }
        }
        """,
        {"id": catalog["id"], "description": description},
    )
    if dig(updated, "issueUpdate", "success") is not True:
        fail("issueUpdate did not succeed")
    saved = dig(updated, "issueUpdate", "issue", "description") or ""
    if not mentions(saved, identifier) or document_url not in saved:
        fail(f"catalog row was not saved; {identifier} was not trashed")

    print("status: archived")
    print(f"identifier: {identifier}")
    print(f"document: {document_url}")
    print(f"catalog: {dig(updated, 'issueUpdate', 'issue', 'url')}")
    print(f"uuid: {issue['id']}")
    print(f"open_sub_issues: {format_children(opened)}")


if __name__ == "__main__":
    main()
