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
  concepts.json · topics.yaml · README.md

`topics.yaml`이 제외인 이유: 내가 고른 연구 주제가 거기 있다. 덮어쓰면 주제가 날아간다.
`README.md`가 제외인 이유: 자기 저장소 첫 화면은 각자 고쳐 쓴다.

**파일을 지우지 않는다.** 템플릿에서 사라진 파일도 내 저장소에는 남긴다 — 내가 추가한
스크립트를 동기화가 지워 버리는 사고를 막는 쪽이, 낡은 파일 하나가 남는 것보다 낫다.

실행:
    python3 scripts/sync_from_template.py --from <추출된_템플릿_경로>
    python3 scripts/sync_from_template.py --from <경로> --dry-run   # 목록만
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
    "README.md",
)


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


def plan(src_root, dst_root):
    """(새로 생길 것, 내용이 다른 것) — 같은 파일은 어느 쪽에도 없다."""
    added, changed = [], []
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
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        print(f"템플릿 경로가 없다: {args.src}", file=sys.stderr)
        return 2

    added, changed = plan(args.src, args.dst)

    if not added and not changed:
        print("이미 최신이다 — 가져올 변경 없음")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write("changed=false\n")
        return 0

    for rel in added:
        print(f"  + {rel}")
    for rel in changed:
        print(f"  ~ {rel}")
    print(f"\n새 파일 {len(added)}개 · 갱신 {len(changed)}개")
    print("내 기록(daily · mastery · STATUS · topics.yaml · drills)은 건드리지 않았다.")

    if args.dry_run:
        print("\n--dry-run — 실제로 바꾸지 않았다.")
        return 0

    apply(args.src, args.dst, added + changed)

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("changed=true\n")
            f.write(f"summary=새 파일 {len(added)}개 · 갱신 {len(changed)}개\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
