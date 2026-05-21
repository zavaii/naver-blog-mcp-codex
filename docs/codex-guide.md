# Codex MCP 설정 가이드

이 프로젝트는 Codex에서 사용할 수 있는 STDIO 기반 MCP 서버입니다. Codex는 세션 시작 시 MCP 서버를 실행하고 도구 목록을 읽으므로, 이 서버는 브라우저와 네이버 로그인 초기화를 실제 도구 호출 시점까지 미룹니다.

## 1. 의존성 설치

```bash
uv sync
uv run playwright install chromium
```

## 2. Codex 설정

네이버 계정 정보는 저장소 루트의 `.env` 파일에 저장합니다. 이 파일은 `.gitignore`에 포함되어 있습니다.

```env
NAVER_BLOG_ID=
NAVER_BLOG_PASSWORD=
HEADLESS=false
SLOW_MO=100
LOG_LEVEL=INFO
IMAGE_UPLOAD_ALLOWED_DIRS=blog-images
SAVE_DEBUG_ARTIFACTS=false
```

`~/.codex/config.toml`에 다음 설정을 추가합니다. `cwd`는 이 저장소의 절대 경로로 바꿔야 합니다.

```toml
[mcp_servers."naver-blog"]
command = "uv"
args = ["run", "naver-blog-mcp"]
cwd = "/absolute/path/to/naver-blog-mcp-codex"
startup_timeout_sec = 30
tool_timeout_sec = 300
default_tools_approval_mode = "prompt"
enabled_tools = ["naver_blog_create_post", "naver_blog_list_categories"]

[mcp_servers."naver-blog".env]
PYTHONIOENCODING = "utf-8"
HEADLESS = "false"
SLOW_MO = "100"
LOG_LEVEL = "INFO"
IMAGE_UPLOAD_ALLOWED_DIRS = "blog-images"
SAVE_DEBUG_ARTIFACTS = "false"
```

같은 내용의 복사용 예시는 `codex_mcp_config.example.toml`에도 있습니다.

## 3. Codex에서 확인

Codex를 재시작한 뒤 TUI에서 `/mcp`를 실행해 `naver-blog` 서버가 보이는지 확인합니다.

도구는 다음 두 개가 노출됩니다.

- `naver_blog_create_post`: 네이버 블로그 글 작성
- `naver_blog_list_categories`: 카테고리 목록 조회

## 4. 로그인 동작

Codex가 MCP 서버를 시작할 때는 네이버 로그인을 시도하지 않습니다. 첫 도구 호출 때 Playwright 브라우저가 열리고 로그인/세션 복원이 진행됩니다.

처음 로그인하거나 CAPTCHA가 발생할 수 있으면 `HEADLESS = "false"`로 두세요. 세션은 기본적으로 `playwright-state/auth.json`에 저장되며, 이후에는 `HEADLESS = "true"`로 바꿔도 됩니다.

이미지 업로드는 기본적으로 `blog-images` 폴더 안 파일만 허용합니다. 다른 폴더를 허용하려면 `IMAGE_UPLOAD_ALLOWED_DIRS`에 쉼표로 구분해 추가합니다.

## 5. CLI로 등록하는 경우

`codex mcp add`는 `cwd` 옵션이 없으므로, CLI만으로 등록하려면 셸에서 작업 디렉터리를 이동시켜 실행합니다.

```bash
codex mcp add naver-blog \
  --env PYTHONIOENCODING=utf-8 \
  --env HEADLESS=false \
  --env SLOW_MO=100 \
  -- bash -lc 'cd "/absolute/path/to/naver-blog-mcp-codex" && exec uv run naver-blog-mcp'
```

네이버 비밀번호를 셸 히스토리에 남기지 않도록 계정 정보는 `.env` 파일에 저장하는 방식을 권장합니다.
