# Notion 페이지 구조

## 배치 규칙

사용자가 지정한 상위 페이지 안에만 다음 구조를 둔다.

```text
기준 상위 페이지
└── DS Research Radar
    ├── Language Research
    │   ├── 연구·기술 자료 한눈에 보기 표
    │   └── 논문·기사별 개별 페이지
    ├── Climate Research
    │   ├── 연구·기술 자료 한눈에 보기 표
    │   └── 논문·기관 발표별 개별 페이지
    ├── Industry & Product Signals
    │   ├── 사례·초기 추세 비교 표
    │   └── 기사·기업 운영 사례별 개별 페이지
    ├── DS Career & Skills
    │   ├── 채용 공고
    │   │   └── 한국 근무 신입·인턴 회사·역할별 개별 페이지
    │   └── 역량 & 포트폴리오
    │       └── 포트폴리오 기반 지원 우선순위·공통 역량 페이지
    └── Research Items (선택: 과거 기록 보관용)
```

`DS Research Radar`는 길 안내를 하는 허브다. 읽을 내용은 주제 페이지 아래의 자료별 개별 페이지 본문에 저장한다. Language·Climate 주제 페이지에는 가로 스크롤을 최소화한 4열 이하 비교 표를 먼저 두고, 자료 페이지에는 긴 요약, 직접 링크, 새로움, 한계, 직무 연결점을 적어 표 칸을 펼치지 않아도 읽을 수 있게 한다. `Research Items`가 남아 있다면 새 자료를 저장하는 중심이 아니라, 이전 기록·중복 확인을 위한 보관함이다.

선택적으로 기존 보관 표를 유지할 때만 아래 속성을 사용한다. 실제 데이터베이스에 없는 속성은 사용자의 확인 후 추가한다.

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
| Skills | 다중 선택 | 관련 역량 |
| Trend | 선택 | Emerging / Growing / Established / Cooling / Unclear |

중복 확인은 개별 페이지 본문의 1차 출처 URL을 최우선으로 하고, 논문이면 DOI·arXiv ID, 그다음 정규화 제목+기관을 사용한다.
