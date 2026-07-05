# AGENTS.md

## Project Overview

This is a personal website and blog for Kun (Ryan) Ni, built with Hugo and the PaperMod theme. It's hosted on GitHub Pages at https://ekunnii.github.io.

## Tech Stack

- **Static Site Generator:** Hugo v0.163.3
- **Theme:** PaperMod (git submodule at `themes/PaperMod`)
- **Hosting:** GitHub Pages via GitHub Actions
- **Deployment:** `.github/workflows/hugo.yml`

## Site Structure

```
content/
├── cv/index.md          # CV page (uses custom layout + JSON data files)
├── blog/_index.md       # Blog section index
├── blog/*.md            # Blog posts
└── search.md            # Search page

data/
├── experience.json      # Work experience entries
├── education.json       # Education entries
└── skills.json          # Skills grouped by category

layouts/cv/single.html   # Custom CV layout template
assets/css/extended/     # Custom CSS (cv.css, print.css)
static/llms.txt          # LLM-friendly site summary
static/cvs/             # Downloadable CV files
```

## Key Conventions

- Blog posts go in `content/blog/` with front matter: title, date, tags, description
- CV data is driven by JSON files in `data/` — edit those to update the CV
- Custom CSS goes in `assets/css/extended/` (PaperMod auto-loads all files there)
- Site config is in `hugo.toml`
- The CV page has a "Copy as Markdown" button for LLM consumption

## Build & Preview

```bash
# Local preview with drafts
hugo server -D

# Production build
hugo --gc --minify
```

## Deployment

Push to `main` branch triggers GitHub Actions workflow that builds and deploys to GitHub Pages.

## Content Guidelines

- Do not include Ericsson internal project names or implementation details
- Keep CV descriptions generic — focus on technologies used and outcomes achieved
- Blog posts can discuss general concepts, research, and public knowledge
