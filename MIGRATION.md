# 이미 쓰고 있던 저장소 업데이트하기

> 템플릿으로 만든 저장소는 만든 **그 시점의 복사본**입니다 — 템플릿이 고쳐져도 자동으로
> 따라오지 않습니다. 이 문서는 이미 만들어 쓰고 있는 저장소에 변경분을 가져오는 방법입니다.
>
> 학습 기록(`daily/` · `mastery.md` · `STATUS.md`)은 **건드리지 않습니다.** 가져오는 것은
> 스크립트·워크플로·러너 지침뿐입니다.

---

## 2026-08-05 — Custom GPT 액션에서 MCP 커넥터로

### 무엇이 문제였나

두 가지가 계속 반복됐고, 지침을 아무리 세게 써도 안 고쳐졌습니다.

1. **AI가 도구를 아예 안 불렀습니다.** 웹 검색으로 새거나 "읽기에 실패했습니다,
   상태를 붙여넣어 주세요"라고 했고, 매 세션 *"액션으로 해"* · *"다시 불러와"* 를
   쳐야 했습니다.
2. **긴 세션이 3줄로 잘렸습니다.** 기록됐다고 말하고 실제로는 요약만 남았습니다.

둘 다 AI의 불순종이 아니라 배선 문제였습니다. 읽기 동작이 8개라 고르다 틀렸고,
`daily/` 노트는 파일명을 **추측**해야 해서 404가 났고, 404가 반복되니 AI는 절대
404가 안 나는 능력(웹 검색)으로 갈아탔습니다. 쓰기는 3번 호출이라 중간에 끊기면
세션이 통째로 사라졌습니다 — 실제로 그렇게 잃은 세션이 있습니다.

### 무엇이 바뀌었나

| | 예전 | 지금 |
|---|---|---|
| 읽기 | 오퍼레이션 8개, 경로·파일명을 알아야 함 | **`get_state` 1개, 인자 0개.** 직전 세션 전문까지 함께 옴 |
| 쓰기 | `createNote` → `appendNote` → `closeNote` | **`save_session` 1개** |
| 없는 파일 | 404(= AI에겐 "고장") | `missing`에 이름만 담겨 옴 (실패가 아님) |
| 너무 짧은 노트 | 조용히 저장됨 | **서버가 거부**하고 이유를 돌려줌 |
| 인증 | PAT 직접 발급·붙여넣기 | GitHub App 설치 + 승인 버튼 |
| 저장소 지정 | 지침에 `owner/repo` 직접 기입 | 연결에서 옴 (매 대화 되묻지 않음) |

### 내가 해야 하는 일

**학습 기록은 건드리지 않습니다.** `daily/` · `mastery.md` · `STATUS.md` 그대로입니다.

1. [`SETUP.md`](./SETUP.md)의 **3단계(App 설치)** 와 **4단계(커넥터 연결)** 만 새로 합니다.
   1·2단계(저장소·Actions 권한)는 이미 돼 있으니 건너뜁니다.
2. 예전 Custom GPT는 **지워도 되고 그냥 둬도 됩니다.** 두 경로는 같은 자동화로
   흘러가므로 섞여 돌아가도 기록은 한 곳에 모입니다.
3. **PAT은 이제 필요 없습니다.** GitHub → Settings → Developer settings →
   Personal access tokens에서 지우세요. 안 지워도 동작에는 지장 없지만, 안 쓰는
   열쇠를 남겨 둘 이유가 없습니다.
4. 스크립트·워크플로 변경분을 가져오려면 아래 「업데이트 가져오기」를 따릅니다.

> 무료 계정이라 커넥터를 못 쓰면 **예전 방식이 그대로 살아 있습니다** —
> `runner/action-schema.yaml`은 폐기 예정 표시만 붙었을 뿐 동작합니다.

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

## 🎉 먼저 — 이걸 한 번만 하면 다음부터는 자동입니다

지금까지는 템플릿이 고쳐질 때마다 이 문서를 보고 손으로 파일을 복사해야 했습니다.
**이제 안 그래도 됩니다.** 아래 **파일 하나만** 가져오면, 다음부터는 템플릿이 바뀔 때마다
내 저장소에 **자동으로 적용되고 Issue로 알려 줍니다.** 머지도 안 눌러도 됩니다.

| 가져올 파일 | 무엇 |
|---|---|
| [`.github/workflows/template-sync.yml`](https://github.com/youjhun/Socralearner/blob/main/.github/workflows/template-sync.yml) | 세션이 끝날 때·매일 09:20 KST에 템플릿을 확인해 적용한다 |

이거 하나뿐입니다. 동기화 로직은 **매번 템플릿에서 새로 받아 실행**하므로 저장소에 미리
넣어 둘 필요가 없습니다(그래야 로직이 낡아 동기화가 실패하는 자기모순이 안 생깁니다).

가져오는 법은 아래 [1단계](#1단계--바뀐-파일-가져오기-5분)와 같습니다(웹 복사 또는 git).
바로 확인하려면 **Actions → template-sync → Run workflow**.

> 무엇을 가져오나: `scripts/` · `runner/` · `presets/` · `templates/` ·
> `.github/workflows/` · 문서.
> **절대 안 가져오는 것**: `daily/` · `materials/` · `papers/` · `mastery.md` ·
> `mastery/` · `STATUS.md` · `drills.md` · `concepts.json` · `topics.yaml` · `README.md`.
> 이 약속은 `scripts/test_sync_from_template.py`가 매 실행마다 검사합니다.
> 파일을 **지우지도** 않습니다 — 내가 추가한 스크립트는 그대로 남습니다.

### 잘 되고 있는지 확인하기

설치했으면 **Actions → template-sync → Run workflow** 를 한 번 눌러 보세요. 성공하면:

1. 커밋 목록에 `템플릿 업데이트 — …` 커밋이 생깁니다
2. Issues에 `[템플릿] … 업데이트` 가 하나 열립니다 (무엇이 바뀌었는지 적혀 있음)
3. `daily/` · `mastery.md` · `STATUS.md` · `topics.yaml` 은 **그대로**입니다

여러 사람 것을 한 번에 보려면 (템플릿 저장소에서):

```bash
python3 scripts/check_fleet.py friend1/my-learning friend2/study
# 또는 목록 파일로
python3 scripts/check_fleet.py --file fleet.txt
```

```
  friend1/my-learning  🟢 최신  (마지막 동기화 2026-08-03)
  friend2/study        🟡 뒤처짐 2개 — 설치는 됐다. Run workflow 한 번이면 따라온다
  friend3/toeic        🔴 자동 동기화 미설치 — MIGRATION.md의 파일 3개를 넣어 줘야 한다
```

읽기만 합니다. 남의 저장소를 고치지 않습니다.

### 알아 둘 것 두 가지

**① 결국 손으로 하는 건 GPT 지침 하나뿐입니다.**
스크립트·러너 지침 파일·프리셋·문서는 전부 자동으로 적용됩니다. ChatGPT Custom GPT의
Instructions만 API로 바꿀 수 없어서, 그게 바뀌면 알림 Issue 맨 위에
**"⚠️ 이것만 직접 해 주세요 — GPT 지침"** 으로 뜨고 붙여넣을 위치까지 링크로 줍니다.

워크플로 파일(`.github/workflows/`)도 기본 토큰으로는 못 바꾸지만, 이제 그 파일들은
**"체크아웃하고 스크립트를 부른다"만 있는 껍데기**라 거의 바뀌지 않습니다(로직은 `scripts/`에
있고 그건 자동입니다). 혹시 바뀌면 Issue가 링크와 함께 알려 줍니다. 이것까지 자동으로 하려면
`workflow` 스코프 토큰을 **Settings → Secrets and variables → Actions** 에
`TEMPLATE_SYNC_TOKEN` 으로 넣어 두면 됩니다. 선택입니다.

**② 자동 적용이 싫으면 PR로 받을 수 있습니다.**
**Settings → Secrets and variables → Actions → Variables** 에서
`TEMPLATE_SYNC_MODE` = `pr` 로 두면 적용 대신 PR을 엽니다. 이 경우
**Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests"**
를 켜야 합니다.

---

## 2026-08-03 — paper-scan이 주제를 넣어도 0편만 나오던 문제

`topics.yaml`에 주제를 넣었는데 인박스가 계속 "0편"이었다면 이 버그입니다.

| 무엇 | 왜 그랬나 |
|---|---|
| **초록 없는 논문을 전부 버렸다** | OpenAlex는 출판사 라이선스 때문에 상당수 논문의 초록을 주지 않습니다 — 특히 신간이 그렇습니다. API가 25편을 정상으로 돌려줘도 선별 결과가 **0편**이 됐습니다. 이제 초록이 없어도 버리지 않고 뒤로만 밉니다 |
| **조회 실패가 성공으로 처리됐다** | 모든 주제의 조회가 죽어도 종료 코드가 0이라, 인박스엔 "0편"이 적히고 실패 알림 Issue도 안 떴습니다. 이제 전부 실패하면 실패로 끝나고 Issue가 옵니다 |
| **공용 대기열에서 막혔다** | OpenAlex에 이메일을 안 주면 공용 대기열인데 GitHub Actions는 IP를 많이 공유합니다. `topics.yaml`에 `mailto:` 한 줄을 넣으면 여유 있는 대기열로 갑니다. 일시적 오류는 이제 3번까지 다시 시도합니다 |

**가져올 파일**: `scripts/scan_papers.py` · `scripts/test_scan_papers.py`(신규) ·
`.github/workflows/paper-scan.yml` · `topics.yaml`(mailto 주석만 참고, 내 주제는 유지)

가져온 뒤 **Actions → paper-scan → Run workflow**로 즉시 돌려 확인하세요.

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
