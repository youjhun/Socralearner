#!/usr/bin/env python3
"""템플릿 동기화 실행부 — 내려받고, 적용하고, 알린다.

유지훈(2026-08-03): *"진짜 지침말고는 바로 패치되게끔"*.

그래서 로직을 워크플로 YAML에서 여기로 내렸다. Actions의 기본 토큰은
`.github/workflows/` 아래를 수정할 수 없어서, 워크플로 안에 로직이 있으면 그 로직을
고칠 때마다 **자동 배포가 끊긴다**. 워크플로는 얇은 껍데기(체크아웃 + 이 스크립트 호출)만
남기고, 앞으로 고치는 것은 전부 `scripts/`에서 고친다 — scripts는 자유롭게 동기화된다.

남는 수동 작업은 **GPT 지침 재붙여넣기 하나**다. ChatGPT Custom GPT의 Instructions는
API로 접근할 수 없어 어떤 방법으로도 자동화되지 않는다. 그래서 그것만 Issue로 알린다.

환경변수:
  GH_TOKEN        — 알림 Issue 생성용(그리고 PAT이면 워크플로 파일 푸시까지 가능)
  HAS_PAT         — "true"면 워크플로 파일도 밀 수 있다
  SYNC_MODE       — auto(기본) | pr
  TEMPLATE_REPO   — 기본 youjhun/Socralearner
"""
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_github as gh  # noqa: E402
import sync_from_template as sync  # noqa: E402

TEMPLATE = os.environ.get("TEMPLATE_REPO", "youjhun/Socralearner")
HAS_PAT = os.environ.get("HAS_PAT", "").lower() == "true"
MODE = os.environ.get("SYNC_MODE", "auto").strip() or "auto"

# CHANGELOG에서 ⚠️ 가 붙은 항목 = 머지만으로 끝나지 않는 것(= GPT 지침 재붙여넣기).
WARN_RE = re.compile(r"^##\s*⚠️", re.M)


def download_template(dest):
    url = f"https://codeload.github.com/{TEMPLATE}/tar.gz/refs/heads/main"
    print(f"템플릿 내려받기: {url}")
    with urllib.request.urlopen(url, timeout=60) as r, \
            tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp.write(r.read())
        path = tmp.name
    with tarfile.open(path) as tar:
        root = os.path.commonprefix([m.name for m in tar.getmembers() if m.name]).rstrip("/")
        tar.extractall(dest)
    os.unlink(path)
    extracted = os.path.join(dest, root)
    print(f"받은 파일 {sum(len(f) for _, _, f in os.walk(extracted))}개")
    return extracted


def changelog_notes(src):
    """최근 항목 몇 개와, 사람 손이 필요한지 여부."""
    path = os.path.join(src, "CHANGELOG.md")
    if not os.path.exists(path):
        return "", False
    with open(path, encoding="utf-8") as f:
        text = f.read()
    body = text[text.index("## "):] if "## " in text else text
    head = "\n".join(body.splitlines()[:60])
    return head, bool(WARN_RE.search(head))


def notify(summary, skipped_workflows, notes, needs_hand, mode):
    lines = [
        f"템플릿 업데이트를 **적용했습니다** — {summary}"
        if mode == "auto" else
        f"템플릿 업데이트로 **PR을 열었습니다** — {summary}",
        "",
        "내 기록(`daily/` · `materials/` · `papers/` · `mastery.md` · `STATUS.md` · "
        "`drills.md` · `concepts.json` · `topics.yaml` · `README.md`)은 건드리지 않았습니다.",
        "",
    ]

    if needs_hand:
        lines += [
            "## ⚠️ 이것만 직접 해 주세요 — GPT 지침",
            "",
            "러너 지침이 바뀌었습니다. ChatGPT의 Custom GPT 설정은 API로 바꿀 수 없어서",
            "**이 한 가지만** 자동이 안 됩니다.",
            "",
            "1. ChatGPT → 내 GPT → **편집**",
            "2. **지침(Instructions)** 을 비우고",
            f"   [`runner/instructions.md`](https://github.com/{TEMPLATE}/blob/main/runner/instructions.md)",
            "   의 회색 박스 전체를 다시 붙여넣기",
            "3. 토익 트랙이면 `presets/toeic/runner-addendum.md` 도 이어서",
            "",
            "안 하면 이미 생긴 것은 정리돼도 다음 세션부터 예전 방식으로 돌아갑니다.",
            "",
        ]

    if skipped_workflows:
        lines += [
            "## 워크플로 파일 (드문 경우)",
            "",
            "GitHub 기본 토큰은 `.github/workflows/` 를 수정할 수 없어 아래는 건너뛰었습니다:",
            "",
            *[f"- [`{f}`](https://github.com/{TEMPLATE}/blob/main/{f})" for f in skipped_workflows],
            "",
            "이 파일들은 **얇은 껍데기**라 거의 바뀌지 않습니다(로직은 `scripts/`에 있고 그건",
            "자동으로 갱신됩니다). 위 링크에서 복사해 덮어쓰면 됩니다.",
            "",
        ]

    lines += ["## 무엇이 바뀌었나", "", notes, "",
              "<sub>매주 월요일 자동 확인. PR로 받으려면 저장소 변수 `TEMPLATE_SYNC_MODE=pr`. "
              "그만 받으려면 Actions 탭에서 이 워크플로를 비활성화하세요.</sub>"]

    gh.create_issue(
        f"[템플릿] {os.environ.get('SYNC_DATE', '')} 업데이트 — {summary}".replace("  ", " "),
        "\n".join(lines),
    )


def main():
    if not os.path.exists("scripts/sync_from_template.py"):
        print("학습 저장소 루트에서 실행해야 한다", file=sys.stderr)
        return 2

    tmp = tempfile.mkdtemp()
    src = download_template(tmp)

    added, changed = sync.plan(src, ".")
    workflows = [r for r in added + changed if sync.is_workflow(r)]

    # PAT이 없으면 워크플로는 어차피 푸시가 거부된다 — 손대지 않는다.
    skipped = [] if HAS_PAT else workflows
    apply_list = [r for r in added + changed if HAS_PAT or not sync.is_workflow(r)]

    if not apply_list and not skipped:
        print("이미 최신이다 — 할 일 없음")
        return 0

    for r in apply_list:
        print(f"  ~ {r}")
    sync.apply(src, ".", apply_list)

    summary = f"{len(apply_list)}개 파일"
    notes, needs_hand = changelog_notes(src)

    if not gh.has_changes():
        print("적용했으나 실제 변경 없음 — 알림만 보낸다")
        if skipped:
            notify(summary, skipped, notes, needs_hand, MODE)
        return 0

    if MODE == "pr":
        branch = f"template-sync/{os.environ.get('SYNC_DATE', 'update')}"
        gh.git_identity()
        gh.run("git", "checkout", "-B", branch)
        gh.run("git", "add", "-A")
        gh.run("git", "commit", "-m", f"템플릿 업데이트 — {summary}")
        gh.run("git", "push", "-f", "origin", branch)
        try:
            gh.api("POST", f"/repos/{gh.repo_slug()}/pulls", {
                "title": f"템플릿 업데이트 — {summary}",
                "head": branch,
                "base": os.environ.get("GITHUB_REF_NAME", "main"),
                "body": "템플릿 업데이트입니다. 바뀐 것은 CHANGELOG.md를 보세요.\n\n"
                        "내 기록은 건드리지 않았습니다.",
            })
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  PR 생성 실패: {e}", file=sys.stderr)
    else:
        gh.commit_and_push(f"템플릿 업데이트 — {summary}")

    notify(summary, skipped, notes, needs_hand, MODE)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"명령 실패: {e}", file=sys.stderr)
        sys.exit(1)
