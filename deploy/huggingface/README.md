---
title: UE Repo Reader
emoji: 🎮
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

MCP server that reads Unreal Engine projects from a git URL — Blueprints, maps and data assets decoded from
binary `.uasset`/`.umap` files, no editor needed. Source: https://github.com/immigration2000/ue-repo-reader

Set these in **Settings → Variables and secrets** (as *secrets*):

- `UE_READER_SECRET` — a long random string; the MCP endpoint becomes `https://<space-host>/<secret>/mcp`
- `GITHUB_TOKEN` — optional, only for private repositories (fine-grained token, *Contents: Read-only*)
- `UE_READER_ALLOWED_OWNERS` — optional, e.g. `immigration2000` to refuse other owners' repos
