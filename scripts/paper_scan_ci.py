#!/usr/bin/env python3
"""논문 수집 실행부 — 수집하고, 커밋하고, 새 게 있으면 알린다.

로직이 워크플로 YAML이 아니라 여기 있는 이유: 워크플로 파일은 Actions 기본 토큰으로
수정할 수 없어 **자동 배포가 안 된다.** 고칠 가능성이 있는 것은 전부 scripts/에 둔다
(2026-08-03, 유지훈: *"진짜 지침말고는 바로 패치되게끔"*).

실행: python3 scripts/paper_scan_ci.py   (CI가 이렇게 부른다)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_github as gh  # noqa: E402
import scan_papers  # noqa: E402


def main():
    # 수집 자체. 모든 주제의 조회가 실패하면 0이 아닌 값을 돌려준다.
    code = scan_papers.main()
    if code != 0:
        print("수집 실패 — 커밋하지 않는다", file=sys.stderr)
        return code

    if not gh.has_changes("papers"):
        print("변경 없음")
        return 0

    inbox = ""
    if os.path.exists(scan_papers.INBOX_PATH):
        with open(scan_papers.INBOX_PATH, encoding="utf-8") as f:
            inbox = f.read()

    # frontmatter는 기계용이다 — 사람이 읽는 알림에서는 걷어낸다.
    if inbox.startswith("---"):
        parts = inbox.split("---", 2)
        inbox = parts[2] if len(parts) > 2 else inbox

    date = os.environ.get("SYNC_DATE") or scan_papers.today_iso()
    gh.commit_and_push(f"papers: 주간 논문 수집 ({date})", paths=("papers",))

    # 새로 걸린 게 있을 때만 알린다 — 매주 "0편" 알림은 소음이다.
    total = 0
    for line in inbox.splitlines():
        if line.startswith("> 새 논문 **"):
            try:
                total = int(line.split("**")[1].replace("편", ""))
            except (IndexError, ValueError):
                total = 0
            break

    if total > 0:
        gh.create_issue(
            f"[논문] {date} 새 논문 {total}편",
            inbox.strip()
            + "\n\n---\n다 읽지 마세요. 제목·초록만 훑고 **한 편만 골라** 세션에서 깊게 보면 됩니다.\n"
            + '학습 러너에게: *"이번 주 새 논문 같이 보자"*',
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
