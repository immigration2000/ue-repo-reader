# ChatGPT에서 쓰기

**내 PC에서 스킬을 실행하면 서버가 필요 없습니다.** MCP 서버는 웹 채팅 등에서 원격 도구를 호출하려는 경우에만
선택합니다. 로컬 설치·분석과 서버 배포는 별개의 방법입니다.

| 실행 환경 | 방법 |
|---|---|
| ChatGPT 데스크톱 앱의 로컬 작업 / Codex CLI | 스킬 설치 → 내 PC의 Python으로 분석 |
| ChatGPT 웹의 커스텀 MCP 연결 | 선택 사항: MCP 서버 실행 → Plugins에 연결 → 채팅에서 호출 |

계정·워크스페이스마다 표시되는 기능과 권한이 다를 수 있습니다. 요금제별 가능 여부를 단정하지 말고 현재 메뉴와
관리자 정책을 확인하세요. [스킬 지원 환경](https://learn.chatgpt.com/docs/build-skills),
[커스텀 MCP 접근 조건](https://developers.openai.com/api/docs/guides/custom-mcp-server).
아래 외부 서비스 안내는 **2026-10-27 확인 기준**입니다.

## 1. 로컬 스킬로 분석하기 (서버 불필요)

Windows 설치·Python 선택·Git LFS 설정·성공 판정은 검증한 [Codex 설치 가이드](CODEX_SETUP.ko.md)를 따르세요.
저장소 전체를 `~/.agents/skills/ue-repo-reader/`에 설치합니다. 필요한 것은 Python 3.10+, Git, Git LFS입니다.
별도 MCP 호스팅이나 Hugging Face 계정은 필요 없습니다.

앱에서 로컬 작업 폴더를 열고 다음처럼 요청합니다.

> ue-repo-reader 스킬로 https://github.com/immigration2000/ExtractionGame_Fin 분석해줘

Codex CLI에서는 `$ue-repo-reader`로 명시할 수도 있습니다. 직접 실행할 때는:

```bash
python scripts/ue_repo_digest.py https://github.com/owner/Project --out Project_digest
```

처음 실행 시 고정 버전 파서를 내려받습니다. 완료 후 `INDEX.md`의 읽기 순위·커버리지와 `CATALOG.md`의 전체 Parse report를 확인하세요.

프로젝트 대상은 UE 5.7+이며 현재 기본 범위는 숫자 5.7/5.8 선언입니다. 버전 미확정·구버전·미검증 신버전을 명시적으로
탐색할 때만 CLI의 `--best-effort` 또는 MCP `analyze_repo`의 `best_effort=true`를 사용합니다. **Project support**의 범위 밖/
미확정 상태는 계속 보고하며, 오래된 저장 에셋이 섞였다는 이유로 현대 프로젝트를 제외하지 않습니다.

## 2. 원격 MCP 도구 사용하기 (선택 사항)

서버가 git clone과 Python 분석을 수행하고, ChatGPT가 결과를 읽습니다. 대상 저장소를 수정하지 않는 도구 6개를 제공합니다.

| 도구 | 하는 일 |
|---|---|
| `analyze_repo` | URL 분석, INDEX.md 반환; 같은 버전·커밋·프로젝트·분석 모드의 완료 결과 재사용 |
| `wait_for_analysis` | 실행 중인 분석 상태 확인 |
| `list_digest_files` / `read_digest_file` | 요약본 목록·내용 읽기; 긴 파일은 페이지로 반환 |
| `search_digest` | 요약본 검색; 선택적으로 C++·설정 파일 포함 |
| `read_source_file` | C++ / Build.cs / ini 등 원본 텍스트 읽기 |

### 서버 실행 방법 A: 내 PC + HTTPS 터널

1. 이 저장소에서 `server\run_local.bat`를 실행합니다. 서버용 Python과 `mcp` 의존성을 사용하며,
   콘솔에 비밀 경로가 포함된 주소가 표시됩니다.
   배치 파일의 `python`은 실제 Python 3.10+여야 합니다. WindowsApps 스텁이면 먼저 위 설치 가이드로 Python 경로를 정리하세요.
2. 외부 호출용 HTTPS 터널을 연결합니다. 예: `cloudflared tunnel --url http://localhost:8000`.
   터널 도구는 별도 설치가 필요하며 임시 호스트가 바뀌면 MCP 주소도 갱신합니다.
3. MCP 주소는 `https://<터널호스트>/<비밀경로>/mcp`입니다. PC·서버·터널이 실행 중이어야 합니다.

[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)도 선택할 수 있습니다.
별도 설정과 워크스페이스 권한을 확인하세요.

### 서버 실행 방법 B: 컨테이너 호스팅

일반 호스트에는 루트 `Dockerfile`, Hugging Face에는 `deploy/huggingface/` 파일을 사용합니다.
메모리가 작으면 `UE_READER_WORKERS=1`로 설정하세요.

**Hugging Face Docker Space 신규 생성은 무료 계정의 CPU Basic에서 지원되지 않습니다.** CPU Basic 생성에는
개인 **PRO**, 조직 **Team/Enterprise** 구독이 필요합니다. 유료 하드웨어는 별도 결제 조건이 적용됩니다.
CPU Basic의 시간당 하드웨어 비용이 없다는 설명과 Space 생성 자격을 구분하세요.
[Spaces 생성 조건](https://huggingface.co/docs/hub/spaces-overview),
[CPU Basic·유료 하드웨어 조건](https://huggingface.co/docs/huggingface_hub/main/guides/manage-spaces).

1. [새 Space](https://huggingface.co/new-space)에서 Docker SDK를 선택합니다. 공개 범위는 직접 결정하세요.
   연결할 HTTPS 주소에 ChatGPT가 실제로 접근할 수 있어야 합니다.
2. `deploy/huggingface/Dockerfile`과 `deploy/huggingface/README.md`를 Space 루트의 같은 이름으로 올립니다.
3. Variables and secrets에 다음 값을 설정합니다.
   - Secret `UE_READER_SECRET`: 길고 무작위인 영문·숫자 문자열. 예: PowerShell `[guid]::NewGuid().ToString("N")`.
   - Secret `GITHUB_TOKEN`: 비공개 GitHub 저장소를 읽을 때만. 필요한 저장소에만 Contents: Read-only 권한을 부여합니다.
   - 선택 변수 `UE_READER_ALLOWED_OWNERS`: 허용할 소유자 목록(쉼표로 구분).
4. 빌드 후 Space의 정확한 Direct URL에서 `/`를 열어 `ue-repo-reader MCP server is running.`을 확인합니다.
5. MCP 주소는 `https://<Space호스트>/<UE_READER_SECRET>/mcp`입니다.

파일·포트 설정은 [HF Docker 안내](https://huggingface.co/docs/hub/spaces-sdks-docker)를 참고하세요.
휴면·저장소 유지 조건은 호스팅 설정에 따릅니다. 영구 저장소가 없으면 재시작 후 다시 분석해야 합니다.
HF Dockerfile은 빌드 시 GitHub main을 받으므로, 코드 갱신 시 캐시 없는 재빌드로 최신 코드를 가져오세요.

### ChatGPT에서 연결

개발자 모드의 커스텀 MCP 추가는 **Plugins**에서 진행합니다. 기존 Security and login 경로를 찾거나
GPT 만들기 / GPT Actions를 설정할 필요는 없습니다. 현재 공식 절차:

1. **Plugins → + → Add custom MCP server**를 엽니다.
2. 이름 `UE Repo Reader`, Server URL에 위 `/mcp` 주소를 입력합니다.
3. **No authentication**을 선택합니다. 이 서버는 비밀 경로가 접근 수단이므로 주소 전체를 공개하지 마세요.
4. 연결 위험 안내를 검토하고 **Create as a plugin**을 선택합니다.
5. 생성된 개인/워크스페이스 플러그인을 **설치**한 뒤 새 채팅에서 `@UE Repo Reader`를 선택하고 분석을 요청합니다.

추가 메뉴가 없으면 계정·워크스페이스의 플러그인 권한과 보안 정책을 확인하세요.
도구가 바뀌면 플러그인 상세 설정의 Refresh로 갱신합니다.
[OpenAI 연결 절차](https://developers.openai.com/api/docs/guides/custom-mcp-server),
[Plugins 빠른 시작](https://developers.openai.com/plugins/quickstart).

### 스킬 포함 패키지 (선택)

`chatgpt-plugin/`에는 플러그인 설명, 읽는 순서를 담은 스킬, MCP 설정 예제가 있습니다.
패키지를 사용하려면 `mcp.json`의 URL을 자신의 서버 주소로 바꾸고
[공식 패키지 안내](https://developers.openai.com/plugins/build/plugins)를 따르세요.
커스텀 MCP 직접 연결만으로도 서버 도구와 서버 지침을 사용할 수 있습니다.

## 서버 운영 메모

- 공개 호스트에는 `UE_READER_SECRET`을 설정하세요. 주소를 아는 사람은 누구나 서버를 호출할 수 있습니다.
- GitHub 토큰은 필요한 저장소에만 읽기 권한을 부여합니다. 서버 응답·로그에는 토큰을 가립니다.
- 서버는 github.com / gitlab.com / bitbucket.org의 HTTPS 저장소를 받으며 저장소 밖과 `.git` 내부 파일 읽기를 거부합니다.
- 같은 MCP 주소를 Streamable HTTP 지원 클라이언트에서도 사용할 수 있습니다.
- `UE_READER_TIMEOUT`은 분석 실행의 초 단위 제한입니다(기본 1800). 큐 대기는 제외하며 초과 시 자식 프로세스도 종료합니다.
- 캐시는 도구/캐시 버전·저장소·커밋·프로젝트·명시적 탐색 모드별로 구분합니다. 이전 캐시는 재사용하지 않으며 `refresh=true`로 재분석합니다.
- MCP의 `ref`에는 브랜치·태그 또는 전체 40자 커밋 SHA를 사용합니다. CLI의 짧은 SHA 지원은 그대로 유지됩니다.
- 도구는 기존 6개를 유지합니다. 모든 텍스트 응답은 최대 20,000자이며, 목록은 호출당 최대 200개입니다.
  파일 읽기는 문자 offset, 목록/원본 glob은 항목 offset을 사용합니다. 반환된 다음 offset으로 이어 읽으세요.
  목록 전체 탐색은 10,000개까지이며 초과 시 폴더/glob을 좁혀야 합니다. 큰 파일도 메모리에 전부 올리지 않고 읽습니다.
- 검색은 대소문자 구분 없는 리터럴 부분 문자열(1–256자)입니다. FTS/정규식 문법은 사용하지 않습니다.
  `max_results`는 1–100으로 제한하며, 잘린 응답은 검색어를 좁혀 다시 요청하세요.
- 완료된 digest 세대마다 `search.sqlite`를 한 번 생성해 재사용합니다. SQLite FTS5 trigram이 없는 환경은
  캐시된 텍스트에서 같은 의미로 검색합니다. 추가 패키지는 필요 없습니다.
  검색 인덱스는 파일당 2MB, 총 64MB·후보 10,000파일·20만 줄까지이며 생략/상한 도달을 응답에 표시합니다.
  생략된 파일도 읽기 도구로 페이지를 나눠 확인할 수 있습니다. 1~2자 검색은 캐시 내부에서 선형 검색합니다.
