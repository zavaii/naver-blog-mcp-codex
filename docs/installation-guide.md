# 설치 및 설정 가이드

이 문서는 Codex용 네이버 블로그 MCP 서버 설치 절차만 다룹니다. 더 쉬운 설명은 [`easy-start-guide.md`](easy-start-guide.md), Codex 설정 예시는 [`codex-guide.md`](codex-guide.md)를 참고하세요.

## 요구사항

- Python 3.13 이상
- `uv`
- Chromium을 실행할 수 있는 데스크톱 환경
- 네이버 블로그가 개설된 네이버 계정

## 설치

```bash
uv sync
uv run playwright install chromium
```

## 계정 정보

저장소 루트에 `.env` 파일을 만들고 값을 입력합니다. 네이버 비밀번호는 `~/.codex/config.toml` 같은 MCP 클라이언트 설정 파일에 넣지 않습니다.

```env
NAVER_BLOG_ID=
NAVER_BLOG_PASSWORD=
HEADLESS=false
SLOW_MO=100
LOG_LEVEL=INFO
IMAGE_UPLOAD_ALLOWED_DIRS=blog-images
SAVE_DEBUG_ARTIFACTS=false
```

macOS/Linux에서는 권한을 제한합니다.

```bash
chmod 600 .env
```

## Codex MCP 설정

`~/.codex/config.toml`에 다음 내용을 추가합니다. `cwd`는 본인 저장소의 절대 경로로 바꿉니다.

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

## 검증

```bash
uv run python test_mcp_tools.py
uv run python tests/test_integration.py
```

네이버 계정 정보가 없으면 실제 브라우저 로그인 검증은 건너뜁니다.

## 보안 기본값

- `publish=false`는 공개 발행 대신 임시저장을 시도합니다.
- 이미지 업로드는 기본적으로 `blog-images/` 안 파일만 허용합니다.
- Playwright trace와 전체 페이지 스크린샷은 `SAVE_DEBUG_ARTIFACTS=true`일 때만 저장합니다.
- `.env`, `playwright-state/`, `blog-images/`의 실제 파일은 Git에 올리지 않습니다.
