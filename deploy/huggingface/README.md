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

Hosting this server is optional: local skill analysis needs no Space or MCP server.
Creating a Docker Space on CPU Basic requires a personal PRO or organization Team/Enterprise subscription;
paid hardware has separate billing requirements. CPU Basic having no hourly charge does not mean free accounts
can create Docker Spaces. See [HF's creation requirements](https://huggingface.co/docs/huggingface_hub/main/guides/manage-spaces).
Choose visibility and access deliberately. Connection steps: [ChatGPT guide](https://github.com/immigration2000/ue-repo-reader/blob/main/docs/CHATGPT.ko.md).

Set these in **Settings → Variables and secrets** (as *secrets*):

- `UE_READER_SECRET` — a long random string; the MCP endpoint becomes `https://<space-host>/<secret>/mcp`
- `GITHUB_TOKEN` — optional, only for private repositories (fine-grained token, *Contents: Read-only*)
- `UE_READER_ALLOWED_OWNERS` — optional, e.g. `immigration2000` to refuse other owners' repos
