#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rankings.py  —  AI 리그 데이터 파이프라인 (실제 Arena 데이터 연결본)
────────────────────────────────────────────────────────────
소스: lmarena-ai/leaderboard-dataset  (Hugging Face, cc-by-4.0)
확인된 스키마: model_name, organization, license, rating, rank,
              category, leaderboard_publish_date  (외 신뢰구간/표차)

구조(관심사 분리):
  1) fetch_raw_scores()  → Arena에서 점수+조직을 내려받음 (네트워크)
  2) load_mapping()      → product_mapping.json (네가 관리, 무료/유료 등)
  3) assemble()          → 둘을 합쳐 순위/변동 계산 (순수 함수, 네트워크 무관)
  4) build()             → 위를 엮어 rankings.json 출력 (오케스트레이션)

실행:
  pip install "datasets>=2.19" pandas       # 최초 1회
  python3 build_rankings.py                 # 실제 데이터로 rankings.json 생성
────────────────────────────────────────────────────────────
"""

import json
import os
from datetime import date

# 웹사이트 탭과 1:1 대응하는 카테고리
CATEGORIES = ["overall", "text", "coding", "image"]

# ── 각 탭을 Arena의 어느 (arena=subset, category) 에서 가져올지 지정 ──
#   overall/text 는 스키마·데이터로 '확인됨'.
#   coding(webdev=Code Arena), image(text_to_image) 는 카테고리 값이
#   'overall'이 맞는지 Data Studio 뷰어에서 한 번 확인 권장(대개 동일).
CATEGORY_SOURCES = {
    "overall": ("text_style_control", "overall"),   # 확인됨 (스타일 보정된 텍스트 종합)
    "text":    ("text",               "overall"),   # 확인됨 (원본 텍스트 종합)
    "coding":  ("webdev",             "overall"),    # webdev = Code Arena / 값 확인 권장
    "image":   ("text_to_image",      "overall"),    # 이미지 생성 / 값 확인 권장
}

# ── organization → (표시 제조사, 브랜드색). Arena가 채워주는 부분 ──
PROVIDER_META = {
    "anthropic": ("Anthropic", "#E8825A"),
    "openai":    ("OpenAI",    "#10A37F"),
    "google":    ("Google",    "#4DA3FF"),
    "meta":      ("Meta",      "#0866FF"),
    "alibaba":   ("Alibaba",   "#C084FC"),
    "moonshot":  ("Moonshot",  "#6C7BFF"),
    "minimax":   ("MiniMax",   "#3DDCC8"),
    "xai":       ("xAI",       "#B7BDD6"),
    "zai":       ("Z.ai",      "#7CE0FF"),
    "deepseek":  ("DeepSeek",  "#6C7BFF"),
}
DEFAULT_COLOR = "#9A957F"

DATASET      = "lmarena-ai/leaderboard-dataset"
MAPPING_FILE = "product_mapping.json"
STATE_FILE   = "previous_ranks.json"
OUTPUT_FILE  = "rankings.json"


# ════════════════════════════════════════════════════════════
# 순수 헬퍼: Arena 행들 → { 모델: {카테고리: 점수} }, { 모델: 조직 }
#   네트워크와 분리돼 있어 샘플 데이터로도 테스트 가능.
# ════════════════════════════════════════════════════════════
def rows_to_scores_orgs(rows, category_key, scores=None, orgs=None, aranks=None):
    scores = scores if scores is not None else {}
    orgs   = orgs   if orgs   is not None else {}
    aranks = aranks if aranks is not None else {}   # Arena 전체 등수
    for r in rows:
        model = r["model_name"]
        scores.setdefault(model, {})[category_key] = round(r["rating"])  # 1505.48 → 1505
        orgs[model] = r.get("organization", "")
        if r.get("rank") is not None:
            aranks.setdefault(model, {})[category_key] = r["rank"]       # Arena가 매긴 진짜 등수
    return scores, orgs, aranks


# ════════════════════════════════════════════════════════════
# 1) 점수 가져오기 — 실제 Arena 다운로드
#    각 카테고리 소스마다 latest 스냅샷을 받아 rows_to_scores_orgs로 누적.
# ════════════════════════════════════════════════════════════
def fetch_raw_scores():
    from datasets import load_dataset   # 무거우니 함수 안에서 import
    scores, orgs, aranks = {}, {}, {}
    for cat, (subset, category_value) in CATEGORY_SOURCES.items():
        ds = load_dataset(
            DATASET, subset, split="latest",
            filters=[("category", "==", category_value)],
        )
        rows = [dict(model_name=r["model_name"],
                     organization=r.get("organization", ""),
                     rating=r["rating"],
                     rank=r.get("rank")) for r in ds]
        rows_to_scores_orgs(rows, cat, scores, orgs, aranks)
        print(f"  · {cat:<7} ← {subset}/{category_value}: {len(rows)}개 모델")
    return scores, orgs, aranks


# ════════════════════════════════════════════════════════════
# 2) 매핑 불러오기 ('_' 로 시작하는 주석 키는 무시)
# ════════════════════════════════════════════════════════════
def load_mapping():
    with open(MAPPING_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


# 한 카테고리에서 점수 내림차순 등수 → { 모델: 등수 }
def rank_within_category(merged, category):
    have = [(m, x) for m, x in merged.items() if x["scores"].get(category) is not None]
    have.sort(key=lambda kv: kv[1]["scores"][category], reverse=True)
    return {m: i + 1 for i, (m, _x) in enumerate(have)}


def load_previous_ranks():
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_current_ranks(ranks_by_cat):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(ranks_by_cat, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════
# 3) 합치기 + 순위/변동 계산 (순수 함수)
#    입력: 점수, 조직, 매핑, 어제순위 → 출력: 결과JSON 등
# ════════════════════════════════════════════════════════════
def assemble(scores, orgs, aranks, mapping, prev):
    merged, missing = {}, []
    for model, cat_scores in scores.items():
        if model not in mapping:
            missing.append(model)          # 점수는 있는데 매핑 없음 = 추가 필요
            continue
        provider, color = PROVIDER_META.get(orgs.get(model, ""),
                                             (orgs.get(model, "").title() or "기타", DEFAULT_COLOR))
        info = mapping[model]
        merged[model] = {
            "id": model,
            "name": info.get("name", model),
            "provider": provider,          # Arena에서 자동
            "color": color,                # Arena 조직 → 색 자동
            "product": info["product"],    # 너가 관리
            "free": info["free"],          # 너가 관리
            "access": info["access"],      # 너가 관리
            "scores": {c: cat_scores.get(c) for c in CATEGORIES},
            "arenaRanks": {c: aranks.get(model, {}).get(c) for c in CATEGORIES},  # Arena 전체 등수
        }
    stale = [m for m in mapping if m not in scores]   # 매핑엔 있는데 점수 사라짐

    ranks_by_cat = {c: rank_within_category(merged, c) for c in CATEGORIES}
    for model, x in merged.items():
        x["prevRanks"] = {
            c: (None if x["scores"][c] is None else prev.get(c, {}).get(model))
            for c in CATEGORIES
        }

    output = {"lastUpdated": date.today().isoformat(), "models": list(merged.values())}
    return output, ranks_by_cat, missing, stale


# ════════════════════════════════════════════════════════════
# 4) 전체 실행
# ════════════════════════════════════════════════════════════
def build():
    print("Arena 데이터 내려받는 중…")
    scores, orgs, aranks = fetch_raw_scores()
    mapping = load_mapping()
    prev = load_previous_ranks()

    output, ranks_by_cat, missing, stale = assemble(scores, orgs, aranks, mapping, prev)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    save_current_ranks(ranks_by_cat)

    print(f"  ✓ {OUTPUT_FILE} 생성 — 사이트에 실릴 모델 {len(output['models'])}개")
    if missing:
        print(f"  ⚠ 매핑 없음(추가 후보): {', '.join(sorted(missing)[:12])}"
              + (f" 외 {len(missing)-12}" if len(missing) > 12 else ""))
    if stale:
        print(f"  ℹ 점수 사라짐(확인): {', '.join(stale)}")
    return output


if __name__ == "__main__":
    build()
