# Trend detection: Pull Request 설명

## What

이전 수집 자료와 현재 수집 자료를 주제별로 비교하고, `Emerging`, `Growing`, `Established`, `Cooling`, `Unclear`로 표시하는 Trend Radar를 추가합니다.

## Why

뉴스 항목 수나 키워드 수만으로는 실제 기술·직무 흐름을 판단하기 어렵습니다. 서로 다른 종류의 1차 출처 신호를 비교해, 근거가 약한 경우에는 판단을 보류하도록 했습니다.

## Changes

- 논문·모델·기업·행사·채용·데이터 공개 신호를 주제별로 집계
- 이전·현재 기간의 신호 수와 종류 수 비교
- 근거 기준이 있는 추세 분류 함수와 단위 테스트 추가
- 뉴스레터 Trend Radar의 해석 기준 문서화

## Example Output

`LLM evaluation: previous 4 / current 6 / signal types 2 → Growing`

단, 같은 기간에 수집된 출처가 적다면 `Unclear`로 표시합니다.

## Testing

`python -m unittest discover -s ds-research-radar/tests -v`

9개 테스트로 중복 제거, 점수 계산, 이전·현재 비교, 5개 추세 분류를 확인했습니다.
