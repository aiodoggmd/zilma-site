# -*- coding: utf-8 -*-
"""Convert a Telegraph article's content JSON (from getPage) into the Markdown
body used by src/content/articles/*.md. Reused per NEWS article migrated to the site.

Usage: python scripts/telegraph-to-md.py <telegraph-path> > body.md
"""
import sys
import requests


def text_of(node):
    if isinstance(node, str):
        return node
    tag = node.get("tag")
    children = "".join(text_of(c) for c in node.get("children", []))
    if tag == "strong":
        return f"**{children}**"
    if tag == "em":
        return f"*{children}*"
    if tag == "a":
        href = node.get("attrs", {}).get("href", "")
        return f"[{children}]({href})"
    return children


def node_to_md(node, lines):
    if isinstance(node, str):
        return
    tag = node.get("tag")
    children = node.get("children", [])
    if tag == "h3":
        lines.append(f"## {text_of({'children': children})}\n")
    elif tag == "h4":
        lines.append(f"### {text_of({'children': children})}\n")
    elif tag == "p":
        lines.append(text_of({"children": children}) + "\n")
    elif tag == "ul":
        for li in children:
            lines.append(f"- {text_of(li)}")
        lines.append("")
    elif tag == "figure":
        # cover/palette images are handled separately via frontmatter, skip in body
        pass
    else:
        for c in children:
            node_to_md(c, lines)


def main():
    path = sys.argv[1]
    r = requests.get("https://api.telegra.ph/getPage/" + path, params={"return_content": "true"})
    r.raise_for_status()
    content = r.json()["result"]["content"]
    lines = []
    for node in content:
        node_to_md(node, lines)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
