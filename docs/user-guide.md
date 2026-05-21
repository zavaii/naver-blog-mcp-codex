# 네이버 블로그 MCP 사용 가이드

이 저장소는 Codex에서 네이버 블로그 글 작성과 카테고리 조회를 호출하기 위한 MCP 서버입니다. 처음 쓰는 사람은 [`easy-start-guide.md`](easy-start-guide.md)를 먼저 보면 됩니다.

## 가능한 작업

- `naver_blog_create_post`: 제목과 본문으로 새 글을 작성합니다.
- `naver_blog_list_categories`: 내 블로그의 카테고리 목록을 조회합니다.

`naver_blog_create_post`는 현재 카테고리 지정과 태그 입력을 지원하지 않습니다. 값을 보내면 서버가 실패 응답을 반환합니다.

## 계정 정보 보관

네이버 아이디와 비밀번호는 Codex 설정 파일에 넣지 말고, 저장소 루트의 `.env` 파일에만 저장합니다.

```env
NAVER_BLOG_ID=
NAVER_BLOG_PASSWORD=
HEADLESS=false
SLOW_MO=100
LOG_LEVEL=INFO
IMAGE_UPLOAD_ALLOWED_DIRS=blog-images
SAVE_DEBUG_ARTIFACTS=false
```

`.env` 파일은 Git에 올리면 안 됩니다. 이 저장소의 `.gitignore`에는 이미 제외 규칙이 들어 있습니다.

## 이미지 업로드

이미지는 기본적으로 저장소 루트의 `blog-images/` 폴더 안 파일만 허용합니다. 예를 들어 `blog-images/photo.png`는 가능하지만, `/Users/name/Desktop/secret.png`처럼 임의의 로컬 파일 경로는 거부됩니다.

허용 폴더를 추가해야 할 때만 `.env`의 `IMAGE_UPLOAD_ALLOWED_DIRS`에 쉼표로 구분해서 추가합니다.

## 발행과 임시저장

기본값은 즉시 발행입니다.

```json
{
  "title": "테스트 글",
  "content": "Codex MCP 서버로 작성한 글입니다.",
  "publish": true
}
```

임시저장을 원하면 `publish`를 `false`로 보냅니다.

```json
{
  "title": "임시저장 테스트",
  "content": "아직 공개하지 않을 글입니다.",
  "publish": false
}
```

`publish=false`일 때는 공개 발행 버튼을 누르지 않고 임시저장 버튼만 찾습니다.

## 디버그 파일

기본값은 `SAVE_DEBUG_ARTIFACTS=false`라서 Playwright trace와 전체 페이지 스크린샷을 저장하지 않습니다. 문제가 생겨 원인 분석이 필요할 때만 `true`로 바꾸고, 생성된 `playwright-state/` 폴더는 외부에 공유하지 마세요.
