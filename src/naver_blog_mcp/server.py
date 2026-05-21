"""네이버 블로그 MCP 서버.

이 모듈은 Codex 등 MCP 클라이언트가 네이버 블로그와 상호작용할 수 있도록
MCP (Model Context Protocol) 서버를 제공합니다.
"""

import asyncio
import json
import logging
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .config import get_browser_config, config
from .services.session_manager import SessionManager
from .mcp.tools import (
    TOOLS_METADATA,
    handle_create_post,
    # handle_delete_post,  # 비활성화
    handle_list_categories,
)
from .utils.trace_manager import trace_manager

# 로깅 설정
logging.basicConfig(level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)
logger.setLevel(config.LOG_LEVEL)


class NaverBlogMCPServer:
    """네이버 블로그 MCP 서버 클래스."""

    def __init__(self):
        """서버 초기화."""
        self.server = Server("naver-blog")
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.session_manager: Optional[SessionManager] = None
        self._initialize_lock = asyncio.Lock()

        # Tool 등록
        self._register_tools()

    def _register_tools(self):
        """MCP Tool들을 등록합니다."""
        logger.info("Registering MCP tools...")

        # naver_blog_create_post Tool 등록
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[dict]:
            """Tool 호출 핸들러."""
            arguments = arguments or {}
            logger.info("Tool called: %s with keys: %s", name, sorted(arguments.keys()))

            try:
                if name not in TOOLS_METADATA:
                    return [
                        {
                            "type": "text",
                            "text": f"알 수 없는 Tool: {name}",
                        }
                    ]

                # 페이지 가져오기. Codex가 서버 시작 시점에 도구 목록만 조회할 수
                # 있도록 브라우저와 네이버 로그인은 실제 도구 호출 시점까지 미룹니다.
                page = await self.get_page()

                # Trace 시작
                if self.context and config.SAVE_DEBUG_ARTIFACTS:
                    await trace_manager.start_trace(self.context, name=name)

                # Tool별 핸들러 호출
                if name == "naver_blog_create_post":
                    result = await handle_create_post(
                        page=page,
                        title=arguments["title"],
                        content=arguments["content"],
                        category=arguments.get("category"),
                        tags=arguments.get("tags"),
                        images=arguments.get("images"),
                        publish=arguments.get("publish", True),
                    )
                # elif name == "naver_blog_delete_post":
                #     result = await handle_delete_post(
                #         page=page, post_url=arguments["post_url"]
                #     )
                elif name == "naver_blog_list_categories":
                    result = await handle_list_categories(page=page)

                # Trace 저장 (성공)
                if self.context and config.SAVE_DEBUG_ARTIFACTS:
                    await trace_manager.stop_trace(self.context, success=True)

                return [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2),
                    }
                ]

            except Exception as e:
                logger.error(f"Tool execution error: {e}", exc_info=True)

                # Trace 저장 (실패)
                if self.context and config.SAVE_DEBUG_ARTIFACTS:
                    await trace_manager.stop_trace(self.context, success=False)

                return [
                    {
                        "type": "text",
                        "text": f"오류 발생: {str(e)}",
                    }
                ]

        # list_tools 핸들러 등록
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """사용 가능한 Tool 목록을 반환합니다."""
            # dict를 Tool 객체로 변환
            return [
                Tool(
                    name=tool_data["name"],
                    description=tool_data["description"],
                    inputSchema=tool_data["inputSchema"],
                )
                for tool_data in TOOLS_METADATA.values()
            ]

        logger.info(f"Registered {len(TOOLS_METADATA)} tools")

    async def initialize(self):
        """브라우저 및 세션 초기화.

        MCP 서버 프로세스는 도구 목록 노출을 위해 빠르게 떠야 하므로, 이 초기화는
        실제 네이버 도구가 호출될 때만 실행됩니다.
        """
        async with self._initialize_lock:
            if self.context:
                return

            logger.info("Initializing Naver Blog MCP Server...")

            try:
                # 설정 검증은 list_tools가 아니라 실제 도구 호출 시점에 수행합니다.
                config.validate()

                # 세션 관리자 초기화
                self.session_manager = SessionManager(
                    user_id=config.NAVER_BLOG_ID,
                    password=config.NAVER_BLOG_PASSWORD,
                    storage_path=config.SESSION_STORAGE_PATH,
                    session_validity_hours=config.SESSION_VALIDITY_HOURS,
                )

                # Playwright 시작
                self.playwright = await async_playwright().start()

                # 브라우저 설정 가져오기
                browser_config = get_browser_config()

                # 브라우저 실행
                self.browser = await self.playwright.chromium.launch(**browser_config)
                logger.info(
                    f"Browser launched (headless={browser_config.get('headless', True)})"
                )

                # 세션 복원 또는 새 컨텍스트 생성
                self.context = await self.session_manager.get_or_create_session(
                    self.browser,
                    headless=config.HEADLESS,
                )
                logger.info("Browser context initialized")
            except Exception:
                await self.cleanup()
                raise

    async def cleanup(self):
        """리소스 정리."""
        logger.info("Cleaning up resources...")

        if self.context:
            await self.context.close()
            self.context = None
            logger.info("Browser context closed")

        if self.browser:
            await self.browser.close()
            self.browser = None
            logger.info("Browser closed")

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
            logger.info("Playwright stopped")

        self.session_manager = None

    async def get_page(self) -> Page:
        """새 페이지를 생성하거나 기존 페이지를 반환합니다.

        Returns:
            Playwright Page 객체

        Raises:
            RuntimeError: 브라우저 컨텍스트가 초기화되지 않은 경우
        """
        if not self.context:
            await self.initialize()

        if not self.context:
            raise RuntimeError("Browser context initialization failed.")

        # 기존 페이지가 있으면 재사용, 없으면 새로 생성
        pages = self.context.pages
        if pages:
            return pages[0]
        else:
            return await self.context.new_page()

    async def run(self):
        """MCP 서버 실행."""
        try:
            # stdio를 통해 MCP 서버 실행
            async with stdio_server() as (read_stream, write_stream):
                logger.info("MCP Server started successfully")
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            raise
        finally:
            # 리소스 정리
            await self.cleanup()


async def async_main():
    """비동기 서버 엔트리포인트."""
    server = NaverBlogMCPServer()
    await server.run()


def main():
    """동기 서버 엔트리포인트 (CLI 진입점)."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
