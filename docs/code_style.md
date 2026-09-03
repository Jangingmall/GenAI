# 코드 작성 규칙

> 미담 AI 추천 챗봇 · 2인 협업 기준.
> 코드 스타일·구조·네이밍 규칙. (깃허브 워크플로우는 `GIT_GUIDE.md` 참고)

---

## 1. 자동 포매터·린터

사람이 스타일을 신경 쓰지 않고 **도구로 통일**한다. "따옴표 뭐 쓰냐" 같은 논쟁을 없앤다.

### 설치
```bash
pip install black ruff
```

### 사용
```bash
black .          # 포맷 자동 정리 (들여쓰기·줄바꿈·따옴표 통일)
ruff check .     # 린트 검사 (안 쓰는 import, 오류 소지 탐지)
ruff check . --fix   # 자동 수정 가능한 것은 수정
```

> **커밋 전 `black .`을 습관화**하면 두 사람의 코드 스타일이 항상 같아진다.
> 가능하면 에디터에 "저장 시 Black 자동 실행"을 설정해두면 편하다.

---

## 2. 네이밍 규칙

| 대상 | 규칙 | 예시 |
| :--- | :--- | :--- |
| 함수·변수 | `snake_case` | `search_products`, `query_vector` |
| 클래스 | `PascalCase` | `Settings`, `SearchResult` |
| 상수 | `UPPER_CASE` | `EMBED_DIM`, `SIMILARITY_THRESHOLD` |
| 파일·모듈 | `snake_case` | `search.py`, `intent.py` |
| 비공개(내부용) | 앞에 `_` | `_load_env`, `_build_query` |

- 이름은 **의미가 드러나게.** `d`, `tmp`, `data2` 같은 모호한 이름 지양.
- 약어보다 풀어쓰기 (`emb` 보다 `embedding`).

---

## 3. 함수·주석

### 함수
- 함수 하나는 **한 가지 일**만 한다. 너무 길어지면 나눈다.
- 함수에 **짧은 docstring** — 무엇을 하는 함수인지 한 줄.
```python
def search(query: str, top_k: int = 3) -> list[SearchResult]:
    """자연어 질의로 상품을 검색해 상위 top_k개를 반환한다."""
    ...
```

### 주석
- 주석은 **"왜"를 설명**한다. "무엇을" 하는지는 코드가 말해준다.
```python
# 나쁨: i를 1 증가시킨다
i += 1

# 좋음: 0-based 인덱스를 사용자에게 보일 1-based로 맞춘다
rank = i + 1
```
- 코드로 설명 안 되는 배경·이유·주의점만 주석으로 남긴다.

### 타입 힌트
- 함수 인자·반환에 **타입 힌트**를 단다 (가독성·오류 예방).
```python
def rank(candidates: list[dict], threshold: float) -> list[dict]:
```

---

## 4. 파일·구조 규칙

- **파이프라인 단계별로 파일 분리** :
  `intent.py` / `embedding.py` / `search.py` / `ranking.py` / `generate.py`
- 파일 하나가 너무 커지면(대략 300줄 넘으면) 분리를 고려한다.
- **설정값은 하드코딩 금지.** DB 접속·모델명·임계값 등은 `config`/`.env`에서 읽는다.
```python
# 나쁨
conn = psycopg2.connect("host=localhost ... password=1234")

# 좋음
from app.config import settings
conn = psycopg2.connect(settings.dsn())
```
- **매직 넘버 지양.** 의미 있는 숫자는 상수로.
```python
# 나쁨
if score < 0.7: ...

# 좋음
SIMILARITY_THRESHOLD = 0.7
if score < SIMILARITY_THRESHOLD: ...
```

---

## 5. 프롬프트 관리

- 프롬프트를 **코드 곳곳에 흩지 않는다.** 한곳(예: `prompts.py` 또는 별도 파일)에서 관리.
- 단계별로 분리: 의도분류 / 조건추출 / 추천이유 생성 / 후속칩.
- 프롬프트 변경은 커밋으로 이력을 남긴다 (품질에 직접 영향).

---

## 6. import 순서

`ruff`가 자동 정리하지만, 기준은 다음과 같다:
```python
# 1) 표준 라이브러리
import os
from pathlib import Path

# 2) 서드파티
import psycopg2
from sentence_transformers import SentenceTransformer

# 3) 프로젝트 내부
from app.config import settings
from app.pipeline.search import search
```

---

## 7. 체크리스트

커밋 전 확인:
- [ ] `black .`을 돌렸는가
- [ ] `ruff check .`에 문제가 없는가
- [ ] 함수에 docstring·타입 힌트가 있는가
- [ ] 설정값을 하드코딩하지 않고 config에서 읽는가
- [ ] 네이밍이 규칙(snake_case 등)에 맞는가
- [ ] 매직 넘버를 상수로 뺐는가

---