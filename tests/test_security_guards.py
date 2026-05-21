"""보안 회귀 방지 테스트."""

import pytest

from naver_blog_mcp.automation import post_actions
from naver_blog_mcp.automation.image_upload import validate_image_path_allowed
from naver_blog_mcp.config import config
from naver_blog_mcp.mcp.tools import TOOLS_METADATA, handle_create_post
from naver_blog_mcp.utils.exceptions import UploadError


def test_create_post_schema_does_not_expose_unsupported_fields():
    """미지원 카테고리/태그 필드는 MCP 스키마에 노출하지 않습니다."""
    properties = TOOLS_METADATA["naver_blog_create_post"]["inputSchema"]["properties"]

    assert "category" not in properties
    assert "tags" not in properties


@pytest.mark.asyncio
async def test_category_and_tags_are_rejected_before_browser_work():
    """구버전 클라이언트가 category/tags를 보내도 조용히 무시하지 않습니다."""
    result = await handle_create_post(
        page=None,
        title="제목",
        content="본문",
        category="미지원",
    )

    assert result["success"] is False
    assert "아직 지원하지 않습니다" in result["message"]


@pytest.mark.asyncio
async def test_publish_false_uses_draft_path(monkeypatch):
    """publish=false는 공개 발행 대신 임시저장 경로만 사용합니다."""
    calls = {"publish": 0, "draft": 0}
    order = []

    async def fake_navigate(*args, **kwargs):
        return None

    async def fake_fill_title(*args, **kwargs):
        return None

    async def fake_fill_content(*args, **kwargs):
        order.append("content")
        return None

    async def fake_upload_images(page, images):
        order.append("images")
        assert images == ["blog-images/test.png"]
        return {"uploaded": images, "failed": []}

    async def fake_publish(*args, **kwargs):
        calls["publish"] += 1
        return {"success": True, "message": "published", "post_url": "url"}

    async def fake_save_draft(*args, **kwargs):
        calls["draft"] += 1
        order.append("draft")
        return {"success": True, "message": "draft", "post_url": None}

    monkeypatch.setattr(post_actions, "navigate_to_post_write_page", fake_navigate)
    monkeypatch.setattr(post_actions, "fill_post_title", fake_fill_title)
    monkeypatch.setattr(post_actions, "fill_post_content", fake_fill_content)
    monkeypatch.setattr(post_actions, "upload_images", fake_upload_images)
    monkeypatch.setattr(post_actions, "publish_post", fake_publish)
    monkeypatch.setattr(post_actions, "save_draft", fake_save_draft)

    result = await post_actions.create_blog_post(
        page=object(),
        title="임시저장",
        content="본문",
        publish=False,
        images=["blog-images/test.png"],
    )

    assert result["success"] is True
    assert result["title"] == "임시저장"
    assert result["images_uploaded"] == 1
    assert calls == {"publish": 0, "draft": 1}
    assert order == ["content", "images", "draft"]


def test_image_path_must_be_inside_allowed_directory(tmp_path, monkeypatch):
    """임의 로컬 파일 경로 업로드를 차단합니다."""
    allowed_dir = tmp_path / "blog-images"
    allowed_dir.mkdir()
    allowed_image = allowed_dir / "ok.png"
    outside_image = tmp_path / "outside.png"

    monkeypatch.setattr(config, "IMAGE_UPLOAD_ALLOWED_DIRS", [str(allowed_dir)])

    assert validate_image_path_allowed(allowed_image) == allowed_image.resolve()

    with pytest.raises(UploadError):
        validate_image_path_allowed(outside_image)
