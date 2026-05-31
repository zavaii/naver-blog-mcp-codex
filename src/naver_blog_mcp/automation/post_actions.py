"""네이버 블로그 글쓰기 자동화."""

import asyncio
import logging
import re
from typing import Optional, Dict, Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .image_upload import get_editor_frame, upload_image, upload_images
from .selectors import (
    POST_WRITE_TITLE,
    POST_WRITE_CONTENT_FRAME,
    POST_WRITE_CONTENT_BODY,
    POST_WRITE_PUBLISH_BTN,
    POST_WRITE_TEMP_SAVE_BTN,
)
from ..config import config


logger = logging.getLogger(__name__)

BLOG_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
MARKDOWN_IMAGE_LINE_PATTERN = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")
DRAFT_RESTORE_DISMISS_TEXTS = [
    "취소",
    "새 글쓰기",
    "새글쓰기",
    "새 글 작성",
    "새로 작성",
    "닫기",
    "아니오",
]


class NaverBlogPostError(Exception):
    """네이버 블로그 글쓰기 관련 에러."""

    pass


async def _action_pause(multiplier: float = 1.0) -> None:
    delay = max(config.ACTION_DELAY_SECONDS * multiplier, 0)
    if delay:
        await asyncio.sleep(delay)


def has_markdown_image_markers(content: str) -> bool:
    """본문 안에 마크다운 이미지 줄이 있는지 확인합니다."""
    return any(
        MARKDOWN_IMAGE_LINE_PATTERN.match(line.strip())
        for line in content.splitlines()
    )


def count_markdown_image_markers(content: str) -> int:
    """본문 안의 마크다운 이미지 줄 개수를 셉니다."""
    return sum(
        1
        for line in content.splitlines()
        if MARKDOWN_IMAGE_LINE_PATTERN.match(line.strip())
    )


def is_existing_draft_prompt_text(text: str) -> bool:
    """SmartEditor의 기존 임시글 복원 안내 문구인지 판별합니다."""
    normalized = re.sub(r"\s+", "", text or "")

    return (
        (
            (
                "작성중인글이있습니다" in normalized
                or "임시저장글이있습니다" in normalized
                or "임시저장된글이있습니다" in normalized
            )
            and (
                "이어서작성하시겠습니까" in normalized
                or "이어작성하시겠습니까" in normalized
                or "불러오시겠습니까" in normalized
                or "복원하시겠습니까" in normalized
            )
        )
        or "작성중인글이있습니다.이어서작성하시겠습니까?" in normalized
        or "임시저장글이있습니다.이어서작성하시겠습니까?" in normalized
    )


def _normalize_button_text(text: Optional[str]) -> str:
    """버튼 텍스트 비교용 정규화."""
    return re.sub(r"\s+", "", text or "")


def _may_be_draft_restore_text(text: str) -> bool:
    """확인 버튼 클릭을 피해야 하는 임시글 관련 문구인지 넓게 판별합니다."""
    normalized = _normalize_button_text(text)
    return (
        ("작성중인글" in normalized and "이어서" in normalized)
        or (
            "임시저장" in normalized
            and (
                "이어서" in normalized
                or "불러오" in normalized
                or "복원" in normalized
                or "하시겠습니까" in normalized
            )
        )
    )


async def _frame_body_text(frame) -> str:
    """접근 가능한 frame의 body 텍스트를 읽습니다."""
    try:
        return await frame.locator("body").inner_text(timeout=1000)
    except Exception:
        return ""


async def _click_first_visible_text(frame, texts: list[str]) -> bool:
    """프레임 안에서 텍스트가 정확히 일치하는 visible 버튼/링크를 클릭합니다."""
    target_texts = {_normalize_button_text(text) for text in texts}
    locator = frame.locator("button:visible, a:visible, [role='button']:visible")

    try:
        count = await locator.count()
    except Exception:
        return False

    for index in range(count):
        candidate = locator.nth(index)
        try:
            visible = await candidate.is_visible()
            if not visible:
                continue

            label = await candidate.get_attribute("aria-label")
            if _normalize_button_text(label) in target_texts:
                await candidate.click(timeout=1500)
                await _action_pause()
                return True

            text = await candidate.inner_text(timeout=500)
            if _normalize_button_text(text) in target_texts:
                await candidate.click(timeout=1500)
                await _action_pause()
                return True
        except Exception:
            continue

    return False


async def dismiss_existing_draft_prompt(
    page: Page,
    timeout: int = 5000,
) -> bool:
    """기존 임시글 복원 팝업이 있으면 새 글 작성을 유지하도록 닫습니다.

    네이버 SmartEditor의 "임시저장글이 있습니다" 팝업에서 "확인"은 기존
    임시글을 불러오는 동작입니다. 자동화가 이 버튼을 누르면 이전 글과 새
    글이 섞이므로, 복원 계열 버튼은 누르지 않고 취소/닫기 계열만 사용합니다.
    """
    deadline = asyncio.get_running_loop().time() + (timeout / 1000)
    saw_prompt = False

    while asyncio.get_running_loop().time() < deadline:
        for frame in page.frames:
            text = await _frame_body_text(frame)
            if not is_existing_draft_prompt_text(text):
                continue

            saw_prompt = True
            logger.info("기존 임시글 복원 팝업 감지: 새 글 작성으로 닫기 시도")

            if await _click_first_visible_text(frame, DRAFT_RESTORE_DISMISS_TEXTS):
                await _action_pause()
            else:
                await page.keyboard.press("Escape")
                await _action_pause()

            remaining_text = await _frame_body_text(frame)
            if not is_existing_draft_prompt_text(remaining_text):
                logger.info("기존 임시글 복원 팝업 닫기 완료")
                return True

        if not saw_prompt:
            await _action_pause(0.35)
        else:
            await _action_pause(0.75)

    if saw_prompt:
        raise NaverBlogPostError(
            "기존 임시글 복원 팝업을 닫지 못했습니다. "
            "기존 임시글을 불러오면 새 글 내용이 섞일 수 있어 중단합니다."
        )

    return False


async def close_editor_popups(
    page: Page,
    allow_confirm: bool = False,
    timeout: int = 1500,
) -> None:
    """에디터 진행을 막는 일반 팝업을 닫습니다."""
    await dismiss_existing_draft_prompt(page, timeout=timeout)

    close_selectors = [
        "button[aria-label='닫기']:visible",
        ".se-popup-button-close:visible",
        "button.se-popup-close:visible",
        ".se-help-panel button:visible",
    ]

    for frame in page.frames:
        frame_text = await _frame_body_text(frame)
        frame_has_draft_prompt = is_existing_draft_prompt_text(frame_text)
        close_texts = ["취소", "닫기"]
        if allow_confirm and not _may_be_draft_restore_text(frame_text):
            close_texts.append("확인")

        for selector in close_selectors:
            try:
                locator = frame.locator(selector)
                count = await locator.count()
                if count > 0:
                    await locator.last.click(timeout=1000)
                    await _action_pause(0.35)
                    break
            except Exception:
                continue

        if frame_has_draft_prompt:
            continue

        await _click_first_visible_text(frame, close_texts)


def split_content_by_image_markers(content: str) -> list[tuple[str, str]]:
    """마크다운 이미지 줄을 기준으로 본문을 텍스트/이미지 블록으로 나눕니다."""
    blocks: list[tuple[str, str]] = []
    text_buffer: list[str] = []

    for line in content.splitlines(keepends=True):
        if MARKDOWN_IMAGE_LINE_PATTERN.match(line.strip()):
            if text_buffer or not blocks:
                blocks.append(("text", "".join(text_buffer)))
                text_buffer = []
            blocks.append(("image", line.strip()))
            continue
        text_buffer.append(line)

    if text_buffer or not blocks:
        blocks.append(("text", "".join(text_buffer)))

    return blocks


def replace_image_markers_with_placeholders(
    content: str,
) -> tuple[str, list[str]]:
    """마크다운 이미지 줄을 안정적으로 치환 가능한 자리표시자로 바꿉니다."""
    placeholders: list[str] = []
    output_lines: list[str] = []

    for line in content.splitlines(keepends=True):
        if MARKDOWN_IMAGE_LINE_PATTERN.match(line.strip()):
            token = f"[[NAVER_IMAGE_{len(placeholders) + 1:03d}]]"
            line_ending = "\n" if line.endswith("\n") else ""
            output_lines.append(f"{token}{line_ending}")
            placeholders.append(token)
            continue
        output_lines.append(line)

    return "".join(output_lines), placeholders


async def insert_editor_text(page: Page, fallback_target, text: str) -> None:
    """현재 포커스된 에디터에 텍스트를 삽입합니다.

    keyboard.type()은 SmartEditor의 자동 번호목록 변환을 쉽게 건드립니다.
    insert_text()를 줄 단위로 사용하고 Enter로 문단을 만들어, 원문 번호
    중복과 줄바꿈 붕괴를 함께 줄입니다.
    """
    if not text:
        return

    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line:
            try:
                await page.keyboard.insert_text(line)
            except Exception as e:
                logger.debug(f"insert_text 실패, 순차 타이핑으로 대체: {e}")
                if fallback_target is not None:
                    await fallback_target.type(line, delay=10)
                else:
                    await page.keyboard.type(line, delay=10)

        if index < len(lines) - 1:
            await page.keyboard.press("Enter")
            await _action_pause(0.1)


async def paste_editor_text(page: Page, fallback_target, text: str) -> None:
    """현재 포커스된 에디터에 일반 텍스트를 붙여넣습니다."""
    if not text:
        return

    try:
        await page.context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://blog.naver.com",
        )
    except Exception as e:
        logger.debug(f"Clipboard permission grant failed (ignored): {e}")

    try:
        await page.evaluate(
            "async (value) => navigator.clipboard.writeText(value)",
            text,
        )
        await page.keyboard.press("Meta+V")
    except Exception as e:
        logger.debug(f"텍스트 붙여넣기 실패, 줄 단위 삽입으로 대체: {e}")
        await insert_editor_text(page, fallback_target, text)


async def select_editor_text(page: Page, text: str) -> bool:
    """에디터 iframe 안에서 특정 텍스트를 찾아 선택합니다."""
    frame = await get_editor_frame(page)
    return await frame.evaluate(
        """
        (needle) => {
            const root =
                document.querySelector("article.se-components-wrap") ||
                document.querySelector(".se-canvas") ||
                document.body;
            const walker = document.createTreeWalker(
                root,
                NodeFilter.SHOW_TEXT,
            );

            while (walker.nextNode()) {
                const node = walker.currentNode;
                const index = node.nodeValue.indexOf(needle);
                if (index === -1) {
                    continue;
                }

                const range = document.createRange();
                range.setStart(node, index);
                range.setEnd(node, index + needle.length);

                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);

                const parent = node.parentElement;
                if (parent) {
                    parent.scrollIntoView({ block: "center", inline: "nearest" });
                }

                return true;
            }

            return false;
        }
        """,
        text,
    )


async def delete_selected_editor_text(page: Page) -> None:
    """현재 에디터 선택 영역을 지우고 그 위치에 커서를 남깁니다."""
    frame = await get_editor_frame(page)
    await frame.evaluate(
        """
        () => {
            document.execCommand("delete");
            document.dispatchEvent(new InputEvent("input", { bubbles: true }));
        }
        """
    )


async def remove_editor_text_and_place_cursor(page: Page, text: str) -> bool:
    """텍스트 노드에서 특정 문자열을 제거하고 그 위치에 커서를 둡니다."""
    frame = await get_editor_frame(page)
    return await frame.evaluate(
        """
        (needle) => {
            const root =
                document.querySelector("article.se-components-wrap") ||
                document.querySelector(".se-canvas") ||
                document.body;
            const walker = document.createTreeWalker(
                root,
                NodeFilter.SHOW_TEXT,
            );

            while (walker.nextNode()) {
                const node = walker.currentNode;
                const index = node.nodeValue.indexOf(needle);
                if (index === -1) {
                    continue;
                }

                node.nodeValue =
                    node.nodeValue.slice(0, index) +
                    node.nodeValue.slice(index + needle.length);

                const range = document.createRange();
                range.setStart(node, index);
                range.collapse(true);

                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);

                const parent = node.parentElement;
                if (parent) {
                    parent.scrollIntoView({ block: "center", inline: "nearest" });
                }

                document.dispatchEvent(new InputEvent("input", { bubbles: true }));
                return true;
            }

            return false;
        }
        """,
        text,
    )


async def remove_unresolved_image_placeholders(page: Page) -> int:
    """에디터에 남은 NAVER_IMAGE 자리표시자 텍스트를 모두 제거합니다."""
    frame = await get_editor_frame(page)
    return await frame.evaluate(
        """
        () => {
            const root =
                document.querySelector("article.se-components-wrap") ||
                document.querySelector(".se-canvas") ||
                document.body;
            const pattern = /\\[\\[NAVER_IMAGE_\\d{3}\\]\\]/g;
            const walker = document.createTreeWalker(
                root,
                NodeFilter.SHOW_TEXT,
            );
            let removed = 0;

            while (walker.nextNode()) {
                const node = walker.currentNode;
                const text = node.nodeValue || "";
                const matches = text.match(pattern);
                if (!matches) {
                    continue;
                }
                removed += matches.length;
                node.nodeValue = text.replace(pattern, "");
            }

            if (removed > 0) {
                document.dispatchEvent(new InputEvent("input", { bubbles: true }));
            }
            return removed;
        }
        """
    )


async def assert_no_unresolved_image_placeholders(page: Page) -> None:
    """발행 전 NAVER_IMAGE 자리표시자가 남아 있으면 실패시킵니다."""
    frame = await get_editor_frame(page)
    remaining = await frame.evaluate(
        """
        () => {
            const root =
                document.querySelector("article.se-components-wrap") ||
                document.querySelector(".se-canvas") ||
                document.body;
            const text = root.innerText || "";
            return text.match(/\\[\\[NAVER_IMAGE_\\d{3}\\]\\]/g) || [];
        }
        """
    )
    if remaining:
        raise NaverBlogPostError(
            "이미지 자리표시자가 본문에 남아 있어 발행을 중단합니다: "
            + ", ".join(remaining)
        )


async def wait_for_editor_uploads_idle(page: Page, timeout: int = 30000) -> None:
    """SmartEditor 이미지 업로드 상태 문구가 사라질 때까지 기다립니다."""
    frames = getattr(page, "frames", None)
    if frames is None:
        return

    deadline = asyncio.get_running_loop().time() + (timeout / 1000)
    idle_rounds = 0

    while asyncio.get_running_loop().time() < deadline:
        busy = False
        for frame in frames:
            try:
                frame_busy = await frame.evaluate(
                    """
                    () => {
                        const text = document.body.innerText || "";
                        return text.includes("업로드 준비") ||
                            text.includes("전송중") ||
                            text.includes("업로드 중");
                    }
                    """
                )
                busy = busy or bool(frame_busy)
            except Exception:
                continue

        if not busy:
            idle_rounds += 1
            if idle_rounds >= 2:
                return
        else:
            idle_rounds = 0

        await asyncio.sleep(1)

    logger.warning("이미지 업로드 완료 대기 시간이 초과되었습니다.")


async def navigate_to_post_write_page(
    page: Page, blog_id: Optional[str] = None, timeout: int = 30000
) -> None:
    """
    네이버 블로그 글쓰기 페이지로 이동합니다.

    Args:
        page: Playwright Page 객체
        blog_id: 블로그 ID (옵션, 없으면 자동으로 현재 로그인된 블로그 사용)
        timeout: 페이지 로딩 대기 시간 (ms)

    Raises:
        NaverBlogPostError: 페이지 이동 실패 시
    """
    try:
        # 방법 1: blog_id가 주어진 경우
        if blog_id:
            safe_blog_id = blog_id.strip().strip("/")
            if not BLOG_ID_PATTERN.fullmatch(safe_blog_id):
                raise NaverBlogPostError("유효하지 않은 블로그 아이디입니다.")
            url = f"https://blog.naver.com/{safe_blog_id}/postwrite"
        else:
            # 방법 2: 블로그 메인에서 글쓰기 버튼 찾아서 클릭
            # 먼저 블로그 메인으로 이동
            await page.goto("https://blog.naver.com", wait_until="load", timeout=timeout)
            await asyncio.sleep(2)

            # 글쓰기 버튼 찾기 (여러 셀렉터 시도)
            write_btn_selectors = [
                "a[href*='postwrite']",
                "a:has-text('글쓰기')",
                "button:has-text('글쓰기')",
            ]

            write_btn_found = False
            for selector in write_btn_selectors:
                count = await page.locator(selector).count()
                if count > 0:
                    # href 가져오기
                    element = page.locator(selector).first
                    href = await element.get_attribute("href")
                    if href:
                        # 절대 URL로 변환
                        if href.startswith("/"):
                            url = f"https://blog.naver.com{href}"
                        elif href.startswith("http"):
                            url = href
                        else:
                            url = f"https://blog.naver.com/{href}"
                        write_btn_found = True
                        print(f"   글쓰기 버튼 발견: {url}")
                        break

            if not write_btn_found:
                # 기본 URL 사용
                url = "https://blog.naver.com/postwrite"
                print(f"   글쓰기 버튼을 찾지 못했습니다. 기본 URL 사용: {url}")

        await page.goto(url, wait_until="load", timeout=timeout)
        await asyncio.sleep(3)  # 에디터 로딩 충분히 대기
        await dismiss_existing_draft_prompt(page)

        # 글쓰기 페이지인지 확인
        current_url = page.url
        print(f"   현재 URL: {current_url}")

        # URL에 postwrite, PostWriteForm, Redirect=Write가 포함되어 있으면 성공으로 간주
        if (
            "postwrite" in current_url.lower()
            or "PostWriteForm" in current_url
            or "Redirect=Write" in current_url
        ):
            logger.info(f"글쓰기 페이지로 이동: {current_url}")
            return

        # 제목 입력란 확인 (추가 검증)
        title_input_exists = False
        if isinstance(POST_WRITE_TITLE, list):
            for selector in POST_WRITE_TITLE:
                count = await page.locator(selector).count()
                if count > 0:
                    title_input_exists = True
                    print(f"   제목 입력란 발견: {selector}")
                    break
        else:
            count = await page.locator(POST_WRITE_TITLE).count()
            title_input_exists = count > 0

        if title_input_exists:
            logger.info(f"글쓰기 페이지로 이동: {url}")
            return

        raise NaverBlogPostError(f"글쓰기 페이지 로딩에 실패했습니다. 현재 URL: {current_url}")

    except PlaywrightTimeout as e:
        raise NaverBlogPostError(f"글쓰기 페이지 이동 시간 초과: {str(e)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise NaverBlogPostError(f"글쓰기 페이지 이동 중 오류: {str(e)}")


async def fill_post_title(page: Page, title: str) -> None:
    """
    블로그 글 제목을 입력합니다.

    Args:
        page: Playwright Page 객체
        title: 글 제목

    Raises:
        NaverBlogPostError: 제목 입력 실패 시
    """
    try:
        await dismiss_existing_draft_prompt(page, timeout=1500)

        # 제목 입력란 찾기 (대체 셀렉터 시도)
        title_filled = False

        # 방법 1: 일반적인 셀렉터 시도
        if isinstance(POST_WRITE_TITLE, list):
            for selector in POST_WRITE_TITLE:
                try:
                    element_count = await page.locator(selector).count()
                    if element_count > 0:
                        # contenteditable div는 fill 대신 type 사용
                        element = page.locator(selector).first

                        # contenteditable인지 확인
                        is_contenteditable = await element.get_attribute("contenteditable")

                        if is_contenteditable:
                            # contenteditable div: 클릭 후 타이핑
                            await element.click()
                            await _action_pause(0.5)
                            await page.keyboard.press("Meta+A")
                            await page.keyboard.press("Backspace")
                            await page.keyboard.insert_text(title)
                        else:
                            # 일반 input: fill 사용
                            await element.fill(title)
                            await _action_pause()

                        title_filled = True
                        logger.info(f"제목 입력 완료: {title} (selector: {selector})")
                        break
                except Exception as e:
                    print(f"   셀렉터 {selector} 실패: {e}")
                    continue

        # 방법 2: 제목 영역을 직접 클릭 (좌표 기반)
        if not title_filled:
            try:
                # 제목 영역 대략적인 위치 클릭 (상단 중앙)
                await page.mouse.click(450, 250)
                await _action_pause(0.75)
                await page.keyboard.type(title, delay=50)
                title_filled = True
                logger.info(f"제목 입력 완료 (클릭 방식): {title}")
            except Exception as e:
                print(f"   클릭 방식 실패: {e}")

        # 방법 3: Tab 키로 이동
        if not title_filled:
            try:
                # 페이지 최상단으로 포커스 이동 후 Tab으로 제목까지 이동
                await page.keyboard.press("Tab")
                await _action_pause(0.5)
                await page.keyboard.type(title, delay=50)
                title_filled = True
                logger.info(f"제목 입력 완료 (Tab 방식): {title}")
            except Exception as e:
                print(f"   Tab 방식 실패: {e}")

        if not title_filled:
            raise NaverBlogPostError("제목 입력란을 찾을 수 없습니다.")

        await _action_pause()

    except Exception as e:
        raise NaverBlogPostError(f"제목 입력 중 오류: {str(e)}")


async def fill_post_content(page: Page, content: str, use_html: bool = False) -> None:
    """
    블로그 글 본문을 입력합니다.
    스마트에디터 ONE은 iframe 없이 직접 contenteditable을 사용합니다.

    Args:
        page: Playwright Page 객체
        content: 글 본문 내용
        use_html: HTML 모드로 입력할지 여부 (기본: False, 텍스트 모드)

    Raises:
        NaverBlogPostError: 본문 입력 실패 시
    """
    try:
        await close_editor_popups(page, allow_confirm=True)

        content_filled = False

        # 방법 1: iframe이 있는 경우 (구형 스마트에디터)
        iframe_selectors = (
            POST_WRITE_CONTENT_FRAME
            if isinstance(POST_WRITE_CONTENT_FRAME, list)
            else [POST_WRITE_CONTENT_FRAME]
        )

        for iframe_selector in iframe_selectors:
            try:
                iframe_count = await page.locator(iframe_selector).count()
                if iframe_count > 0:
                    print(f"   iframe 발견: {iframe_selector}")
                    frame_element = await page.wait_for_selector(
                        iframe_selector, timeout=5000
                    )
                    iframe_found = await frame_element.content_frame()

                    if iframe_found:
                        await close_editor_popups(page, allow_confirm=True)

                        # iframe 내부에서 contenteditable 찾기
                        body_selectors = (
                            POST_WRITE_CONTENT_BODY
                            if isinstance(POST_WRITE_CONTENT_BODY, list)
                            else [POST_WRITE_CONTENT_BODY]
                        )

                        for body_selector in body_selectors:
                            try:
                                content_body = await iframe_found.wait_for_selector(
                                    body_selector, timeout=3000
                                )
                                if content_body:
                                    await content_body.click()
                                    await _action_pause(0.75)
                                    await paste_editor_text(
                                        page, content_body, content
                                    )
                                    content_filled = True
                                    logger.info(
                                        f"본문 입력 완료 (iframe 방식, selector: {body_selector})"
                                    )
                                    break
                            except Exception as e:
                                print(f"   iframe 내부 셀렉터 {body_selector} 실패: {e}")
                                continue

                        if content_filled:
                            # iframe에서 메인 페이지로 포커스 전환
                            await page.evaluate("() => { window.focus(); }")
                            await _action_pause(0.75)
                            break
            except Exception:
                continue

        # 방법 2: iframe 없이 직접 contenteditable (스마트에디터 ONE)
        if not content_filled:
            print("   iframe 없음, 직접 contenteditable 찾기 시도")

            # 본문 영역 찾기 - 여러 방법 시도
            content_selectors = [
                "div[contenteditable='true']:not([data-placeholder='제목'])",  # 제목이 아닌 contenteditable
                "div[contenteditable='true'][role='textbox']",
                "div.se-component",  # 스마트에디터 컴포넌트
                "div:has-text('글감과 함께')",  # 플레이스홀더 텍스트로 찾기
            ]

            for selector in content_selectors:
                try:
                    element_count = await page.locator(selector).count()
                    if element_count > 0:
                        element = page.locator(selector).first
                        await element.click()
                        await _action_pause(0.75)

                        # 기존 플레이스홀더 텍스트 제거
                        await page.keyboard.press("Control+A")
                        await _action_pause(0.35)

                        # 본문 입력
                        await paste_editor_text(page, element, content)
                        content_filled = True
                        logger.info(f"본문 입력 완료 (직접 방식, selector: {selector})")
                        break
                except Exception as e:
                    print(f"   셀렉터 {selector} 실패: {e}")
                    continue

        if not content_filled:
            raise NaverBlogPostError("본문 입력 영역을 찾을 수 없습니다.")

        await _action_pause()

    except PlaywrightTimeout as e:
        raise NaverBlogPostError(f"본문 입력 시간 초과: {str(e)}")
    except Exception as e:
        raise NaverBlogPostError(f"본문 입력 중 오류: {str(e)}")


async def fill_post_content_with_images(
    page: Page,
    content: str,
    images: list[str],
    use_html: bool = False,
) -> int:
    """마크다운 이미지 줄 위치에 맞춰 본문과 이미지를 순서대로 입력합니다."""
    placeholder_content, placeholders = replace_image_markers_with_placeholders(content)

    if not placeholders:
        await fill_post_content(page, content, use_html)
        return 0

    await fill_post_content(page, placeholder_content, use_html)

    images_uploaded = 0

    for index, token in enumerate(placeholders):
        if index >= len(images):
            logger.warning(f"이미지 마커에 대응하는 이미지가 없습니다: {token}")
            break

        try:
            if not await remove_editor_text_and_place_cursor(page, token):
                logger.warning(f"이미지 자리표시자를 찾지 못했습니다: {token}")
                continue

            await _action_pause(0.35)

            image_path = images[index]
            upload_result = await upload_image(page, image_path)
            if upload_result.get("success"):
                images_uploaded += 1
            await _action_pause(0.5)
        except Exception as e:
            image_path = images[index] if index < len(images) else token
            logger.warning(f"이미지 인라인 업로드 실패 ({image_path}): {e}")

    if len(images) > len(placeholders):
        remaining = images[len(placeholders):]
        logger.info(f"남은 이미지 {len(remaining)}개를 본문 끝에 업로드합니다.")
        upload_result = await upload_images(page, remaining)
        images_uploaded += len(upload_result.get("uploaded", []))

    removed = await remove_unresolved_image_placeholders(page)
    if removed:
        logger.warning(f"남은 이미지 자리표시자 {removed}개를 제거했습니다.")

    return images_uploaded


async def publish_post(
    page: Page, wait_for_completion: bool = True, timeout: int = 30000
) -> Dict[str, Any]:
    """
    블로그 글을 발행합니다.

    Args:
        page: Playwright Page 객체
        wait_for_completion: 발행 완료를 기다릴지 여부
        timeout: 발행 완료 대기 시간 (ms)

    Returns:
        발행 결과 딕셔너리
        {
            "success": bool,
            "message": str,
            "post_url": str (발행된 글 URL, 성공 시)
        }

    Raises:
        NaverBlogPostError: 발행 실패 시
    """
    try:
        # 0. 메인 페이지로 포커스 전환 (iframe에서 나오기)
        # 명시적으로 메인 페이지로 전환
        await page.bring_to_front()
        await page.evaluate(
            "() => { if (window.parent) { window.parent.focus(); } window.focus(); }"
        )
        await _action_pause()

        # 페이지가 실제로 로드되었는지 확인
        print(f"   현재 URL: {page.url}")
        print(f"   페이지 타이틀: {await page.title()}")

        await close_editor_popups(page, allow_confirm=True)

        # 1. 발행 버튼 찾기 (대체 셀렉터 시도)
        publish_clicked = False

        # 추가 발행 버튼 셀렉터
        # 네이버 블로그는 하단 중앙에 "글쓰기" 버튼이 있음 (이것이 발행 버튼)
        publish_selectors = [
            "div.publish_area button:has-text('글쓰기')",  # 하단 중앙 글쓰기 버튼
            "button.publish_btn",
            "a.publish_btn:has-text('글쓰기')",
            "button:has-text('글쓰기'):visible",
            "a:has-text('글쓰기'):visible",
            "button:has-text('발행'):visible",
            "button.se-toolbar-group-button.se-toolbar-publish-button",
            "button:has-text('등록')",
            "button.publish",
            "button.btn_post",
            "a:has-text('발행')",
            "a.btn_submit",
            "button[type='submit']",
        ]

        # 기존 셀렉터와 병합
        if isinstance(POST_WRITE_PUBLISH_BTN, list):
            publish_selectors = POST_WRITE_PUBLISH_BTN + publish_selectors
        else:
            publish_selectors.insert(0, POST_WRITE_PUBLISH_BTN)

        # 1. 모든 iframe에서 발행 버튼 찾기
        all_frames = page.frames
        for idx, frame in enumerate(all_frames):
            try:
                # Frame 내부의 도움말 팝업 닫기
                help_popup_selectors = [
                    "button.se-help-close-btn",
                    "button:has-text('닫기')",
                    ".se-help-close",
                ]
                for help_sel in help_popup_selectors:
                    help_count = await frame.locator(help_sel).count()
                    if help_count > 0:
                        await frame.locator(help_sel).first.click(timeout=2000)
                        await _action_pause()
                        break

                # 발행 버튼 찾기 (우선순위: 발행 > 글쓰기)
                search_texts = ["발행", "글쓰기"]
                for search_text in search_texts:
                    write_btn_count = await frame.locator(
                        f"button:has-text('{search_text}'):visible"
                    ).count()
                    if write_btn_count > 0:
                        element = frame.locator(
                            f"button:has-text('{search_text}'):visible"
                        ).first
                        await element.click(timeout=5000)
                        publish_clicked = True
                        logger.info(f"발행 버튼 클릭 성공 (Frame {idx})")
                        await _action_pause(2)
                        break

                if publish_clicked:
                    break
            except Exception:
                continue

        if not publish_clicked:
            if config.SAVE_DEBUG_ARTIFACTS:
                await page.screenshot(path="playwright-state/error_publish_btn.png")
            raise NaverBlogPostError("발행 버튼을 찾을 수 없습니다.")

        # 2. 발행 설정 대화상자에서 최종 "발행" 버튼 클릭
        if publish_clicked:
            try:
                await _action_pause()  # 대화상자 로딩 대기

                # 대화상자 내 발행 버튼을 force=True로 클릭 시도
                final_publish_clicked = False
                for idx, frame in enumerate(page.frames):
                    try:
                        dialog_publish_selectors = [
                            ".layer_popup__i0QOY button[class*='confirm']:has-text('발행')",
                            ".layer_popup__i0QOY button:has-text('발행')",
                        ]

                        for selector in dialog_publish_selectors:
                            try:
                                btn_count = await frame.locator(selector).count()
                                if btn_count > 0:
                                    await frame.locator(selector).first.click(
                                        force=True, timeout=5000
                                    )
                                    final_publish_clicked = True
                                    await _action_pause(2)
                                    break
                            except Exception:
                                continue

                        if final_publish_clicked:
                            break
                    except Exception:
                        continue

                # JavaScript로 대화상자 내 발행 버튼 클릭 (fallback)
                if not final_publish_clicked:
                    for frame in page.frames:
                        try:
                            result = await frame.evaluate("""
                                () => {
                                    const popup = document.querySelector('.layer_popup__i0QOY.is_show__TMSLq');
                                    if (!popup) return 'No popup';

                                    const buttons = popup.querySelectorAll('button');
                                    for (let btn of buttons) {
                                        if ((btn.textContent || '').trim() === '발행') {
                                            btn.click();
                                            return 'Clicked';
                                        }
                                    }
                                    return 'No button';
                                }
                            """)
                            if 'Clicked' in result:
                                await _action_pause(3)
                                break
                        except Exception:
                            continue

            except Exception:
                pass

        # 3. 발행 완료 대기 (옵션)
        if wait_for_completion:
            try:
                # 발행 후 글 보기 페이지로 리다이렉트되는지 확인
                # URL 패턴: https://blog.naver.com/{blog_id}/{post_id}
                await page.wait_for_url("**/blog.naver.com/*/**", timeout=timeout)
                post_url = page.url

                # PostView 페이지인지 확인 (본문 영역이 있는지)
                # 글쓰기 페이지가 아닌 글 보기 페이지인지 체크
                if "postwrite" not in post_url.lower() and "redirect=write" not in post_url.lower():
                    # URL이 {blog_id}/{post_id} 형태인지 확인
                    logger.info(f"발행 완료: {post_url}")
                    return {
                        "success": True,
                        "message": "글이 성공적으로 발행되었습니다.",
                        "post_url": post_url,
                    }
                else:
                    raise NaverBlogPostError("발행 후 페이지 이동에 실패했습니다.")

            except PlaywrightTimeout:
                raise NaverBlogPostError("발행 완료 대기 시간 초과")
        else:
            return {
                "success": True,
                "message": "발행 요청을 전송했습니다.",
                "post_url": None,
            }

    except Exception as e:
        raise NaverBlogPostError(f"발행 중 오류: {str(e)}")


async def save_draft(page: Page) -> Dict[str, Any]:
    """현재 글쓰기 화면의 글을 임시저장합니다."""
    temp_save_selectors = (
        list(POST_WRITE_TEMP_SAVE_BTN)
        if isinstance(POST_WRITE_TEMP_SAVE_BTN, list)
        else [POST_WRITE_TEMP_SAVE_BTN]
    )
    temp_save_selectors.extend(
        [
            "button:has-text('임시저장'):visible",
            "a:has-text('임시저장'):visible",
            "button[class*='temp']:visible",
            "button[class*='save']:visible",
            "a[class*='save']:visible",
        ]
    )

    try:
        await page.bring_to_front()
        await page.evaluate("() => { window.focus(); }")
        await page.keyboard.press("Escape")
        await _action_pause(0.5)
        await close_editor_popups(page, allow_confirm=False)

        # 도움말/팝업 패널이 발행·임시저장 영역을 덮으면 버튼 탐색이 실패합니다.
        close_selectors = [
            "button[aria-label='닫기']:visible",
            "button:has-text('닫기'):visible",
            ".se-help-panel button:visible",
            ".se-popup-button-close:visible",
        ]
        for frame in page.frames:
            for selector in close_selectors:
                try:
                    count = await frame.locator(selector).count()
                    if count > 0:
                        await frame.locator(selector).last.click(timeout=1000)
                        await _action_pause(0.35)
                        break
                except Exception:
                    continue

        try:
            await page.evaluate("() => window.scrollTo(0, 0)")
        except Exception:
            pass
        for frame in page.frames:
            try:
                await frame.evaluate("() => window.scrollTo(0, 0)")
            except Exception:
                continue
        await _action_pause()

        for frame in page.frames:
            for selector in temp_save_selectors:
                try:
                    button = frame.locator(selector).first
                    if await button.count() > 0:
                        await button.click(timeout=5000)
                        await _action_pause()
                        logger.info(f"임시저장 버튼 클릭 성공: {selector}")
                        return {
                            "success": True,
                            "message": "글을 임시저장했습니다.",
                            "post_url": None,
                        }
                except Exception as e:
                    logger.debug(f"임시저장 셀렉터 실패 ({selector}): {e}")
                    continue

        raise NaverBlogPostError("임시저장 버튼을 찾을 수 없습니다.")
    except NaverBlogPostError:
        raise
    except Exception as e:
        raise NaverBlogPostError(f"임시저장 중 오류: {str(e)}")


async def create_blog_post(
    page: Page,
    title: str,
    content: str,
    blog_id: Optional[str] = None,
    use_html: bool = False,
    publish: bool = True,
    images: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    네이버 블로그에 새 글을 작성하고 발행하는 전체 프로세스.

    Args:
        page: Playwright Page 객체 (로그인된 상태여야 함)
        title: 글 제목
        content: 글 본문
        blog_id: 블로그 ID (옵션)
        use_html: HTML 모드로 본문 입력할지 여부
        publish: True면 공개 발행, False면 임시저장
        images: 첨부할 이미지 파일 경로 목록

    Returns:
        발행 결과 딕셔너리
        {
            "success": bool,
            "message": str,
            "post_url": str,
            "title": str,
            "images_uploaded": int,
        }

    Raises:
        NaverBlogPostError: 글 작성 실패 시
    """
    try:
        # 1. 글쓰기 페이지로 이동
        await navigate_to_post_write_page(page, blog_id)
        await _action_pause()

        # 2. 제목 입력
        await fill_post_title(page, title)
        await _action_pause()

        # 3. 본문 입력 및 이미지 업로드
        images_uploaded = 0
        has_image_markers = has_markdown_image_markers(content)
        may_have_image_placeholders = has_image_markers or "[[NAVER_IMAGE_" in content

        if images and has_image_markers:
            expected_inline_images = min(len(images), count_markdown_image_markers(content))
            images_uploaded = await fill_post_content_with_images(
                page, content, images, use_html
            )
            if images_uploaded < expected_inline_images:
                raise NaverBlogPostError(
                    "이미지 마커 "
                    f"{expected_inline_images}개 중 {images_uploaded}개만 업로드되어 발행을 중단합니다."
                )
        else:
            await fill_post_content(page, content, use_html)
        await _action_pause()

        # 4. 이미지 마커가 없는 기존 호출은 본문 끝에 이미지를 업로드
        if images and not has_image_markers:
            upload_result = await upload_images(page, images)
            images_uploaded = len(upload_result.get("uploaded", []))
            if upload_result.get("failed"):
                logger.warning(f"일부 이미지 업로드 실패: {upload_result['failed']}")
            await _action_pause()

        await wait_for_editor_uploads_idle(page)
        if may_have_image_placeholders:
            removed_placeholders = await remove_unresolved_image_placeholders(page)
            if removed_placeholders:
                logger.warning(
                    f"발행 전 이미지 자리표시자 {removed_placeholders}개를 제거했습니다."
                )
            await assert_no_unresolved_image_placeholders(page)

        # 5. 발행 또는 임시저장
        if publish:
            result = await publish_post(page, wait_for_completion=True)
        else:
            result = await save_draft(page)

        result["title"] = title
        result["images_uploaded"] = images_uploaded
        return result

    except NaverBlogPostError:
        raise
    except Exception as e:
        raise NaverBlogPostError(f"글 작성 중 오류: {str(e)}")
