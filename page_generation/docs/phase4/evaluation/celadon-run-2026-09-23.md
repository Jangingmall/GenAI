# 청자 분청 찻잔 실행 기록 — 생성컷 미사용이 재현됐다

> 이 문서는 2026-09-23 시점 기록이다. 이후 상태가 바뀌어도 이 문서는 고치지 않는다.

- 목적: 합죽선에서 관측된 생성컷 미사용이 **다른 품목에서도 재현되는지** 확인
- 입력: 청자 분청 찻잔. 장인 사진 **4장**(`sample2-1`·`-2`·`-3`·`-5`) + 제품명·제작과정·관리법
- 모델: `ddalcu/Qwen3.8-27B-MLX-Serve-4bit`(분석) · `mlx-community/flux2-klein-9b-4bit`(생성), 2단계 교체
- 산출물: `generated/attached/cheongja-buncheong/`

---

## 결론 — 재현됐다. 품목 문제가 아니다

```
774 × 3535 · 8블록
hero → statement → gallery → detail_split → usage_scene → info_table → notice → closing
생성 실패 0건

unused_generated_photo_ids: ['lifestyle-02','detail-02','detail-03','detail-04','detail-05']
```

| | 합죽선 2차 | 청자 찻잔 |
| --- | --- | --- |
| `gallery` 블록 | 있음 | 있음 |
| 모델이 채운 `photo_ids` | `['hero','detail']` | `['hero']` |
| `react_document` 갤러리 이미지 | 2장 | **1장** |
| 렌더된 `gallery.png` 이미지 | 5장 | **5장** |
| **미사용 생성컷** | **5장** | **5장** |

두 품목, 두 레이아웃 원형에서 같은 결과가 나왔다. 특정 사진이나 특정 상품의
문제가 아니라 **구조의 문제**다.

## 1. 페이지 품질 자체는 문제없다

본문은 사진에 붙어 있다. 추출된 특징 4종이 전부 `image-visible` 이다.

```
· 청자빛 유약     [image-visible 0.95]
· 귀얄 붓결       [image-visible 0.85]
· 꽃잎 모양 받침  [image-visible 0.95]
· 붉은 테두리 선  [image-visible 0.90]
```

입력한 관리법 3줄(미지근한 물 헹굼 / 전자레인지·식기세척기 회피 / 급격한 온도 변화 회피)이
`notice` 블록에 그대로 반영됐다. 할루시네이션으로 볼 항목은 없다.

## 2. 무엇이 갈리는가

`react_document` 의 이미지 노드는 4개뿐이고, **생성컷 참조가 하나도 없다.**

```
section-01-hero-image-01          hero
section-03-gallery-image-01       hero        ← 갤러리인데 1장
section-04-detail_split-image-01  detail
section-05-usage_scene-image-01   lifestyle
```

반면 렌더된 `sections/gallery.png` 에는 이미지가 5장 들어 있다. 원본과 FLUX
연출컷이 함께 배치돼 있다.

원인은 두 렌더 경로가 갤러리 사진 집합을 **다른 방식으로** 정한다는 데 있다.

| 경로 | 갤러리 사진을 정하는 방법 | 결과 |
| --- | --- | ---: |
| PNG (`html_renderer.py:358-369`) | 생성컷이 있으면 **모델 출력을 무시하고** detail 슬롯 전체 | 5장 |
| `react_document` (`react_document_builder.py:_photo_ids`) | 모델의 `block.photo_ids` 를 그대로 따름 | 1장 |

즉 **PNG 쪽은 이미 코드가 확정하는 방식으로 동작하고 있었다.**
`react_document` 만 그 정책이 빠져 있다.

## 3. 이 불일치가 왜 문제인가

판매자가 미리보기에서 보는 것은 PNG 다. BE·FE 로 전달돼 실제 상세페이지가 되는
것은 `react_document` 다. 지금 구조에서는 **판매자가 승인한 페이지와 실제로
노출되는 페이지의 사진 구성이 다르다.**

합죽선 때는 5 대 2였고 이번에는 5 대 1이다. 모델이 `photo_ids` 를 적게 채울수록
격차가 벌어진다.

## 4. 채택한 대응 — A안

`generated-photo-usage-2026-09-23.md` 5절의 선택지 중 **A(갤러리 `photo_ids` 를
코드가 확정)** 로 진행하기로 했다. 13차에서 레이아웃 시퀀스에 이미 쓴 방식이다.

새 정책을 만드는 작업이 아니라는 점이 중요하다. `html_renderer` 에 이미 있는
정책을 공용 모듈로 끌어내고 `react_document_builder` 가 같이 쓰게 하는 것이다.
그러면 생성컷 소비와 PNG↔`react_document` 일치가 한 번에 해결된다.

B(사진이 충분하면 생성을 건너뛴다)는 채택하지 않았다. 생성 비용을 아끼는
장점이 있으나, 이번 실행에서 보듯 **생성 자체는 실패 없이 잘 동작한다.**
쓰이지 않는 것이 문제이므로 소비 경로를 고치는 쪽이 맞다.

## 재현

```bash
# 분석 (텍스트 모델)
curl -X POST localhost:8009/internal/v1/ai/detail-page-jobs \
  -H "X-AI-Internal-Token: <토큰>" \
  -F "product_image=@sample2-3.png;type=image/png" \
  -F "product_images=@sample2-1.png" -F "product_images=@sample2-2.png" \
  -F "product_images=@sample2-5.png" \
  -F 'metadata={"product_id":"...","idempotency_key":"...","user_hints":{...}}'

# 모델 교체 후 승인·렌더 (이미지 모델)
curl -X POST localhost:8009/internal/v1/ai/detail-page-renders \
  -H "X-AI-Internal-Token: <토큰>" -F 'metadata=<approve.json' -F "product_image=@..."
```

확인은 `result_summary.json` 의 `detail_page.unused_generated_photo_ids` 와
`react_document.json` 의 `imageId` 참조를 **둘 다** 본다. 상위 `result` 층에도
같은 이름의 필드가 있고 그쪽은 비어 있으니 주의한다.
