"""본문/이미지 블록 분리 테스트."""

import sys

sys.path.insert(0, "src")

from naver_blog_mcp.automation.post_actions import (  # noqa: E402
    DRAFT_RESTORE_DISMISS_TEXTS,
    has_markdown_image_markers,
    is_existing_draft_prompt_text,
    replace_image_markers_with_placeholders,
    split_content_by_image_markers,
)


def test_split_content_by_image_markers_preserves_order():
    content = """첫 문단

![대표 이미지](../images/001.png)
이미지 설명: 대표 이미지

둘째 문단
![상세 이미지](../images/002.png)
끝"""

    assert has_markdown_image_markers(content)
    assert split_content_by_image_markers(content) == [
        ("text", "첫 문단\n\n"),
        ("image", "![대표 이미지](../images/001.png)"),
        ("text", "이미지 설명: 대표 이미지\n\n둘째 문단\n"),
        ("image", "![상세 이미지](../images/002.png)"),
        ("text", "끝"),
    ]


def test_split_content_without_images_returns_single_text_block():
    content = "이미지 없는 본문\n1. 첫째\n2. 둘째"

    assert not has_markdown_image_markers(content)
    assert split_content_by_image_markers(content) == [("text", content)]


def test_replace_image_markers_with_placeholders():
    content = "앞\n![one](1.png)\n중간\n![two](2.png)\n뒤"

    replaced, placeholders = replace_image_markers_with_placeholders(content)

    assert placeholders == ["[[NAVER_IMAGE_001]]", "[[NAVER_IMAGE_002]]"]
    assert replaced == "앞\n[[NAVER_IMAGE_001]]\n중간\n[[NAVER_IMAGE_002]]\n뒤"


def test_existing_draft_prompt_detection_is_specific():
    assert is_existing_draft_prompt_text(
        "임시저장글이 있습니다. 이어서 작성하시겠습니까?"
    )
    assert is_existing_draft_prompt_text(
        "작성 중인 글이 있습니다. 이어서 작성하시겠습니까?"
    )
    assert is_existing_draft_prompt_text("임시저장된 글이 있습니다. 불러오시겠습니까?")

    assert not is_existing_draft_prompt_text("작성 중인 글이 있습니다")
    assert not is_existing_draft_prompt_text("임시저장 버튼")
    assert not is_existing_draft_prompt_text("임시저장된 글 보기, 2개")
    assert not is_existing_draft_prompt_text("본문에 임시저장이라는 단어가 있습니다")


def test_draft_restore_dismiss_buttons_do_not_confirm_restore():
    assert "확인" not in DRAFT_RESTORE_DISMISS_TEXTS
    assert "불러오기" not in DRAFT_RESTORE_DISMISS_TEXTS
    assert "이어쓰기" not in DRAFT_RESTORE_DISMISS_TEXTS
