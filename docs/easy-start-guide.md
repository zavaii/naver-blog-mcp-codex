# 네이버 블로그 MCP 쉬운 사용 설명서

이 설명서는 Codex에서 네이버 블로그 글쓰기 도구를 쓰기 위한 안내서입니다. 개발자가 아니어도 따라 할 수 있게 순서대로 적었습니다.

## 이 도구로 할 수 있는 일

- Codex에게 네이버 블로그 글 작성을 부탁할 수 있습니다.
- 내 블로그 카테고리 목록을 불러올 수 있습니다.
- 이미지 파일 경로를 알려주면 글에 이미지를 넣을 수 있습니다.

## 준비물

1. 네이버 아이디와 비밀번호
2. Codex가 설치된 컴퓨터
3. 이 프로젝트 폴더
4. `uv`라는 Python 실행 도구

현재 이 프로젝트 폴더 위치는 아래와 같습니다.

```text
/Users/name/Desktop/네이버 블로그 mcp/naver-blog-mcp-codex
```

## 1단계: 터미널 열기

macOS에서는 Spotlight 검색에서 `터미널`을 검색해서 실행합니다.

터미널에 아래 명령을 붙여넣고 Enter를 누릅니다.

```bash
cd "/Users/name/Desktop/네이버 블로그 mcp/naver-blog-mcp-codex"
```

## 2단계: 필요한 프로그램 설치하기

아래 명령을 한 줄씩 실행합니다.

```bash
uv sync
```

```bash
uv run playwright install chromium
```

첫 번째 명령은 이 도구가 필요한 Python 패키지를 설치합니다. 두 번째 명령은 네이버 블로그를 자동으로 조작할 Chromium 브라우저를 설치합니다.

## 3단계: 네이버 계정 정보를 로컬 `.env` 파일에 저장하기

네이버 아이디와 비밀번호는 Codex 설정 파일에 직접 넣지 않습니다. 이 프로젝트 폴더 안의 `.env` 파일에만 저장합니다. `.env` 파일은 Git에 올라가지 않도록 이미 제외되어 있습니다.

터미널에 아래 명령을 입력합니다.

```bash
cat > .env <<'EOF'
NAVER_BLOG_ID=
NAVER_BLOG_PASSWORD=
HEADLESS=false
SLOW_MO=100
LOG_LEVEL=INFO
IMAGE_UPLOAD_ALLOWED_DIRS=blog-images
SAVE_DEBUG_ARTIFACTS=false
EOF
chmod 600 .env
```

그다음 `.env` 파일을 열어 본인 정보로 바꿉니다.

```bash
open -a TextEdit .env
```

예를 들어 네이버 아이디가 `myblogid`라면 이렇게 됩니다.

```env
NAVER_BLOG_ID=myblogid
NAVER_BLOG_PASSWORD=
```

`NAVER_BLOG_PASSWORD=` 뒤에는 실제 비밀번호를 직접 입력하세요.

## 4단계: Codex 설정 파일 열기

터미널에 아래 명령을 입력합니다.

```bash
mkdir -p ~/.codex
open -a TextEdit ~/.codex/config.toml
```

TextEdit이 열리면 아래 내용을 그대로 붙여넣습니다.

```toml
[mcp_servers."naver-blog"]
command = "uv"
args = ["run", "naver-blog-mcp"]
cwd = "/Users/name/Desktop/네이버 블로그 mcp/naver-blog-mcp-codex"
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

수정이 끝나면 저장합니다.

## 5단계: Codex 다시 시작하기

Codex를 완전히 종료한 뒤 다시 실행합니다.

Codex 안에서 `/mcp`를 입력했을 때 `naver-blog`가 보이면 연결된 것입니다.

## 6단계: 처음 사용해보기

Codex에게 이렇게 말해보세요.

```text
내 네이버 블로그 카테고리 목록 보여줘.
```

또는 글을 쓰려면 이렇게 말하면 됩니다.

```text
네이버 블로그에 글 써줘.
제목: 오늘의 테스트 글
내용: Codex MCP로 네이버 블로그 글쓰기 테스트 중입니다.
일단 임시저장으로 해줘.
```

처음 실행할 때는 브라우저 창이 열릴 수 있습니다. 네이버 로그인 확인이나 CAPTCHA가 나오면 직접 완료해 주세요. 한 번 로그인 세션이 저장되면 다음부터는 더 편하게 사용할 수 있습니다.

## 이미지를 올리고 싶을 때

이미지 파일은 반드시 이 프로젝트의 `blog-images` 폴더 안에 넣어야 합니다.

```text
/Users/name/Desktop/네이버 블로그 mcp/naver-blog-mcp-codex/blog-images
```

예를 들어 `blog-images/photo.png`를 글에 넣고 싶으면 Codex에게 이렇게 말합니다.

```text
blog-images/photo.png 이미지를 넣어서 네이버 블로그 글을 써줘.
```

다른 폴더에 있는 이미지는 안전을 위해 거부됩니다.

## 실제 발행 전 주의사항

- 처음에는 꼭 `임시저장으로 해줘`라고 요청해서 테스트하세요.
- 바로 공개 발행하고 싶을 때만 `발행해줘`라고 말하세요.
- 비밀번호가 들어간 `.env` 파일은 다른 사람에게 보내면 안 됩니다.
- 문제가 생겼을 때만 `SAVE_DEBUG_ARTIFACTS=true`로 바꾸세요. 기본값은 스크린샷과 trace를 저장하지 않는 `false`입니다.
- 네이버 보안 정책 때문에 로그인 확인이나 CAPTCHA가 나올 수 있습니다.

## 자주 생기는 문제

### `/mcp`에 `naver-blog`가 안 보여요

Codex를 완전히 종료한 뒤 다시 실행하세요. 그래도 안 보이면 `~/.codex/config.toml`에 붙여넣은 내용에서 따옴표나 경로가 빠졌는지 확인하세요.

### 도구는 보이는데 실행하면 로그인 오류가 나요

`NAVER_BLOG_ID`와 `NAVER_BLOG_PASSWORD`가 정확한지 확인하세요. 네이버에서 추가 인증이 필요한 경우 브라우저 창에서 직접 인증을 완료해야 합니다.

### 브라우저 창이 안 보이고 CAPTCHA 때문에 실패해요

설정에서 아래 줄이 `false`인지 확인하세요.

```toml
HEADLESS = "false"
```

`false`이면 브라우저 창이 보여서 사람이 직접 CAPTCHA를 풀 수 있습니다.

### 글이 바로 올라갈까 봐 불안해요

요청할 때 항상 `임시저장으로 해줘`라고 붙이세요.

```text
네이버 블로그에 글 써줘. 공개 발행하지 말고 임시저장으로 해줘.
```

## 설정을 지우고 싶을 때

TextEdit으로 `~/.codex/config.toml`을 다시 열고, `[mcp_servers."naver-blog"]`부터 아래 네이버 설정 부분까지 삭제한 뒤 저장하면 됩니다.

```bash
open -a TextEdit ~/.codex/config.toml
```
