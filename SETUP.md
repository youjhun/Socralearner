# 세팅 — 처음 한 번, 20분

> 이 문서만 따라 하면 **혼자 끝까지** 됩니다. 누구에게 물어볼 필요 없습니다.
> 막히면 맨 아래 [막히는 지점](#막히는-지점)을 보세요. 각 단계 끝에 **"이렇게 되면 성공"**을 적어 뒀습니다.

준비물: GitHub 계정 · ChatGPT 계정(Custom GPT를 직접 만들려면 유료 Plus 필요 — [대안](#chatgpt-plus가-없다면)도 있음)

---

## 1단계 — 내 학습 저장소 만들기 (3분)

1. 이 repo(Socralearner) 페이지 우측 상단의 **`Use this template`** → **`Create a new repository`** 클릭.
   - 버튼이 안 보이면: **Fork**를 눌러도 됩니다.
2. 이름은 아무거나 (예: `my-learning`).
3. **Public / Private 고르기** — 나중에 바꿀 수 있으니 부담 갖지 마세요.

   | | 이럴 때 | 비고 |
   |---|---|---|
   | **Public** (권장) | 그래프 뷰어로 내 상태를 보고 싶다 · 나중에 **"이렇게 공부했습니다"로 보여주고** 싶다(연구실 컨택·포트폴리오) | 학습 기록이라 민감한 내용이 아닙니다 |
   | **Private** | 기록을 아무에게도 안 보이고 싶다 | 그래프 뷰어(7단계)는 못 씁니다. **공부 자체는 똑같이 됩니다** |

   > 그래프 뷰어는 **없어도 되는 편의 기능**입니다. 핵심(AI 세션 + 자동 기록)은 둘 다 동일합니다.

4. 만들어진 내 repo 주소를 기억합니다. 형식: `내아이디/my-learning`

> ✅ **성공**: 내 GitHub에 `STATUS.md`, `daily/`, `mastery.md`가 있는 repo가 생겼다.

---

## 2단계 — Actions 권한 켜기 (1분) ⚠️ 빼먹으면 기록이 안 됩니다

내 repo에서:

1. **Settings** → 왼쪽 메뉴 **Actions** → **General**
2. 맨 위 **Actions permissions**: `Allow all actions and reusable workflows` 선택 → **Save**
3. 아래로 스크롤 → **Workflow permissions**: **`Read and write permissions`** 선택 → **Save**

> ✅ **성공**: Workflow permissions가 "Read and write"로 저장됨.
> (이게 있어야 AI가 남긴 기록을 자동화가 파일로 만들어 커밋할 수 있습니다.)

---

## 3단계 — 토큰(PAT) 발급 (5분)

AI가 내 repo를 읽고 기록을 남기려면 열쇠가 필요합니다.

1. GitHub 우측 상단 프로필 → **Settings** (repo 설정 아님, **계정** 설정)
2. 맨 아래 **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
3. **Generate new token**
   - **Token name**: 아무거나 (예: `socralearner`)
   - **Expiration**: 90일 등 원하는 대로
   - **Repository access**: `Only select repositories` → **1단계에서 만든 내 repo만** 선택
   - **Permissions** → **Repository permissions**에서 딱 2개만:
     - **Contents**: `Read-only`
     - **Issues**: `Read and write`
4. **Generate token** → 나온 문자열(`github_pat_...`)을 복사해 둡니다. **다시 볼 수 없으니** 메모장에 잠깐 붙여넣으세요.

> ✅ **성공**: `github_pat_`로 시작하는 문자열을 손에 들고 있다.

### 이 토큰, 위험하지 않나요?

긴 문자열을 복사해서 붙여넣는 일이 불안하게 느껴지는 건 자연스럽습니다. **실제로 이
토큰이 무엇을 할 수 있는지** 정확히 적어 둡니다.

| 할 수 있는 일 | 할 수 **없는** 일 |
|---|---|
| 위에서 **선택한 repo 하나**의 파일을 읽기 | 다른 repo는 이름조차 볼 수 없음 |
| 그 repo에 Issue를 열고 코멘트 달기 | **코드·파일을 직접 고치거나 커밋하기** (Contents가 읽기 전용) |
| | repo 삭제·공개설정 변경·다른 사람 초대 |
| | 내 GitHub 계정 설정 건드리기 |

가장 나쁜 경우(토큰이 유출)에도 **내 학습 저장소 하나를 읽고 거기 Issue를 남길 수 있는
것이 전부**입니다. 파일을 만드는 것은 AI가 아니라 자동화(CI)이기 때문에, 쓰기 권한을
아예 주지 않아도 기록이 남습니다.

그래도 불안하면:

- **Expiration을 90일로** 두세요. 만료되면 그때 다시 만들면 됩니다(2분).
- **언제든 즉시 끊을 수 있습니다** — GitHub → Settings → Developer settings →
  Fine-grained tokens → 해당 토큰 → **Delete**. 누른 순간 무효가 됩니다.
- 토큰을 새로 만들었다면 GPT의 Actions 인증값도 새 토큰으로 바꿔 주세요.

<details>
<summary>OAuth(로그인 방식)로는 안 되나요?</summary>

됩니다 — Custom GPT의 Actions는 API Key 말고 **OAuth**도 지원하고, GitHub App을
등록하면 "로그인해서 승인" 방식으로 바꿀 수 있습니다. 다만 지금 이 문서에서는
권하지 않습니다:

- GitHub App을 **내가 직접 등록하고 Client Secret을 보관**해야 해서, 혼자 쓰는
  경우엔 단계가 **늘어납니다**(줄지 않습니다).
- 흔히 쓰는 OAuth App(GitHub App이 아닌 쪽)은 권한 단위가 거칠어서 `repo` 하나로
  **내 모든 저장소에 읽기·쓰기**가 열립니다 — 지금의 fine-grained PAT보다 오히려
  넓습니다.
- ChatGPT의 커넥터/앱(MCP) 경로는 쓰기 가능한 커스텀 커넥터가 아직 업무용
  워크스페이스에 한정돼 있고, 하나의 Custom GPT가 Actions와 앱을 **동시에 쓸 수
  없습니다**. 그리고 GitHub의 공식 MCP 서버도 결국 fine-grained PAT으로 인증합니다.

즉 지금 개인 계정에서는 OAuth로 바꿔도 **PAT이 사라지지 않고 설정만 늘어납니다.**
이 방식을 여러 사람에게 배포하게 되는 시점에는 GitHub App + OAuth가 맞고, 그때
이 문서를 갱신합니다.

</details>

---

## 4단계 — 나만의 AI 선생님(Custom GPT) 만들기 (8분)

1. ChatGPT → 왼쪽 사이드바 **GPT 탐색(Explore GPTs)** → 우측 상단 **+ 만들기(Create)**
2. 위 탭에서 **구성(Configure)** 선택 (대화형 말고 이쪽)
3. 칸을 채웁니다:
   - **이름**: `Socralearner` (아무거나)
   - **지침(Instructions)**: 이 repo의 **[`runner/instructions.md`](./runner/instructions.md)** 를 열고, **회색 박스 안 전체**를 복사해 붙여넣기
   - **기능(Capabilities)**: `웹 검색(Web Search)` 체크 (논문·자료 찾을 때 씀)
4. 아래 **Actions** → **Create new action**
   - **Schema**: 이 repo의 **[`runner/action-schema.yaml`](./runner/action-schema.yaml)** 내용을 **전부 복사해 붙여넣기**
   - **Authentication** → `API Key` 선택
     - **Auth Type**: **Bearer**
     - **API Key**: 3단계에서 복사한 `github_pat_...` 붙여넣기
   - 저장
5. 우측 상단 **만들기(Create)** → **나만 사용(Only me)** 으로 저장

> ✅ **성공**: GPT 목록에 내 GPT가 생겼고, Actions에 4개 동작(readFile·createNote·appendNote·closeNote)이 보인다.

---

## 5단계 — 첫 세션 (5분)

만든 GPT를 열고 이렇게 시작합니다:

```
내 repo는 내아이디/my-learning 이야. 오늘 세션 시작.
```

그러면 GPT가:
1. 내 `STATUS.md`를 읽고 (아직 비어 있으면 **목표를 묻습니다**)
2. 목표를 말하면 → 학습 경로를 **가설로** 제안 → 승인하면 시작
3. **"먼저 네 말로 설명해봐"** 라고 합니다 → 모르면 모르는 대로, 아는 만큼 답하세요. **이게 핵심입니다.**
4. 세션이 끝나면 GitHub에 **Issue**로 기록을 남기고 닫습니다.

**목표 예시** (아무 주제나 됩니다):
- "반도체 소자 연구실 인턴 준비 — MOSFET 동작을 스스로 설명할 수 있게"
- "이 논문(링크)을 이해하고 재현하고 싶다"
- "선형대수를 논문 읽을 수준으로"

> ✅ **성공 확인 (중요)**: 내 repo → **Actions** 탭에 워크플로가 돌고, 1~2분 뒤 **`daily/` 폴더에 오늘 날짜 파일**이 생깁니다.
> 그리고 그 **Issue에 자동으로 결과 코멘트**가 달립니다("✅ 학습 노트 기록 완료 …").

---

## 6단계 (선택) — 논문 자동 수집 켜기 (2분)

연구 주제를 따라가는 중이라면, **매주 새 논문**을 자동으로 모아 줄 수 있습니다.

1. repo의 **`topics.yaml`** 을 편집합니다(GitHub 웹에서 연필 아이콘).
2. 예시를 지우고 내 주제를 **영어 query**로 적습니다:
   ```yaml
   topics:
     - id: my-lab
       label: "우리 연구실 주제"
       query: "neural prosthetics implantable electrode decoding"
   ```
3. 커밋하면 끝. 매주 월요일 아침에 돌면서 새 논문이 있으면 **Issue로 알려주고** `papers/inbox.md`에 모읍니다.
4. 지금 당장 확인하려면: **Actions** 탭 → **paper-scan** → **Run workflow**

세션에서 *"이번 주 새 논문 같이 보자"* 라고 하면 러너가 인박스에서 골라 줍니다.

> ✅ **성공**: Actions에서 paper-scan이 초록불이고, `papers/inbox.md`가 갱신된다.
> 💡 주제를 안 쓰면 아무 일도 일어나지 않습니다(안전).

---

## 7단계 (선택) — Topdown 워크스페이스 열기

세션을 몇 번 쌓으면 **Topdown 앱**에서 내 저장소를 그대로 열 수 있습니다:

```
https://<topdown 주소>/workspace/repo/내아이디/my-learning
```

앱 안에서 아무 탭의 **「학습 저장소 연결」** 칸에 `내아이디/my-learning`을 넣어도 같은 곳으로
들어갑니다. 로그인 없이 읽기만 합니다.

화면은 네 단계가 흐름으로 놓여 있습니다 — **논문 → 학습 → 연구 → 산출물**.

| 탭 | 무엇이 보이나 | 어디서 오나 |
|---|---|---|
| **논문** | 내가 올린 원문 자료 · 이번 주 새 논문 · 막힌 개념을 뚫을 자료(위키·영상·무료 강의) | `materials/` · `papers/inbox.md` |
| **학습** | 오늘 할 것 · 내 약점 · 복습 질문 | `STATUS.md` |
| **연구** | 막힌 길목에서 뽑은 재현 실험 | `concepts.json` |
| **산출물** | 노트 | 앱 |

왼쪽에는 **로드맵**과 **지식 그래프**가 항상 붙어 있습니다(어느 탭에 있든). 눌러서 크게 열면:

- 개념 상태 분포 (설명가능 / 암기 / 미학습)
- 🚧 **막힌 길목** — 아직 설명 못 하는데 **다른 개념을 막고 있는** 것

### PDF를 앱에서 바로 올리기

논문 탭 맨 위 **「원문 올리기」** 칸에 PDF를 끌어다 놓으면:

1. **브라우저에서만** 텍스트를 뽑습니다 — 파일은 어디에도 업로드되지 않습니다.
2. 절(section)로 잘라 앱 안에서 읽을 수 있게 합니다.
3. **「[자료] Issue 열기」** 를 누르면 제목이 채워진 Issue 화면이 열립니다. 본문을 붙여넣고
   닫으면 CI가 `materials/`에 파일을 만듭니다.

논문이 길면 본문이 여러 조각으로 나뉩니다 — **첫 조각은 Issue 본문에, 나머지는 코멘트로**
이어 붙이면 됩니다(조각마다 복사 버튼이 있습니다). 원본 PDF는 저장소에 올라가지 않고
**추출된 텍스트만** 남습니다.

> ⚠️ **Public 저장소만 됩니다**(1단계 참고). Private이면 대신 repo의 `concepts.json`을
> 직접 열어봐도 되고, 그냥 안 써도 됩니다 — **공부는 그대로 됩니다.**
>
> 💡 이건 **주 1회쯤 열어보는 거울**입니다. 매일 쓰는 건 GPT 세션이고, 이건
> "지금 뭐가 막혔지"를 한눈에 보려고 가끔 여는 겁니다.

---

## 🗣 세션 시작 문구 모음 (복사해서 쓰세요)

GPT는 **첫 문장으로 어떤 세션인지** 알아듣습니다. 상황별로 이렇게 시작하세요:

| 상황 | 시작 문구 |
|---|---|
| 매일 학습 (기본) | `STATUS.md 읽고 오늘 세션 시작하자.` |
| 논문 한 편 깊이 읽기 | (논문 PDF를 첨부하고) `이 논문 정독하자 — 절 단위로.` |
| 실라버스·강의노트 넣기 | (PDF를 첨부하고) `이 자료 증류해줘 — 요약·개념 지도·빈칸 문제로.` |
| 들은 과목 복원 시작 | `[과목이름] 복원 스캔부터 하자 — 기억나는 대로 설명해볼게.` |
| 이번 주 새 논문 보기 | `papers/inbox.md 읽고 이번 주 논문 같이 골라보자.` (6단계를 켰다면) |
| 막힌 개념 집중 | `막힌 길목부터 하자 — 그래프에서 [개념]이 막혀 있대.` |
| 세션 마무리 | `오늘 세션 마무리하고 기록해줘.` |

> 첫 세션이라면 이 표가 필요 없습니다 — Topdown 사이트의 **시작하기(/start)** ③ 부트 프롬프트가
> 시작 문구를 대신 만들어 줍니다.
> **정독과 학습은 다른 세션입니다** — 논문을 깊이 읽는 날은 정독으로, 개념을 굳히는 날은 기본 세션으로.

---

## 다음부터는

GPT를 열고 **"오늘 세션 시작"** 한 마디면 됩니다. GPT가 알아서 지난 기록을 읽고 이어서 갑니다.
매일 쓰는 법과 기록 읽는 법은 **[`GUIDE.md`](./GUIDE.md)**, 왜 이렇게 공부하는지는 **[`METHOD.md`](./METHOD.md)**.

---

## 막히는 지점

**Q. `Use this template` 버튼이 없어요.**
Fork를 쓰세요. 똑같이 동작합니다.

**Q. Issue는 생겼는데 `daily/`에 파일이 안 생겨요.** ← 가장 흔한 문제
① **2단계(Workflow permissions = Read and write)** 를 했는지 확인하세요. 대부분 이것 때문입니다.
② Issue 제목이 `[학습]`으로 시작하는지 확인 (자동화가 이걸로 걸러냅니다).
③ 그래도 안 되면 그 Issue에 `/기록` 이라고 코멘트를 달면 다시 시도합니다.
④ repo의 **Actions 탭 → 실패한 실행 → 로그**를 보면 이유가 한국어로 나옵니다. 실패하면 Issue에도 자동으로 알려줍니다.

**Q. GPT가 "권한이 없다" 같은 오류를 냅니다.**
PAT 권한을 다시 보세요: **Contents=Read-only, Issues=Read and write**, 그리고 **Repository access에 내 repo가 선택**돼 있어야 합니다. 토큰을 새로 만들었다면 GPT의 Actions 인증값도 새 토큰으로 바꾸세요.

**Q. GPT가 그냥 답을 알려줘요.**
"내가 먼저 설명할게, 답 먼저 주지 마"라고 하세요. 계속 그러면 Instructions가 제대로 안 붙은 겁니다(4-3 확인).

**Q. 기록이 3줄로 짧게만 남아요.**
정상이 아닙니다. Instructions의 쓰기 계약대로 긴 노트는 `appendNote`로 이어 쓰게 되어 있습니다. GPT에게 "노트를 줄이지 말고 전부 기록해"라고 하세요.

### ChatGPT Plus가 없다면
Custom GPT **생성**은 유료지만, **사용**은 무료 계정도 됩니다. 두 가지 방법:
- 누군가 만든 GPT 링크를 받아 쓰되, Actions 인증은 GPT 소유자 것이라 **기록은 그 사람 repo로 갑니다** — 권장하지 않습니다.
- **무료 대안**: 일반 ChatGPT 대화에 [`runner/instructions.md`](./runner/instructions.md)의 회색 박스를 붙여넣고 공부한 뒤, 세션 끝에 GPT가 출력한 노트를 복사해 **내 repo에 직접 Issue로 붙여넣기**(제목은 `[학습] YYYY-MM-DD slug — 제목`). 자동화는 똑같이 돌아 파일을 만들어 줍니다.
