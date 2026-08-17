#!/usr/bin/env python3
"""consolidate_mastery 회귀 테스트 — 조각이 원장에 접힐 때 무엇이 지켜지는가.

실행: python3 scripts/test_consolidate_mastery.py

지키는 것 (2026-08-17):
  ① **빈 칸은 주장이 아니다** — 새 조각이 이겨도 빈 칸은 원장의 옛 값을 지킨다.
     MCP 승급 조각이 중요도를 비워 보내므로, 행 통째 교체면 중요도가 승급마다 지워진다.
  ② 채운 칸은 최신이 이긴다(기존 계약 그대로) — 옛 조각(전 칸이 참)의 동작 불변.
  ③ 조각의 6열 머리는 인제스터의 변환기와 **바이트 동일**하다 — 사람이 조각을 읽을 때
     칸을 잘못 세지 않게, 두 파일이 같은 머리를 단다(동조).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consolidate_mastery as cm  # noqa: E402
import ingest_learning_note as ingest  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


LEDGER = f"""# 이해도

{cm.START}
{cm.HEADER}
{cm.SEP}
| DTW | 암기 | H | 2026-08-01 | [[daily/2026-08-01-dtw]] | 공식만 암기 |
{cm.END}

## 상태정의
- 설명가능: 유도하고 반박을 통과함
"""


def run(fragment):
    d = tempfile.mkdtemp()
    ledger = os.path.join(d, "mastery.md")
    with open(ledger, "w", encoding="utf-8") as f:
        f.write(LEDGER)
    os.makedirs(os.path.join(d, "mastery"))
    with open(os.path.join(d, "mastery", "2026-08-17-x.md"), "w", encoding="utf-8") as f:
        f.write(fragment)
    cm.consolidate(ledger)
    with open(ledger, encoding="utf-8") as f:
        return f.read()


def main():
    print("[병합] 빈 칸은 주장이 아니다")
    # MCP 변환기가 만드는 모양 그대로: 중요도가 빈 새 승급 행.
    out = run(
        f"{cm.HEADER}\n{cm.SEP}\n"
        "| DTW | 설명가능 |  | 2026-08-17 | [[daily/2026-08-17-dtw]] | 반박 통과 |\n"
    )
    check("상태·검증일·증거·메모는 새 것이 이긴다 (②)", "| DTW | 설명가능 | H | 2026-08-17 |" in out, out)
    check("빈 중요도가 원장의 H를 지우지 않는다 (①)", "| H |" in out or "| DTW | 설명가능 | H |" in out)
    check("마커 밖 서사는 그대로다", "## 상태정의" in out and "유도하고 반박을 통과함" in out)

    print("\n[병합] 전 칸이 찬 조각(옛 방식)은 예전 그대로 통째로 이긴다")
    out = run(
        f"{cm.HEADER}\n{cm.SEP}\n"
        "| DTW | 설명가능 | M | 2026-08-17 | [[daily/2026-08-17-dtw]] | 반박 통과 |\n"
    )
    check("채운 중요도는 새 것이 이긴다", "| DTW | 설명가능 | M | 2026-08-17 |" in out, out)

    print("\n[병합] 옛 날짜의 조각은 원장을 되돌리지 못한다")
    out = run(
        f"{cm.HEADER}\n{cm.SEP}\n"
        "| DTW | 미학습 | L | 2026-07-01 | [[daily/2026-07-01-dtw]] | 옛 기록 |\n"
    )
    check("최신 우선이 유지된다", "| DTW | 암기 | H | 2026-08-01 |" in out, out)

    print("\n[동조] 조각 머리 == 원장 머리")
    check("HEADER 바이트 동일", ingest.MASTERY_HEADER == cm.HEADER, ingest.MASTERY_HEADER)
    check("SEP 바이트 동일", ingest.MASTERY_SEP == cm.SEP)

    print()
    if FAILED:
        print(f"❌ 실패 {len(FAILED)}: " + ", ".join(FAILED))
        return 1
    print("✅ 전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
