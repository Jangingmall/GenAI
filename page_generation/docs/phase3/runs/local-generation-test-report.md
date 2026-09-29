# 로컬 상세페이지 생성 테스트 기록

점검일: 2026-09-08  
실행일: 2026-09-07  
상태: 로컬 smoke test 통과 / 정량 평가 및 상용 게시 승인은 미완료

## 1. 테스트 구성

| 구분 | 설정 |
|---|---|
| 텍스트·비전 분석 | `mlx-community/gemma-4-12b-it-4bit` |
| 기본 이미지 모델 | `mlx-community/flux2-klein-9b-4bit` |
| 이번 테스트 이미지 모델 | `Runpod/FLUX.2-klein-4B-mflux-4bit` |
| 프롬프트 기록 | FastAPI 기본 `local-mlx-gemma-flux-v1`; CLI smoke runner `local-mlx-product-fit-v3-detail-guide` |
| 텍스트 endpoint | `http://127.0.0.1:11234` |
| 4B 이미지 endpoint | `http://127.0.0.1:11235` (테스트 중 임시 기동) |
| 외부 API·검색 | 사용하지 않음 |

기본 서비스 설정은 계속 11234의 Gemma + Flux2 Klein 9B를 사용한다. 이번 4B 검증은
기존 서버에서 4B 이미지 modality가 거절되는 것을 확인한 뒤, 기존 서버를 중단하지 않고
4B 전용 로컬 MLX Serve를 11235에 별도로 기동해 수행했다. 테스트 후 11235 서버는 종료했다.

## 2. 실행 결과

| 케이스 | 입력 | 상세페이지 | 원본 보존 자산 | Flux 4B 생성 자산 | 결과 |
|---|---|---:|---:|---:|---|
| 숨의잔 유리 잔 | `54042bf18d450730cd99f154e4b7137d.jpg` | 774×4,341 / 10섹션 | 3장 fallback | lifestyle 1 + detail 4 | 생성 완료 |
| 수채화 문양 부채 | `shop1_ea2db062a3c5a91aecc2aedd6e5d9c3d.jpg` | 774×4,202 / 10섹션 | 3장 verified | lifestyle 1 + detail 4 | 생성 완료 |

결과 파일:

- [숨의잔 상세페이지](../../../generated/runs/sumeuijan_flux2_klein_4b_dedicated_test/detail_page.png)
- [숨의잔 결과 요약](../../../generated/runs/sumeuijan_flux2_klein_4b_dedicated_test/result_summary.json)
- [부채 상세페이지](../../../generated/runs/shop1_flux2_klein_4b_test/detail_page.png)
- [부채 결과 요약](../../../generated/runs/shop1_flux2_klein_4b_test/result_summary.json)

두 기록 폴더는 React JSON builder가 추가되기 전 생성된 smoke 결과라 `react_document.json`을
포함하지 않는다. 현재 코드를 다시 실행하면 각 output-dir에 `react_document.json`이 함께
생성되며, 신규 실행에서는 schema/tree/alias/image reference 검증 결과도 별도로 확인해야 한다.

두 케이스 모두 `hero`, `packshot`, 대표 `detail`은 최종 상품 근거용 원본 자산으로
분리했고, 생성 자산에는 `asset_mode=generated_scene/generated_view`와
`fidelity_status=GENERATED`를 기록했다. 생성 자산은 배경·활용 장면·참고용 디테일로만
사용한다.

## 3. endpoint 점검

4B 전용 서버에서 다음 이미지 생성 요청이 `200`과 `data[0].b64_json`으로 응답했다.

```text
POST http://127.0.0.1:11235/v1/images/generations
model=Runpod/FLUX.2-klein-4B-mflux-4bit
response_format=b64_json
```

반대로 기존 11234 서버에 4B 모델을 직접 지정한 첫 요청은 `400 Target model does not
support this media modality`를 반환했다. 따라서 4B를 기본값으로 바꾸지 않고, 모델별
image endpoint가 실제로 해당 modality를 제공하는지 먼저 확인하도록 운영 절차를 정리했다.

## 4. 품질 판정과 한계

- 부채 테스트는 부채살의 식물 문양, 검은 손잡이, 노란 파우치가 생성 컷에 대체로 유지됐다.
- 유리 잔 테스트는 생성 컷의 분위기는 사용할 수 있었지만 투명 유리의 형태·굴절은 사람
  검수가 필요하다. 원본 역할 자산이 fallback이면 이를 `VERIFIED`로 승격하지 않는다.
- 두 케이스는 모델 품질의 정량 점수가 아니라 pipeline·endpoint·provenance smoke test다.
- React JSON 출력은 두 기존 폴더의 산출물 판정에 포함되지 않았으므로, 최신 계약 검증을 주장하려면
  동일 입력을 현재 runner로 재실행하고 `react_document.json`과 manifest 연결을 보존해야 한다.
- 생성 컷의 상품 형태·색·구성품 보존율, 문구 사실성, p95 지연시간은 평가셋 전체 실행과
  2인 사람 검수를 거쳐야 한다.
- 4B 전용 서버는 메모리 절약형 임시 검증 경로이며 현재 `.env.example`의 기본 이미지 모델과
  endpoint를 변경하지 않는다.

## 5. 재현 명령

4B 서버를 11235에서 먼저 기동한 뒤 다음 명령을 실행한다.

```bash
PYTHONPATH=.:src .venv/bin/python scripts/runtime/run_local_detail_page.py \
  --image /path/to/shop1_ea2db062a3c5a91aecc2aedd6e5d9c3d.jpg \
  --output-dir generated/runs/shop1_flux2_klein_4b_test \
  --text-provider mlx \
  --text-url http://127.0.0.1:11234 \
  --text-model mlx-community/gemma-4-12b-it-4bit \
  --image-provider mlx \
  --image-url http://127.0.0.1:11235 \
  --image-model Runpod/FLUX.2-klein-4B-mflux-4bit
```

운영 기본값과 모델 변경은 [로컬 LLM 운영 문서](../../phase4/operations/local-llm.md)와
[환경 예제](../../../.env.example)를 따른다.
