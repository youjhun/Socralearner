#!/usr/bin/env python3
"""템플릿 동기화 — 내 학습 저장소에 템플릿의 **엔진 부분**만 가져온다.

왜 필요한가 (2026-08-03):
`Use this template`로 만든 저장소는 그 시점의 **복사본**이라, 템플릿을 고쳐도 따라오지
않는다. 그래서 고칠 때마다 쓰는 사람들에게 "이 파일 4개를 복사하세요"라고 전해야 했다.
한 번이면 몰라도 계속 생기고, 그러면 아무도 안 한다 — 결국 각자 다른 버전을 쓰게 되고
버그 보고가 재현되지 않는다.

이 스크립트는 템플릿의 현재 내용을 받아 **엔진 경로만** 덮어쓰고, 무엇이 바뀌었는지
보고한다. 실제 커밋·PR은 워크플로가 한다(이 스크립트는 파일만 만진다).

## 무엇을 가져오고 무엇을 안 가져오나

가져온다 — 내가 쓴 적 없는 것, 템플릿이 주인인 것:
  scripts/ · runner/ · presets/ · templates/ · .github/workflows/ · 문서 몇 개

**절대 안 가져온다 — 내 기록과 내 설정:**
  daily/ · materials/ · papers/ · mastery.md · mastery/ · STATUS.md · drills.md ·
  concepts.json · topics.yaml · tracks.yaml · README.md

`topics.yaml`이 제외인 이유: 내가 고른 연구 주제가 거기 있다. 덮어쓰면 주제가 날아간다.
`README.md`가 제외인 이유: 자기 저장소 첫 화면은 각자 고쳐 쓴다.

**파일을 지우지 않는다.** 템플릿에서 사라진 파일도 내 저장소에는 남긴다 — 내가 추가한
스크립트를 동기화가 지워 버리는 사고를 막는 쪽이, 낡은 파일 하나가 남는 것보다 낫다.

## 워크플로 파일은 따로 센다

GitHub Actions의 기본 토큰(`GITHUB_TOKEN`)은 **`.github/workflows/` 아래를 수정할 수 없다**
— 푸시가 거부된다. 워크플로도 동기화 대상이라, 이걸 모르고 한 덩어리로 밀면 워크플로가
바뀌는 순간(바로 이번 같은 때) 동기화 전체가 실패한다. 그래서 워크플로 변경은 따로 세어
호출부가 다르게 처리할 수 있게 한다(`--skip-workflows`).

실행:
    python3 scripts/sync_from_template.py --from <추출된_템플릿_경로>
    python3 scripts/sync_from_template.py --from <경로> --dry-run       # 목록만
    python3 scripts/sync_from_template.py --from <경로> --skip-workflows # 워크플로 빼고
"""
import argparse
import filecmp
import os
import shutil
import sys

# 템플릿이 주인인 경로. 디렉터리는 슬래시로 끝낸다.
SYNC = (
    "scripts/",
    "runner/",
    "presets/",
    "templates/",
    ".github/workflows/",
    "SETUP.md",
    "GUIDE.md",
    "METHOD.md",
    "MIGRATION.md",
    "CHANGELOG.md",
)

# 어떤 경우에도 건드리지 않는다 — 학습자의 기록과 설정.
# SYNC 안에 들어와도 이쪽이 이긴다(실수로 목록이 넓어져도 기록은 지킨다).
NEVER = (
    "daily/",
    "materials/",
    "papers/",
    "mastery/",
    "mastery.md",
    "STATUS.md",
    "drills.md",
    "concepts.json",
    "topics.yaml",
    "tracks.yaml",  # 내가 나눈 학습 서랍 — 덮어쓰면 세션 저장 위치가 흔들린다
    "subjects.yaml",  # 분야 목록 — 학습자의 것이다(topics.yaml과 같은 성격)
    "README.md",
    "pilot/",  # 파일럿 롤업 산출물 — 내 저장소에서 계산된 내 수치다(pilot_rollup.py)
)


# 없을 때만 만들어 주는 씨앗 파일 — **덮어쓰지는 않는다.**
#
# 2026-08-05: `subjects.yaml`·`tracks.yaml`은 학습자의 것이라 NEVER에 있는데, 그 탓에
# **없을 때 만들어 주지도 않았다.** 그 파일들이 생기기 전에 만들어진 저장소는 영영 못
# 받고, 러너는 세션 시작에 분야 목록을 못 읽어 이름을 매번 새로 지었다(파일럿에서
# "회로 등가화·전자회로·전자회로 기초"가 각각 분야가 된 원인).
#
# 그래서 **create-only**로 연다: 없으면 템플릿의 빈 견본을 놓고, 있으면 절대 손대지 않는다.
# NEVER의 뜻은 "덮어쓰지 마라"이지 "만들지도 마라"가 아니다.
SEED_IF_MISSING = ("subjects.yaml", "tracks.yaml", "topics.yaml")


WORKFLOW_DIR = ".github/workflows/"


def is_workflow(rel):
    return rel.replace(os.sep, "/").startswith(WORKFLOW_DIR)


def is_protected(rel):
    """학습자의 기록·설정인가."""
    rel = rel.replace(os.sep, "/")
    for p in NEVER:
        if p.endswith("/"):
            if rel == p.rstrip("/") or rel.startswith(p):
                return True
        elif rel == p:
            return True
    return False


def candidate_files(src_root):
    """템플릿에서 가져올 후보 — SYNC 경로 아래의 파일 전부(보호 경로 제외)."""
    out = []
    for entry in SYNC:
        if entry.endswith("/"):
            base = os.path.join(src_root, entry.rstrip("/"))
            if not os.path.isdir(base):
                continue
            for dirpath, _dirnames, filenames in os.walk(base):
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, src_root).replace(os.sep, "/")
                    if not is_protected(rel):
                        out.append(rel)
        else:
            if os.path.isfile(os.path.join(src_root, entry)) and not is_protected(entry):
                out.append(entry)
    return sorted(set(out))


def seed_files(src_root, dst_root):
    """보호 파일 중 **없는 것만** — 있으면 절대 넣지 않는다(그건 학습자의 것이다)."""
    out = []
    for rel in SEED_IF_MISSING:
        if os.path.isfile(os.path.join(src_root, rel)) and not os.path.exists(
            os.path.join(dst_root, rel)
        ):
            out.append(rel)
    return out


def plan(src_root, dst_root):
    """(새로 생길 것, 내용이 다른 것) — 같은 파일은 어느 쪽에도 없다."""
    added, changed = seed_files(src_root, dst_root), []
    for rel in candidate_files(src_root):
        src, dst = os.path.join(src_root, rel), os.path.join(dst_root, rel)
        if not os.path.exists(dst):
            added.append(rel)
        elif not filecmp.cmp(src, dst, shallow=False):
            changed.append(rel)
    return added, changed


def apply(src_root, dst_root, files):
    for rel in files:
        src, dst = os.path.join(src_root, rel), os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser(description="템플릿의 엔진 경로만 내 저장소로 가져온다")
    ap.add_argument("--from", dest="src", required=True, help="추출된 템플릿 저장소 경로")
    ap.add_argument("--to", dest="dst", default=".", help="내 저장소 경로 (기본: 현재 위치)")
    ap.add_argument("--dry-run", action="store_true", help="바꾸지 않고 목록만 출력")
    ap.add_argument("--skip-workflows", action="store_true",
                    help="`.github/workflows/`는 건드리지 않는다 (기본 토큰으로는 푸시할 수 없다)")
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        print(f"템플릿 경로가 없다: {args.src}", file=sys.stderr)
        return 2

    added, changed = plan(args.src, args.dst)

    # 워크플로는 따로 센다 — 기본 토큰으로는 푸시할 수 없어서 호출부가 달리 다뤄야 한다.
    wf = [r for r in added + changed if is_workflow(r)]
    if args.skip_workflows:
        added = [r for r in added if not is_workflow(r)]
        changed = [r for r in changed if not is_workflow(r)]

    if not added and not changed and not wf:
        print("이미 최신이다 — 가져올 변경 없음")
        _emit(changed=False, summary="", workflows=[])
        return 0

    for rel in added:
        print(f"  + {rel}")
    for rel in changed:
        print(f"  ~ {rel}")
    summary = f"새 파일 {len(added)}개 · 갱신 {len(changed)}개"
    print(f"\n{summary}")
    print("내 기록(daily · mastery · STATUS · topics.yaml · drills)은 건드리지 않았다.")
    if args.skip_workflows and wf:
        print(f"\n⚠️  워크플로 {len(wf)}개는 건너뛰었다 (기본 토큰으로는 수정할 수 없다):")
        for r in wf:
            print(f"     {r}")

    if args.dry_run:
        print("\n--dry-run — 실제로 바꾸지 않았다.")
        return 0

    apply(args.src, args.dst, added + changed)
    _emit(changed=bool(added or changed), summary=summary, workflows=wf if args.skip_workflows else [])
    return 0


def _emit(changed, summary, workflows):
    """워크플로가 다음 단계를 정할 수 있게 결과를 넘긴다."""
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"changed={'true' if changed else 'false'}\n")
        f.write(f"summary={summary}\n")
        f.write(f"workflow_count={len(workflows)}\n")
        f.write("workflow_files=" + " ".join(workflows) + "\n")


if __name__ == "__main__":
    sys.exit(main())
