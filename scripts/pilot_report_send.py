#!/usr/bin/env python3
"""파일럿 롤업을 중앙 저장소로 보낸다 — 비공개 저장소용 전송 경로.

왜 이 경로가 필요한가 (2026-08-03):
파일럿 참가자들이 학습 저장소를 비공개로 바꾸고 싶어 한다. 비공개가 되는 순간 유지훈이
공개 API로 읽는 pull 경로가 끊긴다. 그렇다고 collaborator로 초대받으면 그 사람의 학습
원문을 전부 읽게 되는데, 비공개를 원한 이유가 바로 그것이라 답이 될 수 없다.

그래서 **저장소가 스스로 익명 수치만 밀어 올린다.** 원문은 저장소 밖으로 한 번도 나가지
않고, 유지훈은 수치만 받는다.

## 이 스크립트가 지키는 것

- **보내는 것은 `pilot_rollup.py`가 만든 JSON 그대로다.** 여기서 내용을 더하지 않는다.
  더할 수 있게 만들면 언젠가 "이건 좀 더 있으면 좋겠는데"가 들어오고, 그때 계약이 깨진다.
- 참가자 ID가 익명 형식(P01)이 아니면 **보내지 않고 실패한다.**
- 토큰이 없으면 그냥 끝낸다(에러 아님) — 공개로 쓰는 동안은 이 경로가 필요 없다.

## 필요한 설정 (비공개로 바꿀 때만)

- 저장소 변수 `PILOT_CENTRAL_REPO` — 받는 저장소 (owner/name)
- 저장소 시크릿 `PILOT_REPORT_TOKEN` — **그 저장소의 Issues: write 하나만** 가진 토큰.
  유지훈이 만들어 나눠 준다(참가자가 직접 발급하지 않는다 — 세팅비를 늘리지 않는다).
  이 토큰으로 할 수 있는 최악은 중앙 저장소에 Issue를 여는 것이고, 폐기하면 끝난다.

의존성 없음 — 표준 라이브러리만.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
PARTICIPANT_RE = re.compile(r"^P\d{2,3}$")

# 롤업 밖의 키가 섞여 들어오면 보내지 않는다. 계약이 조용히 넓어지는 것을 막는 유일한 지점.
ALLOWED_KEYS = {
    "participant", "week", "generated_on", "schema",
    "sessions_week", "sessions_total", "session_dates_week",
    "first_session", "last_session", "returned", "streak_days",
    "session_gap_median_days",
    "transfer", "retention",
    "artifacts_total", "first_artifact", "open_blockers",
    "concepts_total", "explained", "memorized", "unlearned",
    "prereq_edges", "domains", "with_evidence",
}


def send(central, token, data):
    title = f"[롤업] {data['week']} {data['participant']}"
    body = (
        f"참가자 `{data['participant']}` · 주차 `{data['week']}`\n\n"
        "```json\n" + json.dumps(data, ensure_ascii=False, indent=1) + "\n```\n\n"
        "> 이 저장소가 자동으로 올린 익명 수치다. 학습 노트 원문·개념 이름은 포함되지 않는다.\n"
        "> 계약: `scripts/pilot_rollup.py` · 강제: `scripts/test_pilot_rollup.py`\n"
    )
    req = urllib.request.Request(
        f"{API}/repos/{central}/issues",
        data=json.dumps({"title": title, "body": body}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "socralearner-pilot-report",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def main():
    ap = argparse.ArgumentParser(description="파일럿 롤업 전송 (비공개 저장소용)")
    ap.add_argument("--rollup", default="pilot/rollup.json")
    args = ap.parse_args()

    token = os.environ.get("TOKEN") or os.environ.get("PILOT_REPORT_TOKEN") or ""
    central = (os.environ.get("CENTRAL") or os.environ.get("PILOT_CENTRAL_REPO") or "").strip()

    if not token:
        print("PILOT_REPORT_TOKEN이 없다 — 전송 경로를 건너뛴다(공개 저장소면 정상).")
        return 0
    if not re.match(r"^[\w.-]+/[\w.-]+$", central):
        raise SystemExit(
            f"PILOT_CENTRAL_REPO가 owner/name 형식이 아니다: {central!r} — 전송하지 않는다."
        )

    with open(args.rollup, encoding="utf-8") as f:
        data = json.load(f)

    if not PARTICIPANT_RE.match(str(data.get("participant") or "")):
        raise SystemExit(
            f"참가자 ID가 익명 형식이 아니다: {data.get('participant')!r} — 전송하지 않는다."
        )
    extra = set(data) - ALLOWED_KEYS
    if extra:
        raise SystemExit(
            "롤업에 계약 밖의 키가 있다 — 전송하지 않는다: " + ", ".join(sorted(extra))
        )

    try:
        issue = send(central, token, data)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"전송 실패 (HTTP {e.code}) — 토큰 권한과 중앙 저장소를 확인한다.")
    print(f"✅ {central} Issue #{issue.get('number')} 로 전송 — {data['week']} {data['participant']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
