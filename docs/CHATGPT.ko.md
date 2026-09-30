# ChatGPT에서 쓰기

| 요금제 | 방법 |
|---|---|
| Free · Plus (+ 모든 요금제) | **ChatGPT 데스크톱 앱의 Codex + 스킬** — 서버 필요 없음, 내 PC에서 실행 (바로 아래) |
| Pro · Business · Enterprise | 위 방법, 또는 웹 채팅용 **MCP 서버 + 플러그인** (아래 0~2단계) |

## Plus·무료 요금제: ChatGPT 데스크톱 앱(Codex)

ChatGPT 데스크톱 앱(Windows/Mac)에는 모든 요금제에 Codex가 들어 있고, Codex는 내 PC에서 스킬의 스크립트를
실행할 수 있습니다. 한 번만 설치하면 이후로는 주소만 주면 됩니다.

1. **필요한 프로그램 설치** (PowerShell, 이미 있으면 건너뛰기)
   ```powershell
   winget install -e --id Python.Python.3.12
   winget install -e --id Git.Git
   ```
   설치 후 PowerShell을 새로 열고 한 번 실행:
   ```powershell
   git lfs install
   git config --global core.longpaths true
   python --version   # 3.10 이상이면 OK. 안 되면 py -3 --version 이 되는지 확인(스킬이 py도 씁니다)
   ```
2. **스킬 설치** — 스킬 폴더에 이 저장소를 그대로 클론합니다.
   ```powershell
   git clone https://github.com/immigration2000/ue-repo-reader "$env:USERPROFILE\.agents\skills\ue-repo-reader"
   ```
   업데이트: `git -C "$env:USERPROFILE\.agents\skills\ue-repo-reader" pull`
3. **ChatGPT 데스크톱 앱 → Codex**에서 작업 폴더를 하나 엽니다(예: 빈 폴더 `C:\UEReview`, 요약본이 여기에 생깁니다).
   스킬이 안 보이면 앱을 다시 시작하세요(사이드바 **Skills**에서 확인).
4. 이렇게 말합니다:
   > https://github.com/immigration2000/ExtractionGame_Fin 분석해줘

   (확실히 부르려면 `$ue-repo-reader https://github.com/...`)
   명령 실행이나 네트워크(깃 클론) 허용을 물으면 허용하세요.

## Pro 이상: 웹 채팅용 MCP 서버 + 플러그인

웹 ChatGPT는 스킬 안의 스크립트를 실행하지 못합니다(git 클론, 파이썬 불가). 그래서 분석 도구를 **MCP 서버**로
인터넷에 띄우고, ChatGPT가 그 서버의 도구를 호출하는 구조입니다.

```
ChatGPT 채팅 ──(MCP 도구 호출)──▶ ue-repo-reader 서버 ──(git clone)──▶ GitHub 저장소
                                  └ 요약본 생성 · 파일 읽기 · 검색
```

서버가 제공하는 도구(모두 읽기 전용):

| 도구 | 하는 일 |
|---|---|
| `analyze_repo` | 저장소 URL을 받아 분석하고 INDEX.md 반환(같은 커밋은 캐시) |
| `wait_for_analysis` | 큰 프로젝트 분석이 끝날 때까지 대기 |
| `list_digest_files` / `read_digest_file` | 블루프린트·맵·데이터 파일 목록과 내용(긴 파일은 페이지로) |
| `search_digest` | 요약본 전체 검색(선택: C++·설정 파일까지) |
| `read_source_file` | 저장소의 C++ / Build.cs / ini 등 텍스트 파일 읽기 |

## 0단계: 요금제 확인 (중요)

OpenAI 도움말 기준으로 커스텀 MCP(Developer mode)는 요금제마다 다릅니다.

| 요금제 | 사용 가능 여부 |
|---|---|
| Free / Plus | **지원 안 됨** |
| Pro | 가능 (읽기 도구만 — 이 서버는 전부 읽기 전용이라 문제없음) |
| Business | 관리자·소유자만 |
| Enterprise / Edu | 관리자 + 권한 받은 멤버 |

Plus라면 ChatGPT 웹 채팅에서는 쓸 수 없습니다. 대신 Claude(추가 설정 없이 스킬로 동작, 또는 아래
"Claude에서도 같은 서버 쓰기")나 Codex(저장소 루트의 `SKILL.md`를 스킬로 사용)를 쓰세요.

## 1단계: 서버 띄우기

### A. Hugging Face Spaces (추천: 무료, PC를 꺼도 동작)

1. https://huggingface.co/new-space 에서 Space 생성
   - SDK: **Docker** → **Blank**, 공개 범위: **Public**
   - (Private Space는 ChatGPT가 접근할 수 없습니다. 대신 아래의 비밀 경로로 보호합니다.)
2. Space의 **Files** 탭에서 이 저장소의 `deploy/huggingface/Dockerfile`과 `deploy/huggingface/README.md`
   두 파일을 올립니다(README.md는 기존 파일을 덮어쓰기).
3. **Settings → Variables and secrets**에서 *Secret*으로 추가:
   - `UE_READER_SECRET`: 길고 무작위인 문자열. 영문·숫자만 쓰세요(`/ ? #` 금지).
     Windows PowerShell에서 `[guid]::NewGuid().ToString("N")` 실행 → 32자 문자열이 나옵니다.
   - `GITHUB_TOKEN`: 비공개 저장소를 읽을 때만. GitHub → Settings → Developer settings →
     Fine-grained tokens → 대상 저장소 선택, **Contents: Read-only**
   - (선택) `UE_READER_ALLOWED_OWNERS`: `immigration2000` — 내 저장소만 분석하도록 제한
4. 빌드가 끝나면(상단 상태가 **Running**) Space 주소가 `https://<계정>-<space이름>.hf.space`입니다
   (Space 화면 오른쪽 위 **⋮ → Embed this Space → Direct URL**에서 정확한 주소 확인). 브라우저로 열어
   `ue-repo-reader MCP server is running.`이 보이면 정상입니다.
5. MCP 주소: `https://<계정>-<space이름>.hf.space/<UE_READER_SECRET>/mcp`

무료 Space는 48시간 동안 쓰지 않으면 잠듭니다. 잠든 Space는 페이지를 한 번 열면 깨어나고, 1~2분 걸릴 수 있습니다.
분석 캐시는 재시작하면 지워지므로 첫 분석은 다시 1분 안팎 걸립니다.
코드를 업데이트하려면 Space Settings의 **Factory rebuild**를 누르면 GitHub 최신 코드로 다시 빌드됩니다.

다른 호스팅(Render, Railway, Fly.io, Cloud Run 등)도 저장소 루트의 `Dockerfile`로 그대로 배포됩니다.
메모리가 작은 무료 인스턴스라면 `UE_READER_WORKERS=1`로 설정하세요.

### B. 내 PC에서 실행 + 터널 (PC가 켜져 있을 때만)

1. 이 저장소를 클론하고 `server\run_local.bat` 실행 → 콘솔에 비밀 경로가 포함된 주소가 나옵니다.
2. 다른 창에서 터널을 엽니다. 예: `cloudflared tunnel --url http://localhost:8000`
   (주소가 실행할 때마다 바뀌므로, 고정 주소가 필요하면 Cloudflare 이름 있는 터널이나 ngrok 고정 도메인을 쓰세요.
   OpenAI의 Secure MCP Tunnel도 방법입니다.)
3. MCP 주소: `https://<터널주소>/<비밀경로>/mcp`

## 2단계: ChatGPT에 연결

OpenAI 문서 기준 절차입니다(메뉴 이름은 바뀔 수 있습니다).

1. ChatGPT → **Settings → Security and login → Developer mode** 켜기
   (Business/Enterprise는 **Settings → Apps → Advanced settings**에 있을 수 있습니다.)
2. **Plugins**(화면에 따라 **Apps**) → **+ / Create**
   - 이름: `UE Repo Reader`, 설명: `언리얼 저장소 분석(블루프린트 포함)`
   - Connection(연결): MCP 서버 URL에 위의 MCP 주소(끝이 `/mcp`) 입력
   - 인증(Authentication): **없음(No authentication)**
   - 위험 안내 체크박스가 나오면 확인 후 체크 → **Scan Tools**가 있으면 눌러 도구 6개가 보이는지 확인 → **Create**
3. 새 채팅을 열고 입력창의 **+ / 도구 메뉴**에서 UE Repo Reader를 켠 뒤(또는 `@UE Repo Reader`):
   > https://github.com/immigration2000/ExtractionGame_Fin 분석해줘

서버 코드를 업데이트한 뒤 도구 목록이 바뀌었다면 Plugins에서 해당 연결을 열고 **Refresh**를 누르세요.

### 스킬까지 포함한 플러그인 패키지 (선택)

`chatgpt-plugin/` 폴더가 플러그인 패키지입니다(`plugin.json` + `skills/ue-repo-reader/SKILL.md` + `mcp.json`).
MCP 서버만 연결해도 동작하지만(서버가 사용법 지침을 함께 보냄), 스킬을 넣으면 읽는 순서와 리뷰 체크리스트를
더 잘 따릅니다.

1. `chatgpt-plugin/mcp.json`의 `url`을 내 MCP 주소로 바꿉니다.
2. ChatGPT 데스크톱 앱: `~/.agents/plugins/marketplace.json`(Windows는 `%USERPROFILE%\.agents\plugins\`)에
   아래처럼 등록하고 앱을 다시 시작하면 Plugins Directory에 나타납니다.

```json
{
  "name": "personal",
  "interface": { "displayName": "Personal Plugins" },
  "plugins": [
    {
      "name": "ue-repo-reader",
      "source": { "source": "local", "path": "C:/Users/<me>/ue-repo-reader/chatgpt-plugin" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Developer Tools"
    }
  ]
}
```

## Claude에서도 같은 서버 쓰기

같은 MCP 주소를 Claude의 **설정 → 커넥터 → 커스텀 커넥터 추가**에 넣으면 Claude 채팅에서도 똑같이 동작합니다.

## 보안 메모

- 서버 주소를 아는 사람은 누구나 도구를 호출할 수 있으므로 **비밀 경로(`UE_READER_SECRET`)를 꼭 설정**하세요.
- `GITHUB_TOKEN`은 필요한 저장소만, 읽기 전용으로 발급하세요. 토큰은 출력과 로그에서 가려집니다.
- 서버는 github.com / gitlab.com / bitbucket.org의 https 주소만 받고, 저장소 밖의 파일이나 `.git` 내부는 읽지 않습니다.
