"""이미지 업로드 자동화 함수.

이 모듈은 네이버 블로그 글쓰기 에디터에서 이미지를 업로드하는
Playwright 자동화 함수를 제공합니다.
"""

import asyncio
import base64
import logging
import mimetypes
import tempfile
from pathlib import Path
from typing import Optional, Union, List

from playwright.async_api import Page, Frame, TimeoutError as PlaywrightTimeoutError

from ..config import config, get_allowed_image_dirs
from ..utils.exceptions import (
    UploadError,
    ElementNotFoundError,
    TimeoutError,
)
from ..utils.retry import retry_on_error

logger = logging.getLogger(__name__)


# 이미지 업로드 관련 셀렉터
IMAGE_BUTTON_SELECTORS = [
    "button[data-name='image']",
    "button:has-text('사진')",
    ".se-image-toolbar-button",
]

FILE_INPUT_SELECTOR = "input[type='file']#hidden-file"
FILE_INPUT_SELECTORS = [
    FILE_INPUT_SELECTOR,
    "input[type='file'][accept*='image']",
    "input[type='file']",
]

SUPPORTED_IMAGE_FORMATS = [
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".heic",
    ".heif",
    ".webp",
]

# 업로드된 이미지를 나타내는 셀렉터
UPLOADED_IMAGE_SELECTORS = [
    ".se-image-resource",
    ".se-component-content img",
    "img[data-type='img']",
]


async def _action_pause(multiplier: float = 1.0) -> None:
    delay = max(config.ACTION_DELAY_SECONDS * multiplier, 0)
    if delay:
        await asyncio.sleep(delay)


def validate_image_path_allowed(image_path: Path) -> Path:
    """이미지 경로가 업로드 허용 디렉터리 안에 있는지 검증합니다."""
    resolved_path = image_path.expanduser().resolve()
    allowed_dirs = get_allowed_image_dirs()

    for allowed_dir in allowed_dirs:
        try:
            resolved_path.relative_to(allowed_dir)
            return resolved_path
        except ValueError:
            continue

    allowed_text = ", ".join(str(path) for path in allowed_dirs)
    raise UploadError(
        "Image path is outside allowed upload directories",
        details={
            "path": str(resolved_path),
            "allowed_dirs": allowed_text,
        },
    )


async def get_editor_frame(page: Page) -> Frame | Page:
    """글쓰기 에디터 컨텍스트를 가져옵니다.

    Args:
        page: Playwright Page 객체

    Returns:
        에디터 iframe의 Frame 객체. iframe이 없는 스마트에디터 화면에서는 Page 객체.

    Raises:
        ElementNotFoundError: iframe을 찾을 수 없는 경우
        TimeoutError: iframe 로딩 타임아웃
    """
    try:
        # iframe 찾기
        iframe_selectors = ["iframe#mainFrame", "iframe[name='mainFrame']"]

        for selector in iframe_selectors:
            try:
                iframe_element = await page.wait_for_selector(selector, timeout=5000)
                if iframe_element:
                    main_frame = await iframe_element.content_frame()
                    if main_frame:
                        logger.info(f"Editor iframe found: {selector}")
                        return main_frame
            except PlaywrightTimeoutError:
                continue

        editor_selectors = [".se-canvas", "article.se-components-wrap", ".se-component"]
        for selector in editor_selectors:
            try:
                if await page.locator(selector).count() > 0:
                    logger.info(f"Editor found on main page: {selector}")
                    return page
            except Exception:
                continue

        raise ElementNotFoundError(
            "Editor iframe not found",
            details={"selectors": iframe_selectors + editor_selectors}
        )

    except PlaywrightTimeoutError as e:
        raise TimeoutError(
            "Timeout while waiting for editor iframe",
            details={"error": str(e)}
        )


async def click_image_button(frame: Frame) -> None:
    """이미지 업로드 버튼을 클릭합니다.

    Args:
        frame: 에디터 iframe

    Raises:
        ElementNotFoundError: 이미지 버튼을 찾을 수 없는 경우
    """
    for selector in IMAGE_BUTTON_SELECTORS:
        try:
            locator_group = frame.locator(selector)
            count = await locator_group.count()
            for index in range(min(count, 10)):
                button = locator_group.nth(index)
                try:
                    if not await button.is_visible():
                        continue
                except Exception:
                    continue
                await button.click()
                logger.info("Image button clicked: %s[%s]", selector, index)
                await _action_pause()
                return
        except Exception as e:
            logger.debug(f"Failed to click {selector}: {e}")
            continue

    raise ElementNotFoundError(
        "Image button not found",
        details={"selectors": IMAGE_BUTTON_SELECTORS}
    )


async def find_file_input(frame: Frame, timeout: int = 5000):
    """이미지 업로드용 file input을 찾습니다."""
    deadline = asyncio.get_running_loop().time() + (timeout / 1000)

    while asyncio.get_running_loop().time() < deadline:
        for selector in FILE_INPUT_SELECTORS:
            try:
                locator = frame.locator(selector)
                count = await locator.count()
                if count > 0:
                    candidate = locator.nth(count - 1)
                    await candidate.wait_for(state="attached", timeout=500)
                    return candidate
            except Exception:
                continue
        await _action_pause(0.35)

    raise ElementNotFoundError(
        "File input not found after clicking image button",
        details={"selectors": FILE_INPUT_SELECTORS},
    )


async def wait_for_upload_complete(
    frame: Frame,
    timeout: int = 10000,
    initial_count: int = 0,
) -> bool:
    """이미지 업로드가 완료될 때까지 대기합니다.

    Args:
        frame: 에디터 iframe
        timeout: 타임아웃 (밀리초)
        initial_count: 업로드 전 이미지 개수

    Returns:
        업로드 성공 여부

    Raises:
        TimeoutError: 업로드 타임아웃
    """
    try:
        # 이미지가 에디터에 삽입될 때까지 대기
        for selector in UPLOADED_IMAGE_SELECTORS:
            try:
                # 새로운 이미지가 추가되었는지 확인
                current_count = await frame.locator(selector).count()
                if current_count > initial_count:
                    logger.info(f"Image uploaded successfully: {selector}")
                    return True

                # 이미지가 나타날 때까지 대기
                await frame.wait_for_selector(
                    selector,
                    state="visible",
                    timeout=timeout,
                )
                logger.info(f"Image element appeared: {selector}")
                return True

            except PlaywrightTimeoutError:
                continue

        raise TimeoutError(
            "Upload completion timeout",
            details={
                "timeout": timeout,
                "selectors": UPLOADED_IMAGE_SELECTORS,
            }
        )

    except Exception as e:
        logger.error(f"Error while waiting for upload: {e}")
        raise


def validate_upload_image_file(
    image_path: Union[str, Path],
    allow_unrestricted_path: bool = False,
) -> Path:
    """업로드 가능한 이미지 파일인지 검증하고 절대 경로를 반환합니다."""
    image_path = Path(image_path)
    if not allow_unrestricted_path:
        image_path = validate_image_path_allowed(image_path)
    else:
        image_path = image_path.expanduser().resolve()

    if not image_path.exists():
        raise UploadError(
            f"Image file not found: {image_path}",
            details={"path": str(image_path)}
        )

    file_size = image_path.stat().st_size
    if file_size > 10 * 1024 * 1024:
        raise UploadError(
            f"Image file too large: {file_size / 1024 / 1024:.2f}MB (max 10MB)",
            details={"path": str(image_path), "size": file_size}
        )

    if image_path.suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
        raise UploadError(
            f"Unsupported image format: {image_path.suffix}",
            details={"path": str(image_path), "format": image_path.suffix}
        )

    return image_path


@retry_on_error
async def upload_image(
    page: Page,
    image_path: Union[str, Path],
    wait_for_complete: bool = True,
    allow_unrestricted_path: bool = False,
) -> dict:
    """단일 이미지를 업로드합니다.

    Args:
        page: Playwright Page 객체
        image_path: 이미지 파일 경로
        wait_for_complete: 업로드 완료까지 대기 여부

    Returns:
        업로드 결과 딕셔너리
        - success: 성공 여부
        - file: 업로드한 파일 경로
        - message: 결과 메시지

    Raises:
        UploadError: 이미지 업로드 실패
        ElementNotFoundError: 필요한 요소를 찾을 수 없는 경우
    """
    try:
        image_path = validate_upload_image_file(
            image_path,
            allow_unrestricted_path=allow_unrestricted_path,
        )

        logger.info(f"Uploading image: {image_path}")

        # 에디터 iframe 가져오기
        frame = await get_editor_frame(page)

        # 업로드 전 이미지 개수 확인
        initial_image_count = 0
        for selector in UPLOADED_IMAGE_SELECTORS:
            try:
                count = await frame.locator(selector).count()
                if count > initial_image_count:
                    initial_image_count = count
            except Exception:
                pass

        # 이미지 버튼 클릭 후 file input 찾기. SmartEditor는 반복 업로드 시
        # input을 늦게 붙이거나 id 없이 다시 만드는 경우가 있어 한 번 더 시도합니다.
        file_input = None
        for attempt in range(2):
            await click_image_button(frame)
            try:
                file_input = await find_file_input(frame, timeout=5000)
                break
            except ElementNotFoundError:
                if attempt == 1:
                    raise
                await _action_pause()

        # 파일 업로드
        await file_input.set_input_files(str(image_path.absolute()))
        await _action_pause()
        logger.info(f"File selected: {image_path}")

        # 업로드 완료 대기
        if wait_for_complete:
            await wait_for_upload_complete(
                frame,
                timeout=10000,
                initial_count=initial_image_count,
            )

        return {
            "success": True,
            "file": str(image_path),
            "message": f"Image uploaded successfully: {image_path.name}",
        }

    except (UploadError, ElementNotFoundError, TimeoutError):
        # 커스텀 에러는 그대로 전달
        raise

    except Exception as e:
        logger.error(f"Unexpected error during image upload: {e}", exc_info=True)
        raise UploadError(
            f"Failed to upload image: {str(e)}",
            details={"path": str(image_path), "error": str(e)}
        )


@retry_on_error
async def paste_image(
    page: Page,
    image_path: Union[str, Path],
    wait_for_complete: bool = True,
    allow_unrestricted_path: bool = False,
) -> dict:
    """현재 에디터 커서 위치에 클립보드 붙여넣기로 이미지를 삽입합니다."""
    image_path = validate_upload_image_file(
        image_path,
        allow_unrestricted_path=allow_unrestricted_path,
    )

    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    frame = await get_editor_frame(page)

    initial_image_count = 0
    for selector in UPLOADED_IMAGE_SELECTORS:
        try:
            count = await frame.locator(selector).count()
            if count > initial_image_count:
                initial_image_count = count
        except Exception:
            pass

    try:
        await page.context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://blog.naver.com",
        )
    except Exception as e:
        logger.debug(f"Clipboard permission grant failed (ignored): {e}")

    await page.evaluate(
        """
        async ({ imageB64, mimeType }) => {
            const binary = atob(imageB64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i += 1) {
                bytes[i] = binary.charCodeAt(i);
            }
            const blob = new Blob([bytes], { type: mimeType });
            await navigator.clipboard.write([
                new ClipboardItem({ [mimeType]: blob }),
            ]);
        }
        """,
        {"imageB64": image_b64, "mimeType": mime_type},
    )

    await page.keyboard.press("Meta+V")
    await _action_pause()

    if wait_for_complete:
        await wait_for_upload_complete(
            frame,
            timeout=15000,
            initial_count=initial_image_count,
        )

    return {
        "success": True,
        "file": str(image_path),
        "message": f"Image pasted successfully: {image_path.name}",
    }


def decode_base64_image(base64_string: str) -> tuple[bytes, str]:
    """Base64 인코딩된 이미지를 디코딩합니다.

    Args:
        base64_string: Base64 문자열 (data:image/png;base64,... 또는 순수 base64)

    Returns:
        (이미지 바이트, 파일 확장자) 튜플

    Raises:
        UploadError: 디코딩 실패
    """
    try:
        # data:image/... 형식 처리
        if base64_string.startswith("data:image/"):
            # data:image/png;base64,iVBORw0KG... 형식
            header, encoded = base64_string.split(",", 1)
            # image/png 추출
            mime_type = header.split(";")[0].split(":")[1]
            extension = "." + mime_type.split("/")[1]
        else:
            # 순수 base64 문자열
            encoded = base64_string
            extension = ".png"  # 기본값

        # 디코딩
        image_bytes = base64.b64decode(encoded)
        return image_bytes, extension

    except Exception as e:
        raise UploadError(
            f"Failed to decode base64 image: {str(e)}",
            details={"error": str(e)}
        )


@retry_on_error
async def upload_base64_image(
    page: Page,
    base64_string: str,
    filename: Optional[str] = None,
    wait_for_complete: bool = True,
) -> dict:
    """Base64 인코딩된 이미지를 업로드합니다.

    Args:
        page: Playwright Page 객체
        base64_string: Base64 인코딩된 이미지 문자열
        filename: 파일명 (선택, 미지정시 임시 파일명 사용)
        wait_for_complete: 업로드 완료까지 대기 여부

    Returns:
        업로드 결과 딕셔너리

    Raises:
        UploadError: 이미지 업로드 실패
    """
    temp_file = None
    try:
        # Base64 디코딩
        image_bytes, extension = decode_base64_image(base64_string)

        # 임시 파일 생성
        if filename is None:
            filename = f"image{extension}"

        with tempfile.NamedTemporaryFile(
            suffix=extension,
            delete=False,
        ) as temp_file:
            temp_file.write(image_bytes)
            temp_path = Path(temp_file.name)

        logger.info(f"Base64 image saved to temporary file: {temp_path}")

        # 일반 이미지 업로드 사용
        result = await upload_image(
            page,
            temp_path,
            wait_for_complete,
            allow_unrestricted_path=True,
        )

        # 결과 수정 (임시 파일 경로 대신 원래 파일명 사용)
        result["file"] = filename
        result["message"] = f"Base64 image uploaded successfully: {filename}"

        return result

    except (UploadError, ElementNotFoundError, TimeoutError):
        raise

    except Exception as e:
        logger.error(f"Unexpected error during base64 upload: {e}", exc_info=True)
        raise UploadError(
            f"Failed to upload base64 image: {str(e)}",
            details={"error": str(e)}
        )

    finally:
        # 임시 파일 삭제
        if temp_file and Path(temp_file.name).exists():
            try:
                Path(temp_file.name).unlink()
                logger.debug(f"Temporary file deleted: {temp_file.name}")
            except Exception as e:
                logger.warning(f"Failed to delete temporary file: {e}")


@retry_on_error
async def upload_images(
    page: Page,
    image_paths: List[Union[str, Path]],
) -> dict:
    """여러 이미지를 순차적으로 업로드합니다.

    Args:
        page: Playwright Page 객체
        image_paths: 이미지 파일 경로 리스트

    Returns:
        업로드 결과 딕셔너리
        - success: 전체 성공 여부
        - uploaded: 성공한 파일 리스트
        - failed: 실패한 파일 리스트
        - message: 결과 메시지

    Raises:
        UploadError: 모든 이미지 업로드 실패
    """
    if not image_paths:
        return {
            "success": True,
            "uploaded": [],
            "failed": [],
            "message": "No images to upload",
        }

    uploaded = []
    failed = []

    for image_path in image_paths:
        try:
            result = await upload_image(page, image_path, wait_for_complete=True)
            if result["success"]:
                uploaded.append(str(image_path))
                logger.info(f"✓ {Path(image_path).name}")
            else:
                failed.append(str(image_path))
                logger.warning(f"✗ {Path(image_path).name}")

            # 이미지 간 간격
            await _action_pause()

        except Exception as e:
            logger.error(f"Failed to upload {image_path}: {e}")
            failed.append(str(image_path))

    # 결과 정리
    success = len(uploaded) > 0 and len(failed) == 0

    if len(failed) == len(image_paths):
        raise UploadError(
            "All images failed to upload",
            details={"failed": failed}
        )

    return {
        "success": success,
        "uploaded": uploaded,
        "failed": failed,
        "message": f"Uploaded {len(uploaded)}/{len(image_paths)} images",
    }
