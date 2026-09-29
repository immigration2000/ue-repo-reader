# ChatGPT에서 쓰기 (플러그인 / MCP)

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

## 1단계: 서버 띄우기

### A. Hugging Face Spaces (추천: 무료, PC를 꺼도 동작)

1. https://huggingface.co/new-space 에서 Space 생성
   - SDK: **Docker** → **Blank**, 공개 범위: **Public**
   - (Private Space는 ChatGPT가 접근할 수 없습니다. 대신 아래의 비밀 경로로 보호합니다.)
2. Space의 **Files** 탭에서 이 저장소의 `deploy/huggingface/Dockerfile`과 `deploy/huggingface/README.md`
   두 파일을 올립니다(README.md는 기존 파일을 덮어쓰기).
3. **Settings → Variables and secrets**에서 *Secret*으로 추가:
   - `UE_READER_SECRET`: 길고 무작위인 문자열(예: 비밀번호 생성기로 32자)
   - `GITHUB_TOKEN`: 비공개 저장소를 읽을 때만. GitHub → Settings → Developer settings →
     Fine-grained tokens → 대상 저장소 선택, **Contents: Read-only**
   - (선택) `UE_READER_ALLOWED_OWNERS`: `immigration2000` — 내 저장소만 분석하도록 제한
4. 빌드가 끝나면 Space 주소가 `https://<계정>-<space이름>.hf.space`입니다. 브라우저로 열어
   `ue-repo-reader MCP server is running.`이 보이면 정상입니다.
5. MCP 주소: `https://<계정>-<space이름>.hf.space/<UE_READER_SECRET>/mcp`

무료 Space는 한동안 쓰지 않으면 잠들고, 다음 호출 때 깨어나느라 1~2분 걸릴 수 있습니다.
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
2. **Plugins**(또는 Apps)에서 새로 만들기 → MCP 서버 URL에 위의 MCP 주소 입력
   → 인증은 **없음(No authentication)** → 생성
3. 일반 채팅에서 바로 사용:
   > https://github.com/immigration2000/ExtractionGame_Fin 분석해줘

   도구가 안 불리면 메시지 앞에 플러그인을 선택(@UE Repo Reader)하세요.

요금제: OpenAI 문서마다 개인 플랜(Plus/Pro)의 커스텀 MCP 지원 범위가 다르게 적혀 있습니다(Pro는 "읽기 도구만"
이라는 설명도 있음). 이 서버의 도구는 전부 **읽기 전용**이라 그 제한 안에서도 동작합니다. 내 계정에서
Developer mode 메뉴가 보이는지 먼저 확인하세요.

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
