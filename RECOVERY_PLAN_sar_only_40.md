# QuakeSight sar_only 回收计划 — 40 个 pre-factor 通过事件

**生成日期**: 2026-06-09
**来源**: 333 个 sar_only 事件经二维 pre-factor checking 筛选
**scorecard**: `scripts/detectability/prefactor_scorecard.json`

---

## 1. 背景与筛选逻辑

333 个 sar_only 事件（有 S1 SAR 覆盖但从未产出 InSAR/GBIS）经过**信号 × 相干性**二维评估：

- **信号轴 (SNR)**: Okada 正演 peak LOS / σ_atm(0.5cm)。Wells-Coppersmith 定尺寸 + 矩平衡定滑动。
- **相干性轴 (COHER)**: Köppen 气候基准 × 地形因子 × 雪季因子。
  - Köppen: A(热带)→0.1, B(干旱)→0.8-0.95, C(温带)→0.4-0.7, D(雪)季节性, E(极地)→0.05-0.3
  - 地形: flat 1.0 / hilly 0.85 / mountainous 0.62 / very_rugged 0.42 / offshore 按 ocean_frac 衰减
  - 雪季: D/E 区 + 当地冷季 → 0.25-0.35

### 决策矩阵结果

| | COH≥0.55 | COH 0.35-0.55 | COH<0.35 |
|---|---|---|---|
| **SNR≥3** | **13 GO** | 6 | 134 ❌ |
| **SNR 1.5-3** | 8 | 3 | 61 ❌ |
| **SNR<1.5** | 10 STACK | 7 | 91 ❌ |

**293 个 NO_GO 死因**: fully marine 112 + 热带 175 + coastal 48 + rugged 48 + snow 7（可叠加）。
221 个（66%）是热带俯冲带/岛弧/深海事件 → C-band 天然盲区，**等 NISAR L-band**。

---

## 2. 可执行池：40 个（分三层）

### Tier 1 — GO (13)：单 pair 应能解，优先批跑
全部干旱区 (Köppen B)，coh 0.58-0.95，SNR 3-18。

| event_id | Mw | depth | Köppen | terrain | coher | SNR |
|---|---|---|---|---|---|---|
| us1000bjnz | 6.1 | 9 | B4 | mountainous | 0.59 | 18 |
| us2000c3mi | 6.0 | 8 | B4 | mountainous | 0.59 | 16 |
| us6000rq2x | 5.5 | 3 | B4 | hilly | 0.81 | 15 |
| us6000rq2y | 5.4 | 3 | B4 | hilly | 0.81 | 12 |
| us10002n4w | 6.4 | 20 | B5 | hilly | 0.79 | 12 |
| us10008ei0 | 6.1 | 13 | B7 | hilly | 0.68 | 10 |
| us2000c3ag | 6.0 | 12 | B5 | mountainous | 0.58 | 9 |
| us6000phrk | 5.7 | 8 | B6 | flat | 0.82 | 7 |
| nc73886731 | 5.5 | 6 | C9 | hilly | 0.58 | 6 |
| usb000smff | 5.7 | 10 | B6 | flat | 0.82 | 5 |
| us10006rrf | 5.6 | 10 | B6 | flat | 0.82 | 3 |
| us6000mjux | 5.3 | 6 | B4 | flat | 0.95 | 3 |
| us20008jcc | 5.3 | 6 | C8 | hilly | 0.59 | 3 |

### Tier 2 — MARGINAL (17)：试单 pair，期望降低
B 区但地形粗糙或信号偏弱 (SNR 1.5-8.4)。Tier 1 跑完后批跑。
`us7000hsg4 us20007z2r us200082s5 us6000rglb us2000bu6g us10008rah us10003qv5 us6000jbsk us6000phnz us6000smm5 us7000k58h nn00495477 us2000hat7 us7000pdu6 nn00782942 us10008s7b us6000gf1y`

### Tier 3 — STACK_ONLY (10)：stacking 真正用武之地
地面相干好 (coh 0.58-0.82, 干旱区) 但信号埋了 (SNR<1.5)，多为 Mw5.5-5.7 @ 20-28km 偏深。
**单 pair 无意义，等 stacking pipeline。** 先记录，不在本批跑。
`us10003xzv us20005bft nn00916980 us10004c96 us20003lsq us60005lrf us6000nq9a us7000s2x6 us10005h1j nc73201181`

---

## 3. 执行步骤（Tier 1 + Tier 2 = 30 个）

### Step 0 — backend 可得性标注（先做，便宜）
对 30 个 event 查：
- LiCSAR 覆盖（用 retries=2 patch 重 probe）→ 有则走 LiCSAR
- 无 LiCSAR → SP v2（这 30 个已过雪/热带筛子，干旱区为主，SP v2 安全）

### Step 1 — InSAR 产出
- LiCSAR-OK: `quakesight insar <id> --licsar-only`
- SP v2 fallback: `quakesight insar <id>`（无 flag）

### Step 2 — GBIS 反演（关键：放宽 strike/dip 先验）
见 §4。串行 driver + auto-kicker watchdog（沿用 `_batch_logs/` 现有脚本）。

### Step 3 — 分级 + 发布
diagnostics_for_agent.json 评级 → GREEN/YELLOW/RED → 更新 catalog → GitHub Pages。

---

## 4. ⚠️ 关键：strike/dip 先验范围要足够大

**问题**: 当前 quakesight 默认 `str_buffer=60°`(±60→120° 范围), `dip_buffer=35°`(±35→70°)。
这批 30 个事件中 **多数 Mw 5.0-6.1，相当一部分 <5.5** —— 按 memory `feedback_usgs_np_unreliable_small_eq`，
**USGS NP 对 M<5.5 不可靠**，只能当 prior 中心，真实节面要靠 GBIS 后验找。窄先验会把链锁死在错误的 USGS 中心附近。

**本批覆盖方案**（写进 retry_overrides.json 或 opts）：

| 参数 | 默认 | 本批建议 | 理由 |
|---|---|---|---|
| `str_buffer` | 60 | **90** | ±90→180° 全覆盖断层走向 + 共轭节面，strike 180° 模糊全包 |
| `dip_buffer` | 35 | **60** | ±60 覆盖近垂直(过-90)到浅倾，dip 自由 |

- strike ±90 = 半圆，无论 USGS NP1 给哪个，真实走向（含共轭）都在范围内。
- dip ±60 配合现有"不在 -90 截断"逻辑（qsGenInputFile L110-118），near-vertical 链可自由穿越。
- 仍保留 `DIP_HI = min(-0.1, ...)` 防止 dip 越 0 翻转 disloc 的 Z 约定。
- **不放宽 L/W**（Phase B 已验证放宽 L/W 对 compound source 无效，会失稳）。

**实现**: 在每个 event 的 `retry_overrides.json` 写
```json
{"str_buffer": 90, "dip_buffer": 60}
```
或在 driver 调 qsRunFullEvent 时传 opts。**不改 skill 默认值**（保持生产稳定，仅本批覆盖）。

---

## 5. 预期回收

| Tier | 数 | 预期 hit (GREEN/YELLOW) | 备注 |
|---|---|---|---|
| GO | 13 | ~8-10 (60-75%) | 干旱区强信号，最高把握 |
| MARGINAL | 17 | ~4-6 (25-35%) | 地形/弱信号拉低 |
| **小计** | **30** | **~12-16** | |
| STACK_ONLY | 10 | 等 stacking | 不在本批 |

**zone=? → YELLOW+ 净回收预估 12-16 个（本批），约占 333 的 4-5%。**
诚实结论：sar_only 池子的天花板就在这里，剩下 293 个非 NISAR 不可。

---

## 6. 风险与 stop-rule

- 单 event GBIS >25min → auto-kicker 杀（沿用 `auto_kicker_mac.sh`）。
- SP v2 unwrap 失败（干旱区偶发，见 memory `us10006jxs` Oklahoma）→ 标 RED，不重试。
- 若 GO tier hit rate <50% → 暂停，先 double-check pre-factor 模型是否高估 coher。
- 每个 QS 调用加 `< /dev/null` 防 stdin-stealing（已知 bug）。
