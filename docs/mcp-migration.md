# MCP 이관 배선도

> **상태: 설계 확정 · 구현 전** (2026-08-05 결정)
> 러너의 쓰기 경로를 **Custom GPT Action → MCP**로 옮긴다.
> 이 문서가 배선의 원본이다. 서버 코드는 Topdown 모노레포에 산다(§5).

---

## 1. 무엇이 고장났나

**증상**: 세션 노트가 3줄로 잘려 저장된다. 러너가 "기록했다"고 말하고 실제로는 요약만 남는다.

이건 개별 사고가 아니라 **문서화된 상시 증상**이다.

- `SETUP.md` 막히는 지점: *"기록이 3줄로 짧게만 남아요 → **정상이 아닙니다**"*
- 커밋 이력이 전부 같은 불을 끈 기록이다 — #15(러너가 저장소를 못 읽음) · #18(러너가 "못 쓴다"며 기록을 포기) · #19(액션을 코드로 부르거나 웹 검색으로 갈아타지 못하게 못박음) · #21(읽기는 되는데 Issue만 안 만들어짐)
- 2026-08-05 Hunwiki 논문 세션 1건이 **통째로 유실**됐다(Issue #69가 마지막, 08-05는 파일도 이슈도 없음).

## 2. 근본 원인 — 지침으로는 못 고친다

현행 `runner/action-schema.yaml`은 **오퍼레이션 14개가 전부 `api.github.com`을 직접** 친다.
세션 하나를 끝내려면 모델이:

- **읽기 8회** — STATUS · mastery · 모드 대본 · daily · papers · materials … 매 파일이 모델 컨텍스트를 통과한다
- **쓰기 3회** — `createNote` → `appendNote` → `closeNote`. 그 사이 **`issue_number`를 모델이 손으로 들고 있어야** 한다

노트가 길어지면 모델에게 두 갈래뿐이다: 인자가 잘려 호출이 깨지거나, **살아남는 길이로 스스로 줄이거나.**
모델은 후자를 택한다. #19에서 지침을 더 세게 써서 고치려 했으나 재발했다 — 실패의 원인이
**모델의 순종이 아니라 왕복 횟수와 모델의 상태 보유**이기 때문이다. 지침은 그 둘을 바꾸지 못한다.

## 3. 새 배선 — 엔드포인트 14개 → 툴 4개

**원칙: 툴은 엔드포인트 모양이 아니라 동사 모양이다. 팬아웃은 서버가 한다.**

| 툴 | 대체 | 왕복 |
|---|---|---|
| `get_state` | 읽기 8회 | **8 → 1**. 서버가 STATUS·mastery·parking lot·모드 대본·트랙을 서버에서 모아 패킷 하나로 준다 |
| `read_doc(path)` | 나머지 읽기 | 탈출구 — `papers/<slug>/paper.md` · `materials/` · `daily/` |
| `list_papers` / `get_paper(slug)` | 논문 읽기 4종 | 논문 모드 |
| `save_session(payload)` | `createNote`+`appendNote`+`closeNote` | **3 → 1**. 모델이 `issue_number`를 들고 있지 않는다 |

### `save_session` — 잘림을 구조적으로 죽이는 두 장치

```
save_session({
  mode:            "learning" | "paper" | "exam" | "research",
  track?:          string,          // 과목 트랙
  paper_slug?:     string,          // 논문 모드 — papers/ 아래 폴더명과 정확히 일치
  title:           string,

  learned_in_learner_words: string, // 필수. 학습자가 실제로 한 말 그대로
  weak_spots:      string[],
  review_questions: string[],
  mastery_deltas:  [{ concept_id, to: "memorized"|"can_explain", evidence }],
  parking_lot_add: [{ concept, blocker: boolean }],
  parking_lot_resolve: string[],

  // 논문 모드
  refined_sections?: [{ name, body }],   // paper.md의 같은 이름 절을 교체
  annotations?:      string[],
  reading_status?:   { progress, current_understanding, next_session },
  figures?:          [{ alt, url }],

  continuation_token?: string,
}) -> { ok, files_written[], issue_url, warnings[] }
   |  { needs_continuation: true, continuation_token }
```

1. **구조화 인자.** 한 덩어리 마크다운이 아니라 필드 단위다. 그래서 **서버가 무엇이 비었는지 안다** —
   `learned_in_learner_words`가 최소 길이 미만이면 서버가 거부하고 이유를 돌려준다.
   조용한 3줄 요약이 **불가능**해진다. `evidence` 없는 `mastery_deltas`도 거부한다(기존 계약 유지).
2. **`continuation_token`.** 그래도 긴 세션은 이어 보내되, **이슈 번호가 아니라 서버가 준 토큰**으로.
   모델은 어떤 상태도 관리하지 않는다.

### 마크다운 계약을 아는 주체가 바뀐다

지금은 **모델**이 `## 오늘 직접 학습한 지식` 같은 정규 헤딩을 정확히 써야 CI가 읽는다.
새 배선에서는 **서버**가 구조화 payload를 그 헤딩으로 렌더한다. 모델은 내용만 만든다.
이것이 이관의 진짜 이득이다 — 형식 준수를 확률적 주체에서 결정론적 주체로 옮긴다.

## 4. 쓰기 경로 — CI를 그대로 재사용한다

```
러너 → [MCP] save_session → 서버가 Issue 1건 생성 + 즉시 close
                          → learning-note-ingest CI (지금과 동일)
                          → ingest_learning_note.py 가 파일 생성
                          → 서버가 CI 결과를 기다려 툴 응답으로 반환
```

- `ingest_learning_note.py`(951줄)와 `test_ingest_learning_note.py`를 **한 줄도 복제하지 않는다.**
- 서버가 CI 결과를 **기다렸다가** 성공/실패를 돌려주므로, 러너가 "저장됐나?"를 추측하지 않는다 —
  #18의 실패 모드가 사라진다.
- 실패하면 Issue는 열린 채 남고 `/기록` 재시도 경로도 그대로다.

## 5. 배포 두 벌, 코드 한 벌

Topdown은 TypeScript, Hudson `services/hermes`는 Python이다. **각 호스트에 맞춰 다시 구현하면
로직이 두 언어로 복제된다** — 표준규칙("never duplicate logic") 위반이고, 실제로 이 프로젝트가
이미 한 번 당한 실패다(러너 지침이 ChatGPT UI와 대시보드 두 곳에 있어 고칠 곳이 둘이었던 일).

그래서 **코드는 한 벌**(Topdown 모노레포 `packages/mcp-core` + `apps/mcp`), **배포만 두 벌**이다.
차이는 환경설정뿐이며, Hermes는 이 서비스를 **재구현하지 않고 컨테이너로 옆에 띄운다**
(Hermes에 이미 Dockerfile이 있다).

| | **A — 공개 (Socralearner 사용자)** | **B — 개인 (유지훈 Hunwiki 전용)** |
|---|---|---|
| 호스트 | Topdown 앱 | Hudson `services/hermes` 옆 |
| 테넌시 | multi-tenant | single-tenant |
| 대상 repo | 사용자 각자의 학습 repo | `youjhun/Hunwiki` 고정 |
| 인증 | GitHub App **OAuth** | 소유자 App 설치 토큰 (OAuth 플로 없음) |
| 러너 | Socralearner 러너 | PaperGPT · 학습 러너 |
| 경로 | `daily/` · `papers/` | `30-Learning/` · `20-Research/NEP/` |

두 배포의 store adapter만 다르고 툴 계약은 동일하다.

## 6. 인증 — GitHub App OAuth

- 권한: **Contents `read`** + **Issues `read/write`**. 지금 PAT과 같은 범위다 — 새 권한이 아니다.
  파일을 쓰는 것은 여전히 CI이므로 Contents write는 필요 없다.
- **사용자 경험**: `SETUP.md`의 **2단계(Actions 권한)와 3단계(PAT 발급, 5분 + "이 토큰 위험하지 않나요?" 절 전체)가
  통째로 사라진다.** 4단계의 스키마 붙여넣기도 사라진다. 남는 것: repo 만들기 → 커넥터 연결(클릭) → 첫 세션.
  **7단계 → 3단계.**
- **새로 지는 리스크**: 지금은 각자 PAT을 자기 GPT에 넣는다. OAuth로 가면 **우리가 남의 GitHub 토큰을 보관한다.**
  파일럿 규모에서 이게 가장 큰 신규 리스크다. 완화는 구현 단계에서 정한다(암호화 보관 · 최소 권한 · 폐기 경로 · 유출 시 일괄 revoke).

## 7. 배포 단계 — 유료 문턱은 오히려 낮아진다

플랫폼 사실(2026-08-05 확인):

- **커스텀 GPT 빌더는 Actions(OpenAPI)만 붙는다. MCP 커넥터 슬롯이 없다.**
- ChatGPT의 MCP는 **Settings → Connectors → Advanced → Developer mode**(Plus/Pro 베타, 읽기+쓰기)에 있고, 일반 대화에 붙는다.
- **Apps SDK**(MCP 기반)로 만든 앱은 심사 통과 후 **Free·Go·Plus·Pro** 전부에서 쓸 수 있다(EEA·스위스·영국 제외 — 한국은 해당 없음).

| 단계 | 경로 | 대상 |
|---|---|---|
| **1 (파일럿, 지금)** | Developer Mode 커스텀 커넥터 | Plus/Pro. 심사 없음, 오늘 가능 |
| **2** | Apps SDK 앱으로 제출 | 승인 시 Free 포함 전부 |

지금도 커스텀 GPT **생성**은 Plus를 요구한다(`SETUP.md` 4단계). 따라서 2단계에 도달하면 문턱은 **내려간다.**
그리고 MCP는 커스텀 GPT 종속이 아니라 같은 서버가 Claude·Cursor에도 그대로 붙는다.

## 8. 새로 지는 비용 (정직하게)

- **상시 서버가 생긴다.** 지금 Socralearner의 가동 의존성은 GitHub뿐이고 우리가 죽일 수 있는 게 없다.
  MCP 서버가 죽으면 **모든 사용자의 세션 기록이 멈춘다.**
  → **수동 폴백을 반드시 남긴다**: 러너가 노트 전문을 코드블록으로 출력하고 사용자가 `[학습]`/`[논문]` Issue에
  붙여넣으면 CI 경로는 완전히 동일하다. 이미 존재하고 작동하는 경로다(`SETUP.md` "ChatGPT Plus가 없다면").
- **토큰 보관 책임** (§6).
- **Apps SDK 심사 시점을 우리가 통제하지 못한다** — 그래서 1단계로 먼저 간다.

## 9. 남는 열린 질문 (구현 착수 전 결정)

- OAuth 토큰 보관 방식과 폐기·revoke 경로.
- 서버가 CI 완료를 기다리는 타임아웃과, 초과 시 러너에게 무엇을 말할지("접수됨, 결과 미확인"과 "실패"를 구분해야 한다).
- 기존 PAT 사용자 이행 경로 — `MIGRATION.md`에 반영 필요.
- `runner/action-schema.yaml`과 `SETUP.md` 2·3·4단계의 폐기 시점(1단계 동안은 두 경로가 공존한다).
