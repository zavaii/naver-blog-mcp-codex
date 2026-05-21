# AGENTS.md

이 저장소는 Codex에서 사용하는 네이버 블로그 MCP 서버입니다. 사용자와의 대화는 기본적으로 한국어로 답합니다.

## 프로젝트 개요

Playwright 기반 네이버 블로그 자동화 MCP 서버입니다. 네이버 블로그 공식 API가 종료되어 웹 브라우저 자동화로 글 작성과 카테고리 조회를 제공합니다.

## 개발 환경

```bash
uv sync
uv run playwright install chromium
uv run naver-blog-mcp
```

## Codex MCP 설정

Codex 설정 예시는 `codex_mcp_config.example.toml`과 `docs/codex-guide.md`를 기준으로 유지합니다. 이 서버는 Codex가 세션 시작 시 도구 목록을 안정적으로 조회할 수 있도록, 브라우저와 네이버 로그인 초기화를 첫 도구 호출 시점까지 지연합니다.

## 주요 경로

- `src/naver_blog_mcp/server.py`: MCP 서버 진입점
- `src/naver_blog_mcp/mcp/tools.py`: MCP Tool 정의 및 핸들러
- `src/naver_blog_mcp/automation/`: Playwright 자동화
- `src/naver_blog_mcp/services/session_manager.py`: 네이버 세션 저장/복원
- `docs/codex-guide.md`: Codex 연동 가이드

## 환경 변수

```env
NAVER_BLOG_ID=
NAVER_BLOG_PASSWORD=
HEADLESS=false
SLOW_MO=100
LOG_LEVEL=INFO
IMAGE_UPLOAD_ALLOWED_DIRS=blog-images
SAVE_DEBUG_ARTIFACTS=false
```

## 검증

작은 변경은 가능한 한 다음 순서로 확인합니다.

```bash
uv run python -m compileall -q src tests test_mcp_tools.py main.py
uv run python test_mcp_tools.py
```

실제 로그인, 글 작성, 카테고리 조회 검증은 네이버 계정과 Playwright 브라우저 세션이 필요합니다.
