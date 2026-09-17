# React JSON 상세페이지 출력 계약

상태: 구현 기준 / 2026-09-08  
소유 경계: AI 서버가 문서 생성·검증, BE가 공개 API·저장, 상품 FE가 React 컴포넌트·CSS·자산 URL을 구현

## 1. 한 줄 요약

AI는 JSX/HTML/CSS 문자열을 보내지 않는다. 검증된 `ApprovedDraftDto`에서 서버가 `tag + props + children`
형태의 제한형 JSON AST인 `react_document`를 결정적으로 조립해 BE에 전달하고, FE는 이를 자체
컴포넌트 allowlist로 렌더링한다.

`page_plan`은 모델이 만드는 편집·하위 호환용 계획이다. FE의 정식 구조 렌더 입력은 `react_document`이며,
HTML/CSS는 승인 후 PNG를 만드는 AI 내부 renderer에서만 사용한다.

## 2. 전달 위치

| 상황 | JSON 경로 | FE/BE 용도 |
|---|---|---|
| 초안 상태 응답 | `draft.react_document` | 초안 미리보기 |
| 초안 저장 응답 | `react_document` | AiFeDraftResponseDto 최상위의 수정된 draft 미리보기 |
| 최종 FE 결과 | `result.detail_page.react_document` | 최종 구조 렌더링·게시 전 검토 |
| AI→BE 적재 metadata | `detail_page.react_document` | BE 저장·감사·재조회 |
| 로컬 CLI 산출물 | `react_document.json` | PNG/sections/photos와 함께 보관하는 디버깅·검증 파일 |

최종 PNG와 React JSON은 서로 대체하지 않는다. PNG는 게시용 이미지 산출물이고, React JSON은 FE가
구조·문구·자산을 재구성할 수 있는 구조 산출물이다.

## 3. 최상위 schema

```json
{
  "schemaVersion": "2.0",
  "canvasWidth": 774,
  "root": [
    {
      "id": "section-01-hero-root",
      "type": "element",
      "tag": "section",
      "props": {
        "variant": "paper",
        "layout": { "display": "stack", "gap": 16, "align": "stretch" }
      },
      "children": [
        {
          "id": "section-01-hero-title",
          "type": "element",
          "tag": "h2",
          "children": [
            { "id": "section-01-hero-title-text", "type": "text", "value": "상품명" }
          ]
        },
        {
          "id": "section-01-hero-figure",
          "type": "element",
          "tag": "figure",
          "children": [
            {
              "id": "section-01-hero-image",
              "type": "element",
              "tag": "img",
              "props": { "imageId": "hero", "alt": "상품명 상품 소개" }
            }
          ]
        }
      ]
    }
  ]
}
```

| 필드 | 타입·제한 | 설명 |
|---|---|---|
| `schemaVersion` | 고정 문자열 `"2.0"` | 계약 버전. 알 수 없는 버전은 렌더하지 않고 호환 오류로 처리 |
| `canvasWidth` | 정수 `1..4096`, 현재 기본 `774` | FE/PNG 기준 폭 |
| `root` | `section` element 1~14개 | 상세페이지의 순서 있는 최상위 섹션 |
| `id` | 영문으로 시작하는 1~80자 unique ID | 노드 추적·diff·접근성 테스트용 |
| `type` | `element` 또는 `text` | discriminator |
| `tag` | 아래 allowlist 중 하나 | FE 컴포넌트 매핑 키 |
| `children` | 재귀 node, element당 최대 50개 | 텍스트·element 자식 |

외부 JSON 키는 camelCase를 사용한다. Python 내부 필드명(`schema_version`, `canvas_width`, `image_id` 등)은
BE/FE 경계에서 alias로 직렬화되어 `schemaVersion`, `canvasWidth`, `imageId`가 된다.

## 4. 허용 범위

### 4.1 태그 allowlist

```text
section, article, div,
h2, h3, h4, p, span, strong, em,
ul, ol, li,
figure, figcaption, img, video, a,
table, caption, thead, tbody, tr, th, td
```

현재 builder는 page-plan block을 `section` 중심으로 조립하며, 이미지 노드는 `figure > img`로 만든다.
생성 여부는 `product_generated` 플래그로 구분하며, `react_document` 내부에는 별도의 `figcaption`(`...-reference-label` 노드)을 붙이지 않는다 (계약 변경: 생성 이미지에 붙이던 `...-reference-label` 노드는 제거됨).
임의 태그, `script`, `style`, `iframe`, form control, SVG 실행 경로는 계약에 없다.

### 4.2 element props

| 그룹 | 허용 필드 | 규칙 |
|---|---|---|
| 공통 | `variant`, `layout`, `style` | 길이·enum·숫자 범위 검증, 알 수 없는 키 거부 |
| 이미지 | `imageId`, `alt`, `crop` | `img`에서만 사용. `img`는 `imageId` 필수·children 금지 |
| 링크 | `href`, `target` | `a`에서만 사용. 내부 상대 경로 또는 HTTPS만 허용 |
| 동영상 | `videoUrl` | `video`에서만 사용. 내부 상대 경로 또는 HTTPS만 허용 |
| 그리드 | `scope`, `colSpan`, `rowSpan` | 허용 enum/범위만 사용 |

`img.props.imageId`는 `hero`, `packshot`, `detail`, `lifestyle` 같은 asset manifest 키다. AI는 실제 CDN URL,
Base64, 파일 경로를 AST에 넣지 않는다. FE가 `photos[]`와 BE asset manifest를 이용해 URL을 해석한다.
해석되지 않는 image ID가 있으면 게시 전 검증을 실패시킨다.

### 4.3 구조화 layout/style

layout은 `stack`, `flex(row|column)`, `grid(columns 1..4)`와 제한된 `gap`, `align`, `wrap`만 사용한다.
style은 색상, 타이포그래피, 여백, border, shadow, `objectFit`, `objectPosition`, rotate, gradient 등
정의된 필드만 사용한다. CSS declaration 문자열, class injection, CSS URL, expression, event handler는
허용하지 않는다.

## 5. 트리·보안 검증

서버의 `ReactDetailPageDocumentDto`가 FE/BE 경계 전에 다음을 검증한다.

- 알 수 없는 top-level·node·props 키 거부(`extra="forbid"`)
- 최상위 1~14개, 전체 최대 300노드, 최대 깊이 20
- 모든 node ID unique 및 허용 패턴
- `ul/ol`의 직접 자식은 `li`, `table`의 직접 자식은 `caption/thead/tbody`
- `thead/tbody`의 직접 자식은 `tr`, `tr`의 직접 자식은 `th/td`
- heading 안 block element 금지, 중첩 `a` 금지
- `img`에 `imageId` 필수·children 금지, 태그별 `alt/crop/videoUrl/href` 사용 범위 준수
- 외부 링크·동영상은 HTTPS만, 내부 자산은 상대 경로만 허용
- 실행 가능한 HTML/JSX/CSS/script/event handler/`dangerouslySetInnerHTML` 구조를 전달하지 않음.
  `text.value`는 text node로만 출력하고 FE가 markup으로 재해석하지 않는다.

검증 실패는 문서를 부분 성공으로 전달하지 않고, 작업 실패 또는 안전한 fallback 대상으로 처리한다.

## 6. 생성·편집·렌더링 흐름

```text
Qwen3.8 27B 분석 (Mac 로컬 MLX Serve 또는 서버 SGLang)
  → ProductProfileDto / page_plan / 카피 검증
  → ApprovedDraftDto
  → React JSON builder + Pydantic tree validation
  → draft.react_document를 BE/FE에 전달
  → 장인 편집·저장(문자열/구조화 draft만)
  → 승인
  → react_document 재조립·검증
  → 내부 HTML/CSS + Playwright
  → 전체 PNG + 섹션 PNG + BE multipart
```

React AST는 모델이 직접 출력하는 별도 자유 형식이 아니다. 따라서 prompt injection이 태그·속성·URL로
그대로 실행될 수 없고, `ApprovedDraftDto`와 page-plan allowlist를 통과한 값만 AST에 반영된다.

## 7. FE 구현 책임

FE는 다음 순서로 처리한다.

1. `schemaVersion`을 확인하고 지원하지 않는 버전은 사용자에게 호환 오류를 표시한다.
2. `root[]`를 순서대로 순회하며 `tag`를 사전 정의된 React component map에 매핑한다.
3. `text.value`는 텍스트 node로 출력하고 HTML 문자열로 재해석하지 않는다.
4. `img`의 `imageId`를 asset manifest에 조회하고, 없는 자산은 렌더하지 않고 오류로 표시한다.
5. `style/layout`은 FE design token으로 매핑한다. raw CSS를 실행하지 않는다.
6. 생성 여부는 `product_generated` 플래그로 구분한다 (`asset_mode=generated_scene/generated_view`).
7. `fidelity_status=REJECTED` 자산은 표시·저장·게시하지 않는다.

AI 서버는 FE component, design token, 공개 asset URL, 공개 인증을 제공하지 않는다. BE가 이를 공개
API 모델로 변환한다.

## 8. 버전·호환 정책

- 현재 계약 버전은 `2.0`이다.
- 필드 추가는 FE가 알 수 없는 키를 무시할지 계약에서 먼저 합의한다. 현재 DTO는 알 수 없는 키를 거부한다.
- 태그·props 의미 변경, image manifest 변경, 노드 규칙 변경은 schema version을 올리고 FE/BE 동시 배포한다.
- `page_plan`은 기존 소비자와 편집 저장을 위해 당분간 함께 보낸다. 제거 시점은 FE/BE 합의와 migration 후 결정한다.
- HTML/CSS renderer의 시각 스타일 변경은 React schema version과 별도이지만, PNG 회귀 테스트를 다시 실행한다.

## 9. 구현·검증 위치

- DTO/validator: [`src/detail_page_ai/react_document.py`](../../src/detail_page_ai/react_document.py)
- builder: [`src/detail_page_ai/react_document_builder.py`](../../src/detail_page_ai/react_document_builder.py)
- pipeline 연결: [`src/detail_page_ai/pipeline.py`](../../src/detail_page_ai/pipeline.py)
- FE/BE DTO 연결: [`src/detail_page_ai/dto.py`](../../src/detail_page_ai/dto.py), [`src/detail_page_ai/fe_dto.py`](../../src/detail_page_ai/fe_dto.py)
- BE metadata 직렬화: [`src/detail_page_ai/backend_client.py`](../../src/detail_page_ai/backend_client.py)
- 로컬 JSON 산출: [`src/local_detail_page_ai/runner.py`](../../src/local_detail_page_ai/runner.py)
- 계약 테스트: [`tests/test_react_document.py`](../../tests/test_react_document.py), [`tests/test_backend_client.py`](../../tests/test_backend_client.py), [`tests/test_local_llm.py`](../../tests/test_local_llm.py)
