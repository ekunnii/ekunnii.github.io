#!/usr/bin/env python3
"""Regenerate static/cv.md from data/ JSON files and content/cv/index.md front matter."""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CV_FRONT_MATTER = os.path.join(ROOT, "content", "cv", "index.md")
OUTPUT = os.path.join(ROOT, "static", "cv.md")


def load_json(name):
    with open(os.path.join(DATA_DIR, name), "r") as f:
        return json.load(f)


def parse_front_matter(path):
    """Extract YAML front matter values we need."""
    params = {}
    with open(path, "r") as f:
        content = f.read()

    # Simple front matter parser
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            # Extract summary
            for line in fm.split("\n"):
                if line.startswith("summary:"):
                    params["summary"] = line.split("summary:", 1)[1].strip().strip('"')

            # Extract publications
            pubs = []
            in_pubs = False
            current_pub = {}
            for line in fm.split("\n"):
                if line.strip() == "publications:":
                    in_pubs = True
                    continue
                if in_pubs:
                    if line.strip().startswith("- title:"):
                        if current_pub:
                            pubs.append(current_pub)
                        current_pub = {"title": line.split("title:", 1)[1].strip().strip('"')}
                    elif line.strip().startswith("venue:"):
                        current_pub["venue"] = line.split("venue:", 1)[1].strip().strip('"')
                    elif line.strip().startswith("link:"):
                        current_pub["link"] = line.split("link:", 1)[1].strip().strip('"')
                    elif line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                        in_pubs = False
            if current_pub:
                pubs.append(current_pub)
            params["publications"] = pubs

    return params


def generate_cv_md():
    skills = load_json("skills.json")
    experience = load_json("experience.json")
    education = load_json("education.json")
    params = parse_front_matter(CV_FRONT_MATTER)

    lines = []
    lines.append("# Curriculum Vitae")
    lines.append("**Kun (Ryan) Ni — AI Architect**")
    lines.append("")

    # Summary
    if params.get("summary"):
        lines.append("## Summary")
        lines.append("")
        lines.append(params["summary"])
        lines.append("")

    # Skills
    lines.append("## Skills")
    lines.append("")
    for group in skills:
        lines.append(f"**{group['grouping']}:** {', '.join(group['skills'])}")
        lines.append("")

    # Experience
    lines.append("## Professional Experience")
    lines.append("")
    for exp in experience:
        lines.append(f"### {exp['role']} — {exp['company']}")
        lines.append(f"*{exp['range']}*")
        lines.append("")
        lines.append(exp["summary"])
        lines.append("")

    # Education
    lines.append("## Education")
    lines.append("")
    for edu in education:
        lines.append(f"### {edu['degree']} in {edu['major']}")
        lines.append(f"*{edu['school']} ({edu['range']})*")
        lines.append("")

    # Publications
    if params.get("publications"):
        lines.append("## Publications")
        lines.append("")
        for pub in params["publications"]:
            lines.append(f"- [{pub['title']}]({pub.get('link', '')}) — {pub['venue']}")
        lines.append("")

    md = "\n".join(lines)

    with open(OUTPUT, "w") as f:
        f.write(md)

    print(f"Generated {OUTPUT} ({len(md)} bytes)")


if __name__ == "__main__":
    generate_cv_md()
