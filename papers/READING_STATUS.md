---
title: "논문 읽기 상태 — 논문 러너 진입점"
updated: 2026-08-04
kind: reading-status
---

# 📄 논문 읽기 상태

> **논문 세션을 시작하면 러너가 가장 먼저 읽는 한 파일.**
> 여기서 "지금 어느 논문 어디까지"를 잡고 시작한다 — 전체를 스캔하지 않는다.
> 세션이 끝나면 러너가 Issue의 `## READING_STATUS 갱신` 절로 이 파일을 갱신한다.

## Progress

- (아직 읽는 논문이 없다 — `papers/inbox.md`에서 한 편 골라 시작한다)

## Current Understanding

- (첫 세션 뒤부터 여기에 쌓인다)

## Next Session

- (다음 세션의 시작점 한 줄)

---

## 쓰는 법

논문 하나를 여러 세션에 걸쳐 관통한다. 한 번에 다 읽지 않는다 —
`Methods` 한 절만 제대로 설명할 수 있게 되는 것이 한 세션의 목표다.

세션이 끝나면 CI가 아래를 만든다:

| 경로 | 무엇 |
|---|---|
| `papers/<slug>/sessions/YYYY-MM-DD-<섹션>.md` | 세션 원문 — 내가 한 말 그대로 |
| `papers/<slug>/paper.md` | 정제본 — **검증된 이해만**. 설명하지 못한 것은 오지 않는다 |
| `papers/<slug>/annotations.md` | 인용 + 내 코멘트 (쌓인다) |
| 이 파일 | 지금 어디까지 · 다음 시작점 |

`<slug>`는 논문 폴더 이름이고 Issue 제목이 정한다 — `[논문] <slug> — <섹션>`.
