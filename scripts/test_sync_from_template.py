#!/usr/bin/env python3
"""sync_from_template 회귀 테스트 — 가짜 저장소 두 개를 만들어 실제로 동기화해 본다.

실행: python3 scripts/test_sync_from_template.py

지켜야 하는 것은 하나다: **학습자의 기록을 절대 덮어쓰지 않는다.**
이 스크립트는 남의 저장소에서 자동으로 도는 것이라, 한 번 잘못 덮으면 그 사람의
공부 기록이 사라진다. 그래서 경로 정책을 테스트로 못박는다.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_from_template as sync  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "template")
dst = os.path.join(tmp, "mine")

# ── 템플릿 (새 버전) ────────────────────────────────────────────────────────
write(src, "scripts/build_concepts.py", "새 버전")
write(src, "scripts/brand_new.py", "새로 생긴 스크립트")
write(src, "runner/instructions.md", "새 지침")
write(src, ".github/workflows/paper-scan.yml", "새 워크플로")
write(src, "presets/toeic/README.md", "새 프리셋 설명")
write(src, "SETUP.md", "새 세팅 문서")
write(src, "CHANGELOG.md", "## 2026-08-03\n바뀐 것")
# 템플릿에도 있지만 학습자 쪽이 주인인 것들
write(src, "topics.yaml", "topics: []          # 템플릿 기본값")
write(src, "STATUS.md", "템플릿 기본 STATUS")
write(src, "mastery.md", "템플릿 기본 원장")
write(src, "README.md", "템플릿 README")
write(src, "daily/2026-01-01-example-session.md", "예시 세션")
write(src, "knowledge/concepts.yaml", "concepts: []        # 템플릿 빈 견본")

# ── 학습자 저장소 (옛 버전 + 자기 기록) ─────────────────────────────────────
write(dst, "scripts/build_concepts.py", "옛 버전")
write(dst, "runner/instructions.md", "옛 지침")
write(dst, ".github/workflows/paper-scan.yml", "옛 워크플로")
write(dst, "presets/toeic/README.md", "옛 프리셋 설명")
write(dst, "SETUP.md", "옛 세팅 문서")
write(dst, "scripts/my_own_hack.py", "내가 추가한 스크립트")
MY = {
    "topics.yaml": "topics:\n  - id: bci\n    query: 'brain computer interface'",
    "STATUS.md": "내 진짜 학습 상태",
    "mastery.md": "| 개념 | 상태 |\n| 푸리에 | 설명가능 |",
    "drills.md": "- procurement = 조달",
    "concepts.json": '{"concepts": [{"id": "fourier"}]}',
    "README.md": "내가 고친 첫 화면",
    "daily/2026-07-30-fourier.md": "내가 쓴 세션 기록",
    "materials/lecture-01.md": "내가 올린 강의자료",
    "papers/inbox.md": "내 논문 인박스",
    "mastery/2026-07-30-x.md": "내 승급 조각",
    # 개념 레지스트리 — 손으로 쌓은 그래프의 SSOT다. 템플릿의 빈 견본이 이걸 덮으면
    # 개념 72·선수관계 75가 한 번에 0이 된다(그리고 그래프는 조용히 비어 보인다).
    "knowledge/concepts.yaml": "concepts:\n- id: fourier\n  label: 푸리에 변환",
}
for rel, text in MY.items():
    write(dst, rel, text)

print("① 계획 단계에서 이미 기록을 후보로 잡지 않는다")
added, changed = sync.plan(src, dst)
touched = set(added) | set(changed)
for rel in MY:
    check(f"{rel} 는 후보가 아니다", rel not in touched)

print("\n② 엔진 파일은 제대로 잡는다")
check("바뀐 스크립트를 갱신 대상으로", "scripts/build_concepts.py" in changed)
check("새 스크립트를 추가 대상으로", "scripts/brand_new.py" in added)
check("러너 지침을 갱신 대상으로", "runner/instructions.md" in changed)
check("워크플로를 갱신 대상으로", ".github/workflows/paper-scan.yml" in changed)
check("프리셋을 갱신 대상으로", "presets/toeic/README.md" in changed)
check("CHANGELOG를 추가 대상으로", "CHANGELOG.md" in added)

print("\n③ 실제로 적용해도 내 기록은 한 글자도 안 바뀐다")
sync.apply(src, dst, added + changed)
for rel, original in MY.items():
    check(f"{rel} 내용 보존", read(dst, rel) == original,
          f"기대={original[:20]!r} 실제={read(dst, rel)[:20]!r}")

print("\n④ 엔진은 새 버전이 됐다")
check("build_concepts.py 갱신됨", read(dst, "scripts/build_concepts.py") == "새 버전")
check("instructions.md 갱신됨", read(dst, "runner/instructions.md") == "새 지침")
check("새 스크립트가 생겼다", os.path.exists(os.path.join(dst, "scripts/brand_new.py")))

print("\n⑤ 내가 추가한 파일을 지우지 않는다")
check("my_own_hack.py 가 남아 있다", read(dst, "scripts/my_own_hack.py") == "내가 추가한 스크립트")

print("\n⑥ 두 번째 실행은 할 일이 없다 (멱등)")
added2, changed2 = sync.plan(src, dst)
check("다시 돌려도 변경 없음", not added2 and not changed2, f"added={added2} changed={changed2}")

print("\n⑦ 보호 경로 판정 자체")
for rel in ("daily/x.md", "daily", "topics.yaml", "mastery/a.md", "materials/deep/x.md",
            "knowledge/concepts.yaml", "knowledge"):
    check(f"{rel} → 보호됨", sync.is_protected(rel))
for rel in ("scripts/x.py", "runner/instructions.md", "presets/toeic/README.md"):
    check(f"{rel} → 보호 아님", not sync.is_protected(rel))

print("\n⑦-b 컴파일 산출물은 남의 저장소에 심지 않는다")
# 템플릿에서는 .gitignore가 막지만 이 스크립트는 작업 트리를 걷는다 — 로컬에서 테스트를
# 한 번 돌린 뒤 동기화하면 .pyc가 딸려 가고, 받는 쪽엔 .gitignore가 없을 수도 있다.
for rel in ("scripts/__pycache__/build_concepts.cpython-311.pyc", "scripts/x.pyc",
            "runner/__pycache__/a.pyc"):
    check(f"{rel} → 후보 아님", sync.is_junk(rel))
for rel in ("scripts/build_concepts.py", "runner/instructions.md"):
    check(f"{rel} → 정상 후보", not sync.is_junk(rel))
src_j = os.path.join(tmp, "template_junk")
write(src_j, "scripts/a.py", "엔진")
write(src_j, "scripts/__pycache__/a.cpython-311.pyc", "바이트코드")
check("__pycache__는 계획에 아예 안 들어온다",
      not any("pycache" in r for r in sum(sync.plan(src_j, os.path.join(tmp, "mine_junk")), [])))

print("\n⑧ 워크플로 파일을 따로 셀 수 있다 (기본 토큰으로는 못 밀기 때문)")
check(".github/workflows/x.yml → 워크플로", sync.is_workflow(".github/workflows/x.yml"))
check("scripts/x.py → 워크플로 아님", not sync.is_workflow("scripts/x.py"))

# --skip-workflows 로 돌리면 워크플로만 빼고 나머지는 그대로 간다
src2 = os.path.join(tmp, "template2")
dst2 = os.path.join(tmp, "mine2")
write(src2, "scripts/a.py", "새것")
write(src2, ".github/workflows/w.yml", "새 워크플로")
write(dst2, "scripts/a.py", "옛것")
write(dst2, ".github/workflows/w.yml", "옛 워크플로")
added3, changed3 = sync.plan(src2, dst2)
sync.apply(src2, dst2, [r for r in changed3 if not sync.is_workflow(r)])
check("워크플로를 건너뛰면 스크립트만 갱신된다", read(dst2, "scripts/a.py") == "새것")
check("워크플로는 그대로 남는다", read(dst2, ".github/workflows/w.yml") == "옛 워크플로")

shutil.rmtree(tmp)

print()
if FAILED:
    print(f"실패 {len(FAILED)}개: " + ", ".join(FAILED))
    sys.exit(1)

# ⑨ 씨앗 파일 — 없으면 만들고, 있으면 절대 건드리지 않는다 (2026-08-05)
#    `subjects.yaml`은 NEVER에 있어 덮어쓰지 않지만, 그 탓에 **없을 때 만들어 주지도
#    않았다.** 그 파일이 생기기 전에 만들어진 저장소는 영영 못 받았고, 러너는 분야
#    목록을 못 읽어 이름을 매번 새로 지었다.
print("\n⑨ 씨앗 파일 (create-only)")
with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
    os.makedirs(os.path.join(src, "scripts"), exist_ok=True)
    with open(os.path.join(src, "subjects.yaml"), "w", encoding="utf-8") as f:
        f.write("subjects: []\n")
    with open(os.path.join(src, "tracks.yaml"), "w", encoding="utf-8") as f:
        f.write("tracks: []\n")
    os.makedirs(os.path.join(src, "knowledge"), exist_ok=True)
    with open(os.path.join(src, "knowledge", "concepts.yaml"), "w", encoding="utf-8") as f:
        f.write("concepts: []\n")

    added, changed = sync.plan(src, dst)
    check("없으면 씨앗을 만든다", "subjects.yaml" in added and "tracks.yaml" in added,
          str(added))
    # 빈 견본이라 노트 모드는 그대로 돌고, 채우면 그때부터 그래프의 SSOT가 된다.
    check("레지스트리 빈 견본도 씨앗으로 놓인다", "knowledge/concepts.yaml" in added, str(added))

    sync.apply(src, dst, added + changed)
    with open(os.path.join(dst, "knowledge", "concepts.yaml"), "w", encoding="utf-8") as f:
        f.write("concepts:\n- id: fourier\n")   # 학습자가 채웠다
    added_r, changed_r = sync.plan(src, dst)
    check("채워진 레지스트리는 씨앗에도 갱신에도 안 들어간다",
          "knowledge/concepts.yaml" not in added_r + changed_r, str(added_r + changed_r))

    # 학습자가 이미 채워 둔 파일을 템플릿 견본으로 되돌리면 묶어 둔 분야가 통째로 날아간다.
    with open(os.path.join(dst, "subjects.yaml"), "w", encoding="utf-8") as f:
        f.write('subjects:\n  - name: "전자회로"\n')
    added2, changed2 = sync.plan(src, dst)
    check("이미 있으면 씨앗에 넣지 않는다", "subjects.yaml" not in added2, str(added2))
    check("이미 있으면 갱신 대상도 아니다", "subjects.yaml" not in changed2, str(changed2))

    sync.apply(src, dst, added2 + changed2)
    kept = open(os.path.join(dst, "subjects.yaml"), encoding="utf-8").read()
    check("학습자가 적은 분야가 살아남는다", "전자회로" in kept, kept)

print("전부 통과 — 학습 기록은 어느 경로로도 덮이지 않는다")
