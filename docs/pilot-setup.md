# 파일럿 참여 설정 — 공개 저장소든 비공개 저장소든

> 이 문서는 **파일럿에 참여하기로 한 사람**만 읽으면 된다.
> 참여하지 않으면 아무것도 설정하지 않아도 되고, 그러면 수집 워크플로는 **존재하지 않는 것과 같다**.
> 계약 원문: `Topdown/docs/experiments/proof-system.md` §8.

## 0. 먼저 — 나가는 것과 나가지 않는 것

| 밖으로 나가는 것 (수치뿐) | 절대 나가지 않는 것 |
|---|---|
| 익명 ID(P01 형식), 주차 | 노트 원문 |
| 세션 수·날짜·간격 | **개념 이름** |
| 개념 수와 상태 분포(미학습/암기/설명가능) | 목표·트랙 텍스트 |
| 전이 시도·통과 수, 7일 재검증 수 | **저장소 이름·사용자명·파일 경로** |
| 산출물 수, 미해결 병목 수 | 이메일 |

이 경계는 문서가 아니라 **테스트로 강제된다** (`scripts/test_pilot_rollup.py`). 워크플로가
계산 전에 이 테스트를 먼저 돌리고, 실패하면 아무것도 내보내지 않는다.
`pilot_report_send.py`는 참가자 ID가 `P01` 형식이 아니면 **전송 자체를 거부한다**.

## 1. 동의 = 변수 하나 (opt-in)

> 동의는 기본값이 아니다. 아래를 설정하지 않으면 롤업은 **계산조차 되지 않는다**.

내 저장소 → **Settings → Secrets and variables → Actions → Variables → New**

| 이름 | 값 | 비고 |
|---|---|---|
| `PILOT_PARTICIPANT` | `P01` | 유지훈에게 배정받은 익명 ID. 이 형식이 아니면 실패한다 |

**그만두고 싶으면 이 변수를 지우면 된다.** 그 시점부터 아무것도 계산되지 않고 나가지 않는다.
(다만 "그만뒀다"는 사실 자체는 분모에 남는다 — §8.4. 이탈자가 조용히 사라지면 완료율이 부풀려지기 때문이며,
남는 것은 "P0N이 N주차부터 세션 0"이라는 **수치**이지 이유나 신원이 아니다.)

## 2-A. 저장소가 **공개**일 때 — 추가 설정 없음

워크플로가 매주 월요일 09:20 KST에 `pilot/rollup.json`을 계산해 **내 저장소에 커밋**한다.
유지훈은 그 파일을 공개 API로 읽는다. 내가 할 일은 없다.

## 2-B. 저장소가 **비공개**일 때 — 시크릿 하나 추가

비공개로 두면 유지훈이 내 저장소를 읽을 수 없다. 그래서 **내 저장소가 수치만 밖으로 보낸다.**

> 유지훈을 내 저장소의 collaborator로 초대하는 방식은 **채택하지 않는다.**
> 비공개로 바꾸고 싶은 이유가 바로 그것이기 때문이다 (§8.1).

**① 중앙 저장소 변수** (Variables에 추가)

| 이름 | 값 |
|---|---|
| `PILOT_CENTRAL_REPO` | `youjhun/Socralearner` |

중앙 저장소는 **공개**여야 한다 — 비공개 저장소에는 외부인이 Issue를 만들 수 없기 때문이다.
공개여도 안전한 이유는 §0의 경계가 테스트로 강제되기 때문이다(수치만 나간다).

**② 토큰** — Settings → Secrets → Actions → **New repository secret**

| 이름 | 값 |
|---|---|
| `PILOT_REPORT_TOKEN` | 아래에서 만든 fine-grained PAT |

토큰 만들기: GitHub → Settings → Developer settings → **Personal access tokens → Fine-grained tokens → Generate new token**

- **Repository access**: `Only select repositories` → **`youjhun/Socralearner` 하나만**
- **Permissions**: `Issues` → **Read and write** — 이것 하나만. 다른 권한은 전부 `No access`
- **Expiration**: 파일럿 종료 예정일 이후로 짧게 (예: 90일)

> 이 토큰은 **내 저장소를 읽지 못한다.** 중앙 저장소에 Issue 하나를 쓸 수 있을 뿐이다.
> 권한을 이보다 넓게 주지 말 것 — 넓게 줘도 이 워크플로는 더 쓰지 않는다.

시크릿이 없으면 전송 스텝은 **에러가 아니라 그냥 조용히 끝난다.** 공개로 쓰는 동안은 필요 없고,
비공개로 바꾸는 날 시크릿 하나만 넣으면 된다. **계산과 파일은 양쪽이 완전히 같다.**

## 3. 지금 바로 확인하기

내 저장소 → **Actions → `pilot-report` → Run workflow**

- `PILOT_PARTICIPANT` 미설정 → *"이 저장소는 파일럿 집계 대상이 아니다"* 로그만 남고 종료 (정상)
- 설정됨 → `pilot/rollup.json` 생성/갱신. 파일을 **직접 열어보고**, 안에 개념 이름이나
  내 계정명이 없는지 눈으로 확인할 것. 하나라도 보이면 **즉시 유지훈에게 알리고 변수를 지운다.**

## 4. 내가 언제든 할 수 있는 것

| 하고 싶은 것 | 방법 |
|---|---|
| 중단 | `PILOT_PARTICIPANT` 변수 삭제 |
| 완전 삭제 요청 | 유지훈에게 말한다 — 이미 보낸 롤업 Issue까지 지운다 |
| 무엇이 나갔는지 확인 | `pilot/rollup.json` 커밋 이력이 전부다. 그 밖의 경로는 없다 |
| 저장소를 비공개로 전환 | 2-B만 추가하면 된다. 롤업 계산은 그대로 |

## 5. 유지훈 쪽 (참가자는 읽지 않아도 됨)

```bash
# 공개 참가자 — fleet.txt는 .gitignore 대상이다. 저장소 안에 커밋하지 않는다.
python3 scripts/pilot_cohort.py --file fleet.txt

# 비공개 참가자 — 중앙 저장소의 [롤업] Issue를 읽는다.
python3 scripts/pilot_cohort.py --central youjhun/Socralearner --week 2026-W32

# 섞여 있을 때 (전환기의 실제 모습)
python3 scripts/pilot_cohort.py --file fleet.txt --central youjhun/Socralearner
```

익명 ID ↔ 실제 사람의 매핑은 **이 저장소에 두지 않는다.** 비공개 저장소(Hunwiki)에만 둔다.
