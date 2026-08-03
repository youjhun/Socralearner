# 이미 쓰고 있던 저장소 업데이트하기

> 템플릿으로 만든 저장소는 만든 **그 시점의 복사본**입니다 — 템플릿이 고쳐져도 자동으로
> 따라오지 않습니다. 이 문서는 이미 만들어 쓰고 있는 저장소에 변경분을 가져오는 방법입니다.
>
> 학습 기록(`daily/` · `mastery.md` · `STATUS.md`)은 **건드리지 않습니다.** 가져오는 것은
> 스크립트·워크플로·러너 지침뿐입니다.

---

## 2026-08-03 — 지식 그래프가 단어 단위로 생기던 문제

### 무엇이 문제였나

토익 트랙에서 그래프를 열어 보니 `procurement` · `adjacent` 같은 **단어 하나하나가 노드**로
잡혀 있었습니다. 원인은 러너의 실수가 아니라 **개념의 단위가 어디에도 정의돼 있지 않았다**는
것입니다. 정의가 없으면 모델은 공부한 재료를 그대로 노드로 만듭니다 — 어휘를 공부하면 어휘가
노드가 됩니다. 노드가 수백 개가 되면 **막힌 길목이 묻혀** 그래프가 아무것도 말해 주지 않습니다.

### 무엇이 바뀌었나

층을 둘로 나눴습니다.

| | 무엇 | 어디 | 규모 |
|---|---|---|---|
| **개념** | 설명을 요구할 수 있는 것 (`Part5 시제 일치`) | 그래프 노드 | 과목당 10~30개로 수렴 |
| **항목** | 회상 대상 (`procurement = 조달`) | `drills.md` — 그래프 밖 | 수백 개여도 됨 |

항목은 **버리지 않습니다.** `drills.md`에 남아 복습에 쓰이고, 그래프에만 안 들어갑니다.
판정 기준(설명·전이·위계 세 시험)은 `runner/instructions.md`의 「개념의 단위」에 있습니다.

**위계에 참여하면 무조건 개념입니다.** 선수 개념이 있거나 남의 선수이면 모양이 어휘 같아도
노드로 남습니다 — 그래서 `backpropagation` 같은 정당한 개념이 어휘로 오인되지 않습니다.

---

## 1단계 — 바뀐 파일 가져오기 (5분)

### 방법 A. 웹에서 복사 (git을 몰라도 됩니다 · 권장)

템플릿 저장소에서 아래 파일을 열고 **Raw → 전체 복사** 해서, 내 저장소의 같은 경로에
붙여넣고 커밋합니다(내 저장소에서 파일을 열고 연필 아이콘 → 내용 전체 교체).

| 파일 | 왜 |
|---|---|
| `scripts/build_concepts.py` | 개념/항목을 갈라 그래프를 깨끗하게 만든다 |
| `scripts/ingest_learning_note.py` | `## 드릴 항목`을 받아 `drills.md`로 넘긴다 |
| `scripts/migrate_drills.py` | **새 파일** — 기존 그래프 청소기 |
| `.github/workflows/learning-note-ingest.yml` | CI가 `drills.md`도 커밋하도록 |

토익 트랙이면 `presets/toeic/runner-addendum.md`와 `presets/toeic/mastery.md`도 함께.

### 방법 B. git으로 (경로만 골라 가져오기)

내 학습 기록은 손대지 않고 **그 경로들만** 덮어씁니다. 템플릿으로 만든 저장소는 원본과
커밋 이력을 공유하지 않지만, 아래 방식은 이력과 무관하게 동작합니다.

```bash
git remote add upstream https://github.com/youjhun/Socralearner.git   # 최초 한 번
git fetch upstream
git checkout upstream/main -- scripts runner .github/workflows
git commit -m "그래프 단위 수정분 가져오기 (개념/항목 2층 구조)"
git push
```

> `daily/` · `mastery.md` · `STATUS.md` · `topics.yaml`은 위 명령에 포함되지 않습니다 —
> 내 기록은 그대로입니다.

---

## 2단계 — 지금 그래프 진단하기 (1분)

저장소를 로컬에 클론한 뒤, 저장소 루트에서:

```bash
python3 scripts/migrate_drills.py
```

이렇게 나옵니다:

```
지금 라벨 16개 → 개념 2 · 항목 14

항목으로 내릴 후보 14개:
  · procurement  (선수관계 없는 단일 외국어 토큰이 14개 — 어휘 목록으로 판정)
  ...
남는 개념:
  ✓ Part5 시제 일치
  ✓ 동사 시제 기본
```

**아직 아무것도 바뀌지 않았습니다.** 목록만 보여 줍니다.

목록에 **개념인데 잘못 들어온 것**이 있으면, 그 개념에 선수관계를 하나 주세요 —
daily 노트의 `## 개념 지도`에 `그 개념 ← 선수 개념` 한 줄이면 개념으로 남습니다.

목록이 맞으면:

```bash
python3 scripts/migrate_drills.py --apply
git add drills.md concepts.json && git commit -m "그래프 청소 — 어휘를 항목으로" && git push
```

> `mastery.md`는 **건드리지 않습니다.** 원장은 내 기록이라 스크립트가 지울 것이 아닙니다.
> 되돌리려면 `drills.md`에서 그 줄을 지우고 다시 빌드하면 됩니다.

### 로컬에 클론하기 싫다면

건너뛰어도 됩니다. `scripts/build_concepts.py`만 갱신해 두면 **다음 세션의 CI가 자동으로**
같은 판정을 해서 그래프에서 어휘를 뺍니다. `migrate_drills.py`는 그것을 미리 눈으로
확인하고 `drills.md`에 확정해 두는 용도입니다.

---

## 3단계 — GPT 지침 다시 붙여넣기 (2분) ⚠️ 이걸 해야 재발하지 않습니다

스크립트만 고치면 **이미 생긴 것**은 정리되지만, 러너는 계속 단어를 개념으로 올립니다.

1. ChatGPT → 내 GPT → **편집**
2. **지침(Instructions)** 칸을 비우고, 갱신된 [`runner/instructions.md`](./runner/instructions.md)의
   회색 박스 전체를 다시 붙여넣기
3. 토익 트랙이면 그 아래에 [`presets/toeic/runner-addendum.md`](./presets/toeic/runner-addendum.md)의
   회색 박스도 이어서
4. 저장

> ✅ **성공**: 다음 세션 기록에 `## 드릴 항목` 절이 나타나고, 단어가 `## 개념 지도`에
> 올라오지 않는다.

---

## 4단계 — 확인

다음 세션을 한 번 돌린 뒤:

- 내 저장소에 **`drills.md`** 가 생겼고 단어가 거기 쌓인다
- **`concepts.json`** 의 개념 수가 줄고, 남은 것이 전부 "설명해 봐"가 성립하는 것이다
- Topdown 앱의 지식 그래프에 단어가 사라지고 **막힌 길목**이 보인다

무언가 어긋나면 `python3 scripts/build_concepts.py`를 직접 돌려 보세요 — 무엇을 개념으로,
무엇을 항목으로 판정했는지 이유까지 출력합니다.
