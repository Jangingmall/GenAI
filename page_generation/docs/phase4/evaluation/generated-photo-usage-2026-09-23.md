# 생성컷이 쓰이는지 — 합죽선 매화선 2회 실행 기록

> 이 문서는 2026-09-23 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 목적: `usage_scene` + `gallery` 원형 제한(커밋 `97c5f41`)이 **생성컷을 실제로 쓰게 만드는지** 확인
- 입력: 전주 합죽선 매화선. 장인 사진 **4장** + 제품명·제작과정·관리법
- 모델: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`(분석) · `mlx-community/flux2-klein-9b-4bit`(생성), 2단계 교체
- 산출물: `generated/attached/hapjukseon-maehwa/`(1차) · `generated/attached/hapjukseon-maehwa-v2/`(2차)

---

## 결론 — 절반만 통했다

원형 후보 제한으로 **`gallery` 블록은 계획에 들어왔다.** 그러나 **생성컷은 여전히
쓰이지 않는다.** 모델이 `gallery` 의 `photo_ids` 를 규약대로 채우지 않기 때문이다.

| | 1차 (수정 전) | 2차 (수정 후) |
| --- | --- | --- |
| `gallery` 블록 | 없음 | **있음** |
| `gallery` `photo_ids` | — | `['hero','detail']` |
| `react_document` 갤러리 이미지 | — | 2장 |
| **미사용 생성컷** | **5장** | **5장 (변화 없음)** |
| 페이지 | 774 × 3529 · 8블록 | 774 × 4046 · 9블록 |

```
1차 plan: hero → detail_split → statement → usage_scene → wide_image → info_table → notice → closing
2차 plan: hero → statement → detail_split → palette → usage_scene → gallery → recommendation → notice → closing

두 실행 모두 unused_generated_photo_ids:
  ['lifestyle-02','detail-02','detail-03','detail-04','detail-05']
```

---

## 1. 무엇을 기대했나

`prompts.py` 의 규약은 gallery 가 아래 사진을 쓰는 것이다.

```
include exactly one gallery with eyebrow PRODUCT GALLERY and
photo_ids ["detail","detail-02","detail-03","detail-04","detail-05"]
```

생성컷은 `detail-02`~`detail-05` 로 배정되므로, **gallery 가 규약대로 채워지면
생성컷 4장이 소비된다.** 그래서 이미지 생성이 켜질 때 후보 원형을
`usage_scene` + `gallery` 를 모두 가진 것으로 제한했다.

후보 제한 자체는 동작했다. 합죽선 sha256 기준 후보 4종이 전부 조건을 만족한다.

```
texture-macro-led     usage_scene=True  gallery=True
use-scene-led         usage_scene=True  gallery=True
component-assembly    usage_scene=True  gallery=True
tactile-editorial     usage_scene=True  gallery=True
```

## 2. 실제로 무슨 일이 일어났나

모델이 `gallery` 블록을 만들긴 했으나 `photo_ids` 에 **`['hero','detail']` 두 장만**
넣었다. 규약이 지정한 `detail-02`~`detail-05` 가 없다.

그 결과 `react_document` 의 이미지 참조는 이렇다.

```
section-01-hero-root          img 1개 → ['hero']
section-03-detail_split-root  img 1개 → ['detail']
section-04-palette-root       img 1개 → ['detail']
section-05-usage_scene-root   img 1개 → ['lifestyle']
section-06-gallery-root       img 2개 → ['hero','detail']
```

**생성컷 참조가 하나도 없다.** `unused_generated_photo_ids` 가 5장을 미사용으로
집계한 것은 정확하다.

## 3. 따로 확인된 결함 — PNG 와 `react_document` 가 어긋난다

렌더된 갤러리 섹션 PNG(`sections/06-gallery.png`)에는 **이미지가 5장** 들어 있다.
원본 1장과 FLUX 연출컷 4장이 각도별 그리드로 배치돼 있다. 그런데 같은 실행의
`react_document` 의 갤러리 노드에는 **이미지가 2장**뿐이다.

| | 갤러리 이미지 수 |
| --- | ---: |
| 렌더된 PNG | **5장** |
| `react_document` (BE·FE 수신) | **2장** |

두 경로가 사진 집합을 다르게 구성한다. PNG 는 `photo_set` 을 직접 쓰고,
`react_document` 는 블록의 `photo_ids` 를 따른다.

**이것은 생성컷 문제와 별개의 결함이다.** 판매자가 미리보기에서 본 페이지와
실제로 저장·노출되는 페이지의 사진 구성이 다를 수 있다.

## 4. 기록해 둘 관측 오류

작업 중 **"미사용 생성컷 5장 → 0장" 이라고 잘못 보고했다.** 실행 응답에서
`result.unused_generated_photo_ids` 가 `None` 인 것을 "미사용 없음" 으로 읽었으나,
실제 값은 **`result.detail_page.unused_generated_photo_ids`** 에 있었다.

```
result 최상위      unused_generated_photo_ids : None
result.detail_page unused_generated_photo_ids : ['lifestyle-02','detail-02', ...]
```

같은 이름의 필드가 두 층에 있고 위쪽이 비어 있다. 보고 전에 `react_document` 의
실제 이미지 참조로 교차 확인했어야 했다. **집계 필드 하나만 보고 판정하지 말 것.**

## 5. 남은 선택지

생성컷을 실제로 쓰게 하려면 모델의 `photo_ids` 출력에 기대지 않아야 한다.

| 방안 | 내용 | 비고 |
| --- | --- | --- |
| A | gallery 의 `photo_ids` 를 **코드가 확정** | 13차에서 레이아웃 시퀀스에 같은 방식을 쓴 전례가 있다 |
| B | 사진이 충분하면 **생성을 건너뛴다** | 생성 비용(FLUX 5장, 수 분)을 아낀다. 실사 우선 원칙에 부합 |
| C | 현행 유지 | 생성컷은 계속 버려진다 |

`react_document` 와 PNG 불일치(3절)는 위와 무관하게 별도로 정리해야 한다.

## 재현

```bash
# 분석 (텍스트 모델)
curl -X POST localhost:8009/internal/v1/ai/detail-page-jobs \
  -H "X-AI-Internal-Token: <토큰>" \
  -F "product_image=@sample1-3.png;type=image/png" \
  -F "product_images=@sample1-1.png" -F "product_images=@sample1-2.png" \
  -F "product_images=@sample1-5.png" \
  -F 'metadata={"product_id":"...","idempotency_key":"...","user_hints":{...}}'

# 모델 교체 후 승인·렌더 (이미지 모델)
curl -X POST localhost:8009/internal/v1/ai/detail-page-renders \
  -H "X-AI-Internal-Token: <토큰>" -F 'metadata=<approve.json' -F "product_image=@..."
```

확인은 `result_summary.json` 의 `detail_page.unused_generated_photo_ids` 와
`react_document.json` 의 `imageId` 참조를 **둘 다** 본다.
