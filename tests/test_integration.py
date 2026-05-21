"""MCP 서버 통합 테스트."""

import asyncio
import os
import sys

sys.path.insert(0, "src")

from naver_blog_mcp.server import NaverBlogMCPServer
from naver_blog_mcp.mcp.tools import TOOLS_METADATA


def has_naver_credentials() -> bool:
    """실제 네이버 로그인 테스트 실행 가능 여부를 반환합니다."""
    return bool(os.getenv("NAVER_BLOG_ID") and os.getenv("NAVER_BLOG_PASSWORD"))


async def test_server_tools_registration():
    """서버의 Tool 등록 상태를 확인합니다."""
    print("=" * 60)
    print("MCP 서버 통합 테스트 시작")
    print("=" * 60)
    print()

    NaverBlogMCPServer()
    print("✅ 서버 인스턴스 생성 완료")
    print()

    # Tool 메타데이터 확인
    print("📋 등록된 Tool 메타데이터:")
    print("-" * 60)
    for tool_name, tool_meta in TOOLS_METADATA.items():
        print(f"\n🔧 {tool_name}")
        print(f"   설명: {tool_meta['description']}")
        required = tool_meta["inputSchema"].get("required", [])
        properties = tool_meta["inputSchema"].get("properties", {})
        if required:
            print(f"   필수 파라미터: {', '.join(required)}")
        if properties:
            optional = [k for k in properties.keys() if k not in required]
            if optional:
                print(f"   선택 파라미터: {', '.join(optional)}")
    print()
    print("-" * 60)

    # Tool 개수 확인
    tool_count = len(TOOLS_METADATA)
    print(f"\n✅ 총 {tool_count}개의 Tool이 등록되었습니다")
    print()

    # 예상 Tool 확인
    expected_tools = [
        "naver_blog_create_post",
        "naver_blog_list_categories",
    ]

    missing_tools = [t for t in expected_tools if t not in TOOLS_METADATA]
    if missing_tools:
        print(f"❌ 누락된 Tool: {', '.join(missing_tools)}")
        return False
    else:
        print("✅ 모든 예상 Tool이 등록되었습니다")
        print()

    return True


async def test_server_initialization():
    """서버 초기화 및 브라우저 연결을 테스트합니다."""
    print("=" * 60)
    print("서버 초기화 테스트")
    print("=" * 60)
    print()

    server = NaverBlogMCPServer()
    print("✅ 서버 인스턴스 생성 완료")

    if not has_naver_credentials():
        print("⏭️ NAVER_BLOG_ID/PASSWORD가 없어 실제 브라우저 초기화 테스트를 건너뜁니다.")
        return True

    try:
        # 브라우저 초기화
        await server.initialize()
        print("✅ 브라우저 및 세션 초기화 완료")

        # 페이지 가져오기
        page = await server.get_page()
        print("✅ 페이지 생성 완료")

        # 간단한 네비게이션 테스트
        await page.goto("https://blog.naver.com")
        print(f"✅ 네이버 블로그 접속 완료: {page.url}")

        print()
        print("✅ 서버 초기화 테스트 통과!")
        return True

    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 리소스 정리
        await server.cleanup()
        print("✅ 리소스 정리 완료")
        print()


async def test_tool_schema_validation():
    """Tool 스키마 유효성을 검증합니다."""
    print("=" * 60)
    print("Tool 스키마 검증")
    print("=" * 60)
    print()

    all_valid = True

    for tool_name, tool_meta in TOOLS_METADATA.items():
        print(f"🔍 {tool_name} 검증 중...")

        # 필수 필드 확인
        required_fields = ["name", "description", "inputSchema"]
        for field in required_fields:
            if field not in tool_meta:
                print(f"   ❌ 누락된 필드: {field}")
                all_valid = False
            else:
                print(f"   ✅ {field}: OK")

        # inputSchema 구조 확인
        schema = tool_meta.get("inputSchema", {})
        if "type" not in schema:
            print("   ❌ inputSchema에 type 필드 누락")
            all_valid = False
        elif schema["type"] != "object":
            print(f"   ❌ inputSchema type이 'object'가 아님: {schema['type']}")
            all_valid = False
        else:
            print("   ✅ inputSchema type: object")

        if "properties" not in schema:
            print("   ❌ inputSchema에 properties 필드 누락")
            all_valid = False
        else:
            print(f"   ✅ properties: {len(schema['properties'])}개 파라미터")

        print()

    if all_valid:
        print("✅ 모든 Tool 스키마가 유효합니다!")
    else:
        print("❌ 일부 Tool 스키마가 유효하지 않습니다.")

    print()
    return all_valid


async def main():
    """전체 통합 테스트 실행."""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "MCP 서버 통합 테스트" + " " * 23 + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    results = {}

    # 1. Tool 등록 테스트
    results["tool_registration"] = await test_server_tools_registration()

    # 2. Tool 스키마 검증
    results["schema_validation"] = await test_tool_schema_validation()

    # 3. 서버 초기화 테스트
    results["server_initialization"] = await test_server_initialization()

    # 최종 결과
    print("=" * 60)
    print("최종 결과")
    print("=" * 60)
    print()

    for test_name, result in results.items():
        status = "✅ 통과" if result else "❌ 실패"
        print(f"{test_name:30s}: {status}")

    print()

    all_passed = all(results.values())
    if all_passed:
        print("🎉 모든 통합 테스트 통과!")
        print()
        return 0
    else:
        print("❌ 일부 테스트 실패")
        print()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
