# Notion 데이터베이스 구조

## 배치 규칙

사용자가 지정한 상위 페이지 안에만 다음 구조를 둔다.

```text
기준 상위 페이지
└── DS Research Radar
    └── Research Items (데이터베이스 표)
```

`Research Items`의 행이 모든 조사 자료의 유일한 저장 위치다. 자료별로 별도 상위 페이지를 만들지 않는다. Language와 Climate는 같은 표 안의 `Domain` 값과 필터 보기로 구분한다.

권장 속성은 아래와 같다. 실제 데이터베이스에 없는 속성은 사용자의 확인 후 추가한다.

| 속성 | 형식 | 의미 |
| --- | --- | --- |
| Title | 제목 | 항목 이름 |
| Domain | 선택 | Language / Climate |
| Type | 선택 | Paper / News / Model / Company / Event / Job / Data Release |
| Organization | 텍스트 | 주관 기관 |
| Published Date | 날짜 | 원문 발표일 |
| Collected Date | 날짜 | 수집일 |
| Topic | 다중 선택 | 세부 주제 |
| Summary | 텍스트 | 사실 중심 요약 |
| What's New | 텍스트 | 새 신호 |
| Compared With | 텍스트 | 비교 대상 |
| DS Relevance Score | 숫자 | 0–100 |
| Evidence Quality | 선택 | High / Medium / Low |
| Skills | 다중 선택 | 관련 역량 |
| Trend | 선택 | Emerging / Growing / Established / Cooling / Unclear |
| Primary Source URL | URL | 1차 출처 |
| Supporting Source URL | URL | 보조 출처 |
| Status | 선택 | New / Reading / Read / Saved / Project Candidate |

중복 확인은 `Primary Source URL`을 최우선으로 하고, 논문이면 DOI·arXiv ID, 그다음 정규화 제목+기관을 사용한다.
