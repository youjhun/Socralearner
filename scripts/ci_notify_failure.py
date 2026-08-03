#!/usr/bin/env python3
"""실패 알림 — 어떤 워크플로가 왜 죽었는지 Issue로 남긴다.

조용한 실패가 제일 나쁘다. 자동화가 멈춘 줄 모르면 "왜 안 되지"만 남고 단서가 없다.

이것도 워크플로 YAML이 아니라 여기 있는 이유는 같다 — 워크플로 파일은 자동 배포되지
않으므로, 고칠 가능성이 있는 것은 전부 scripts/에 둔다.

실행: python3 scripts/ci_notify_failure.py "<작업 이름>"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_github as gh  # noqa: E402

HINTS = {
    "템플릿 업데이트": (
        "- 기본 브랜치가 보호돼 있어 봇이 밀 수 없음 → 보호 규칙에서 Actions를 허용하거나\n"
        "  저장소 변수 `TEMPLATE_SYNC_MODE=pr` 로 두세요.\n"
        "- PR 모드인데 **Settings → Actions → General →**\n"
        "  **\"Allow GitHub Actions to create and approve pull requests\"** 가 꺼져 있음.\n"
        "- 템플릿 저장소를 일시적으로 못 받았음(잠시 뒤 다시 시도됩니다).\n"
    ),
    "논문 수집": (
        "- `topics.yaml` 문법 오류 — 들여쓰기와 `topics:` 아래 목록 형식을 확인하세요.\n"
        "- 외부 API 일시 장애 또는 요청 한도. `topics.yaml`에 `mailto:` 를 넣으면\n"
        "  여유 있는 대기열로 갑니다.\n"
    ),
}


def main():
    job = sys.argv[1] if len(sys.argv) > 1 else "자동화"
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = gh.repo_slug()
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    url = f"{server}/{repo}/actions/runs/{run_id}"
    today = os.environ.get("SYNC_DATE") or ""

    hint = HINTS.get(job) or "- 실행 로그를 확인하세요.\n"
    body = (
        f"**{job}**이 실패했습니다 — [실행 로그]({url})\n\n"
        f"흔한 원인:\n{hint}\n"
        "고친 뒤 Actions 탭에서 해당 워크플로를 **Run workflow** 로 다시 돌리면 됩니다."
    )
    gh.create_issue(f"[자동화] {job} 실패 {today}".strip(), body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
