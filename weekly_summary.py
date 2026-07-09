#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weekly_summary.py  —  주간 순위 변동 요약 생성
────────────────────────────────────────────────
rankings.json + previous_ranks.json 을 비교해서
"이번 주 뭐가 바뀌었나"를 자동으로 정리한다.

결과는 summary.md 파일로 저장되며,
GitHub Actions가 이걸 읽어 Issue로 만들어 너한테 보내준다.

실행: python3 weekly_summary.py
"""

import json
import os
from datetime import date

RANKINGS_FILE = "rankings.json"
PREV_FILE     = "previous_ranks.json"
OUTPUT_FILE   = "summary.md"
CATEGORIES    = ["overall", "text", "coding", "image"]
CAT_NAMES     = {"overall": "종합", "text": "텍스트", "coding": "코딩", "image": "이미지"}


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def analyze():
    rankings = load_json(RANKINGS_FILE)
    prev     = load_json(PREV_FILE)

    if not rankings or not rankings.get("models"):
        return "❌ rankings.json이 없거나 비어 있습니다. 파이프라인을 먼저 실행하세요."

    models = rankings["models"]
    today  = rankings.get("lastUpdated", date.today().isoformat())

    # ── 카테고리별 순위 계산 ──
    def rank_cat(cat):
        have = [(m, m["scores"][cat]) for m in models if m["scores"].get(cat) is not None]
        have.sort(key=lambda x: x[1], reverse=True)
        return have

    sections = []
    total_changes = 0

    for cat in CATEGORIES:
        ranked = rank_cat(cat)
        if not ranked:
            continue

        cat_name = CAT_NAMES[cat]
        changes = []

        for cur_rank, (m, score) in enumerate(ranked, 1):
            prev_rank = m.get("prevRanks", {}).get(cat)
            name = m["name"]
            free = "무료" if m["free"] else "유료"
            arena_rank = m.get("arenaRanks", {}).get(cat)
            arena_str = f" (Arena 전체 {arena_rank}위)" if arena_rank else ""

            if prev_rank is None:
                changes.append(f"  🆕 **{cur_rank}위** {name} [{free}] — 신규 진입{arena_str}")
                total_changes += 1
            elif prev_rank > cur_rank:
                diff = prev_rank - cur_rank
                changes.append(f"  🔼 **{cur_rank}위** {name} [{free}] — {diff}계단 상승 (전주 {prev_rank}위){arena_str}")
                total_changes += 1
            elif prev_rank < cur_rank:
                diff = cur_rank - prev_rank
                changes.append(f"  🔽 **{cur_rank}위** {name} [{free}] — {diff}계단 하락 (전주 {prev_rank}위){arena_str}")
                total_changes += 1
            # 변동 없는 모델은 생략 (변화가 있는 것만 보고)

        if changes:
            sections.append(f"### {cat_name} 부문\n" + "\n".join(changes))

    # ── 무료 vs 유료 톱3 ──
    overall = rank_cat("overall")
    if overall:
        free_top3 = [(r+1, m) for r, (m, s) in enumerate(overall) if m["free"]][:3]
        paid_top3 = [(r+1, m) for r, (m, s) in enumerate(overall) if not m["free"]][:3]

        ft = "\n".join([f"  {r}위 · {m['name']} ({m['scores']['overall']}점)" for r, m in free_top3])
        pt = "\n".join([f"  {r}위 · {m['name']} ({m['scores']['overall']}점)" for r, m in paid_top3])
    else:
        ft = pt = "  (데이터 없음)"

    # ── 매핑 미등록 주요 모델 ──
    mapping_note = ""
    if prev:
        # previous_ranks.json에 있는 모델 수 참고
        mapped_count = len(models)
        mapping_note = f"\n현재 매핑된 모델: **{mapped_count}개**"

    # ── 마크다운 조립 ──
    md = f"""# 📊 AI 리그 주간 순위 변동 리포트

**기준일**: {today}
**변동 감지**: {total_changes}건{mapping_note}

---

## 순위 변동 요약

{"변동 없음 — 이번 주는 순위가 안정적이었습니다." if not sections else chr(10).join(sections)}

---

## 무료 모델 종합 톱 3
{ft}

## 유료 모델 종합 톱 3
{pt}

---

## ✏️ 주간 분석 초안 (여기를 수정하세요)

> 아래는 데이터를 바탕으로 한 초안입니다.
> **이 부분을 직접 수정하거나 그대로 승인**하면 사이트에 반영됩니다.

이번 주 AI 리그 순위에서 주목할 변화는 {'없었습니다. 상위권이 안정적으로 유지되고 있습니다.' if total_changes == 0 else f'총 {total_changes}건의 순위 변동이 감지되었습니다.'}

{'무료 모델 중에서는 ' + free_top3[0][1]["name"] + '이(가) 종합 ' + str(free_top3[0][0]) + '위로 무료 최강 자리를 지키고 있습니다.' if free_top3 else ''}

{'유료 모델에서는 ' + paid_top3[0][1]["name"] + '이(가) 종합 ' + str(paid_top3[0][0]) + '위를 차지했습니다.' if paid_top3 else ''}

각 모델 옆의 "Arena N위"는 우리가 큐레이션한 목록이 아닌 전체 벤치마크 기준 순위입니다.

---

*이 리포트는 자동 생성되었습니다. 위 초안을 검토/수정한 뒤 사이트에 반영해 주세요.*
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"✓ {OUTPUT_FILE} 생성 완료 — 변동 {total_changes}건")
    return md


if __name__ == "__main__":
    analyze()
