# 이전 계약 폐기 안내

폐기 기준일: 2026-09-08

이 문서는 이전의 `/ai/products`·최상위 `imageId`·HTML block 배열 계약을 기록한 문서입니다.
현재 활성 계약으로 사용하지 않습니다.

현재 `imageId`는 `react_document` 내부 `img.props.imageId`의 안전한 자산 참조로만 사용하며,
예전 계약의 최상위 필드나 임의 URL/HTML 의미로 사용하지 않습니다.

현재 생성형 AI 팀의 계약은 다음 문서를 기준으로 합니다.

- [AI-FE / AI-BE DTO 계약](ai-dto-contract.md)
- [FE 입출력 연결 명세](ai-fe-io-spec.md)

현재 기준은 `FE → 상품 BE → AI → 상품 BE → FE`이며, AI는 다음을 제공합니다.

- 실행 가능한 HTML/JSX 대신 `draft`와 검증된 `react_document` 구조화 JSON
- 이미지 분석 결과와 사실 기반 상품·공예 문구
- 승인 후 최종 `image/png` 및 순서가 있는 섹션 PNG
- `product_id`, `job_id`, `generation_id` 기반의 AI-BE 상태·적재 계약

실제 상품 BE API, DB, S3/SQS/IAM 인프라는 상품 BE/인프라 팀의 책임입니다.
