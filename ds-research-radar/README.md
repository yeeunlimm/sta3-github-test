# DS Research Radar

`ds-research-radar`는 언어 AI와 기후·환경 AI를 따로 조사해 데이터 사이언티스트 관점의 뉴스레터를 만드는 Codex 스킬 프로젝트입니다.

## 핵심 약속

- 1차 출처를 우선합니다.
- Notion에 이미 있는 같은 자료는 다시 저장하지 않습니다.
- Notion의 기준 상위 페이지 안에서 `DS Research Radar` → 주제별 페이지 → 자료별 개별 페이지 구조로 저장합니다.
- 과거 자료는 최신 신호를 이해하는 연구 계보일 때만 짧게 씁니다.
- 언어 AI와 기후·환경 AI를 섞지 않습니다.
- 근거가 부족하면 항목을 만들지 않습니다.

## 사용 예

`$ds-research-radar 언어 AI의 최근 모델·논문·채용 신호를 조사해서 Notion 중복을 제외한 뉴스레터를 만들어줘.`

## 검사

PowerShell에서 아래 명령으로 결정적인 계산 도구를 확인합니다.

`python -m unittest discover -s tests -v`

## 빠른 주간 후보 수집

여러 RSS/Atom 주소를 동시에 읽어 최근 7일의 **후보만** 만듭니다. 결과는 사람이 검토하기 전까지 Notion이나 Slack으로 보내지지 않습니다. 생성되는 후보 파일은 Git에 올리지 않습니다.

```powershell
python scripts/weekly_candidates.py `
  --feed "GeekNews=https://news.hada.io/rss/news" `
  --cache output/weekly-cache.json `
  --output output/weekly-candidates.json `
  --wordcloud output/industry-wordcloud.svg `
  --industry-source GeekNews `
  --approval-file output/approval.json `
  --decision-file output/decisions.json `
  --watchlist-file output/watchlist.json
```

- `weekly-candidates.json`: 최근 7일·중복 제거·관련성 필터를 통과한 검토 후보와 제외 사유 개수
- `weekly-candidates.json`의 각 후보: 통과 후보만 읽은 원문 발췌, 원문 근거 상세 요약 초안, Codex용 상세 요약 프롬프트. 실제 해석은 원문을 검토하는 Codex 단계에서 생성합니다.
- `approval.json`: 예은 님이 남기기로 확인한 URL만 넣는 파일입니다. 예: `{ "approved_urls": ["https://example.com/article"] }`
- `decisions.json`: 검토 상태·이유·실행 가능성 근거를 기록합니다. 예: `{ "decisions": { "https://example.com/article": { "status": "approved", "reason": "기후 시계열 포트폴리오와 직접 연결", "code_available": true, "public_data": true, "modest_compute": true, "portfolio_fit": true } } }`
- `watchlist.json`: 다음 수집에서 특별히 표시할 기관·주제·행사입니다. 예: `{ "terms": ["ECMWF", "LLM evaluation", "ACL"] }`
- `industry-wordcloud.svg`: Industry & Product Signals에서 **승인된** 원문 읽기 완료 자료만 반영한 단어 구름. 승인 자료가 없으면 빈 결과를 분명하게 표시
- `weekly-cache.json`: 다음 실행에서 이미 본 항목을 다시 후보로 내지 않기 위한 식별값

후보 보고서는 `possible_event_clusters`로 제목이 유사한 자료를 **검토용 묶음**으로 제안합니다. 서로 다른 사건을 잘못 합치지 않도록 자동 삭제하지 않습니다. 상세 요약 프롬프트에는 `Why now?` 항목도 포함됩니다.
