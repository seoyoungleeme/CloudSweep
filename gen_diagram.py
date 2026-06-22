import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrow
import matplotlib as mpl

mpl.rcParams['font.family'] = 'Malgun Gothic'
mpl.rcParams['axes.unicode_minus'] = False

# ─── Color palette ────────────────────────────────────────────────────
C_INPUT   = "#D6EAF8"   # light blue
C_LG      = "#EBF5FB"   # very light blue (LangGraph bg)
C_NODE    = "#AED6F1"   # LangGraph step box
C_A       = "#D5F5E3"   # RuleEngine (green)
C_B       = "#FCF3CF"   # Python (yellow)
C_C       = "#FDEDEC"   # GenAI (pink-red)
C_D       = "#F5EEF8"   # Claude Skill (purple)
C_OUT     = "#EAECEE"   # output box
C_EDGE    = "#5D6D7E"   # arrow color
C_RULE    = "#FEF9E7"   # Rule v2 panel

FONT_SM  = 7.5
FONT_MD  = 8.5
FONT_LG  = 10.5
FONT_TL  = 12

def box(ax, x, y, w, h, color, label, fontsize=FONT_MD, bold=False,
        radius=0.015, edgecolor="#888888", labelcolor="black", wrap=None):
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0.0,rounding_size={radius}",
                       facecolor=color, edgecolor=edgecolor, linewidth=0.8, zorder=3)
    ax.add_patch(p)
    weight = "bold" if bold else "normal"
    txt = wrap if wrap else label
    ax.text(x + w/2, y + h/2, txt,
            ha="center", va="center", fontsize=fontsize, fontweight=weight,
            color=labelcolor, zorder=4, linespacing=1.4)

def arrow(ax, x0, y0, x1, y1, color=C_EDGE, style="->", lw=1.0):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw), zorder=5)

def section_header(ax, x, y, w, h, title, color):
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle="round,pad=0.0,rounding_size=0.01",
                       facecolor=color, edgecolor="#777777", linewidth=1.0, zorder=2)
    ax.add_patch(p)
    ax.text(x + w/2, y + h - 0.012, title,
            ha="center", va="top", fontsize=FONT_LG, fontweight="bold",
            color="#2C3E50", zorder=4)

# ─── Figure ───────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(18, 13))
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
fig.patch.set_facecolor("#FAFAFA")

# ══════════════════════════════════════════════════════════════════════
# TITLE
# ══════════════════════════════════════════════════════════════════════
ax.text(0.5, 0.975, "CloudSweep — 전체 분석 로직 구조",
        ha="center", va="top", fontsize=15, fontweight="bold", color="#1A252F")

# ══════════════════════════════════════════════════════════════════════
# SECTION 1 — INPUTS  (y=0.88~0.94)
# ══════════════════════════════════════════════════════════════════════
S1_Y, S1_H = 0.875, 0.075
section_header(ax, 0.02, S1_Y, 0.96, S1_H, "", C_INPUT)
ax.text(0.5, S1_Y + S1_H - 0.010, "입력 파일  (모두 선택 사항)", ha="center", va="top",
        fontsize=FONT_LG, fontweight="bold", color="#1A5276")

inputs = [
    ("main.tf", "Terraform\n리소스 블록"),
    ("metrics.json", "CloudWatch\n지표 시계열"),
    ("cost_report.json", "AWS Cost\nExplorer"),
    ("genai_evidence.json", "Bedrock / SageMaker\n/ EC2 GPU 관측값"),
    ("result/{domain}\n_skill_analysis.json", "Claude Skill\n선행 분석 결과"),
]
IW, IH = 0.16, 0.045
gap = (0.92 - IW * len(inputs)) / (len(inputs) + 1)
ix_start = 0.04
for i, (fname, desc) in enumerate(inputs):
    ix = ix_start + gap * (i + 1) + IW * i
    iy = S1_Y + 0.010
    box(ax, ix, iy, IW, IH, "white", "", fontsize=FONT_SM,
        edgecolor="#2980B9", radius=0.012)
    ax.text(ix + IW/2, iy + IH * 0.70, fname,
            ha="center", va="center", fontsize=FONT_SM, fontweight="bold", color="#1A5276", zorder=5)
    ax.text(ix + IW/2, iy + IH * 0.28, desc,
            ha="center", va="center", fontsize=6.5, color="#555555", zorder=5)

arrow(ax, 0.5, S1_Y, 0.5, S1_Y - 0.012, lw=1.5)

# ══════════════════════════════════════════════════════════════════════
# SECTION 2 — LANGGRAPH PIPELINE  (y=0.74~0.87)
# ══════════════════════════════════════════════════════════════════════
S2_Y, S2_H = 0.735, 0.132
section_header(ax, 0.02, S2_Y, 0.96, S2_H, "", "#D4E6F1")
ax.text(0.5, S2_Y + S2_H - 0.010, "LangGraph 파이프라인", ha="center", va="top",
        fontsize=FONT_LG, fontweight="bold", color="#1A5276")

lg_steps = [
    ("① Evidence\nInventory", "존재 파일 목록"),
    ("② Execution\nPlan", "분석 경로 결정"),
    ("③ Domain\nDetection", "18개 도메인\n관련성 탐지"),
    ("④ Domain\nAnalysis", "도메인별\n병렬 fan-out"),
    ("⑤ Collect\nResults", "finding 집계\nTF 패치 생성"),
    ("⑥ MCP\nEnrichment", "실시간 AWS\n가격·문서"),
    ("⑦ Cross-Domain\nReview", "교차 패턴\n확인"),
    ("⑧ Report\nGeneration", "state.json\n저장"),
]
NW, NH = 0.100, 0.075
ng = (0.92 - NW * len(lg_steps)) / (len(lg_steps) + 1)
nx_start = 0.04

node_centers = []
for i, (step, sub) in enumerate(lg_steps):
    nx = nx_start + ng * (i + 1) + NW * i
    ny = S2_Y + 0.025
    box(ax, nx, ny, NW, NH, C_NODE, "", fontsize=FONT_SM,
        edgecolor="#2471A3", radius=0.012)
    ax.text(nx + NW/2, ny + NH * 0.65, step,
            ha="center", va="center", fontsize=FONT_SM, fontweight="bold", color="#1A5276", zorder=5)
    ax.text(nx + NW/2, ny + NH * 0.22, sub,
            ha="center", va="center", fontsize=6.2, color="#555555", zorder=5)
    node_centers.append((nx + NW/2, ny + NH/2))

for i in range(len(node_centers) - 1):
    x0, y0 = node_centers[i]
    x1, y1 = node_centers[i+1]
    arrow(ax, x0 + NW/2, y0, x1 - NW/2, y1, lw=1.0)

# Interrupt annotation
int_x = node_centers[4][0]
ax.text(int_x, S2_Y + 0.006, "⚠ HIGH+LOW confidence\n→ interrupt 대기",
        ha="center", va="bottom", fontsize=6.0, color="#922B21",
        bbox=dict(fc="#FDEDEC", ec="#E74C3C", boxstyle="round,pad=0.3", lw=0.7))

arrow(ax, 0.5, S2_Y, 0.5, S2_Y - 0.012, lw=1.5)

# ══════════════════════════════════════════════════════════════════════
# SECTION 3 — DOMAIN ANALYSIS METHODS (y=0.355~0.73)
# ══════════════════════════════════════════════════════════════════════
S3_Y, S3_H = 0.350, 0.378
section_header(ax, 0.02, S3_Y, 0.96, S3_H, "", "#EAFAF1")
ax.text(0.5, S3_Y + S3_H - 0.010, "④ Domain Analysis — 4가지 분석 방식",
        ha="center", va="top", fontsize=FONT_LG, fontweight="bold", color="#145A32")

COL_Y = S3_Y + 0.018
COL_H = S3_H - 0.048
COL_W = 0.215
cols = [0.030, 0.258, 0.485, 0.712]

# ─── Method A ─────────────────────────────────────────────────────────
ax.add_patch(FancyBboxPatch((cols[0], COL_Y), COL_W, COL_H,
             boxstyle="round,pad=0.0,rounding_size=0.012",
             facecolor=C_A, edgecolor="#1E8449", linewidth=1.2, zorder=2))
ax.text(cols[0]+COL_W/2, COL_Y+COL_H-0.010, "방식 A — RuleEngine",
        ha="center", va="top", fontsize=FONT_MD, fontweight="bold", color="#145A32", zorder=4)
ax.text(cols[0]+COL_W/2, COL_Y+COL_H-0.030, "8개 도메인",
        ha="center", va="top", fontsize=FONT_SM, color="#145A32", zorder=4)

a_domains = ["cloudwatch  C1", "cw-alarm  M1, M2",
             "sqs  Q1", "kinesis  K1 / K5(B)",
             "ebs  S1 / S2(B)", "nat  N1",
             "tgw  T2", "organizations  O1"]
for i, d in enumerate(a_domains):
    ax.text(cols[0]+0.012, COL_Y+COL_H-0.060 - i*0.030, f"• {d}",
            va="top", fontsize=FONT_SM, color="#1A5631", zorder=4)

ax.text(cols[0]+COL_W/2, COL_Y + 0.045,
        "_findings_from_engine()\n→ predicate 평가\n→ blocker 집행\n→ savings_fraction 계산",
        ha="center", va="bottom", fontsize=6.3, color="#0E6655", zorder=4,
        bbox=dict(fc="white", ec="#1E8449", boxstyle="round,pad=0.4", lw=0.7))
ax.text(cols[0]+0.005, COL_Y+0.006, "(B) = Blocker",
        fontsize=6.0, color="#666666", zorder=4)

# ─── Method B ─────────────────────────────────────────────────────────
ax.add_patch(FancyBboxPatch((cols[1], COL_Y), COL_W, COL_H,
             boxstyle="round,pad=0.0,rounding_size=0.012",
             facecolor=C_B, edgecolor="#D4AC0D", linewidth=1.2, zorder=2))
ax.text(cols[1]+COL_W/2, COL_Y+COL_H-0.010, "방식 B — Python 직접",
        ha="center", va="top", fontsize=FONT_MD, fontweight="bold", color="#7D6608", zorder=4)
ax.text(cols[1]+COL_W/2, COL_Y+COL_H-0.030, "3개 도메인",
        ha="center", va="top", fontsize=FONT_SM, color="#7D6608", zorder=4)

b_items = [
    ("lambda", "LAMBDA_RIGHTSIZE_POLICY:L1",
     "p99 / allocated_mb < 0.2\n→ _next_lambda_memory(p99)"),
    ("s3", "S3_LIFECYCLE_POLICY:V1",
     "lifecycle config가 버킷\n참조하는지 교차 검색"),
    ("dynamodb", "DYNAMODB_CAPACITY_POLICY:D1",
     "read_p99 / read_cap &\nwrite_p99 / write_cap"),
]
b_y = COL_Y + COL_H - 0.062
for dname, rid, logic in b_items:
    ax.text(cols[1]+0.010, b_y, dname,
            fontsize=FONT_SM, fontweight="bold", color="#6E2F0A", va="top", zorder=4)
    ax.text(cols[1]+0.010, b_y - 0.020, rid,
            fontsize=6.2, color="#5D6D7E", va="top", zorder=4, family="monospace")
    ax.text(cols[1]+0.010, b_y - 0.038, logic,
            fontsize=6.0, color="#333333", va="top", zorder=4)
    b_y -= 0.098

# ─── Method C ─────────────────────────────────────────────────────────
ax.add_patch(FancyBboxPatch((cols[2], COL_Y), COL_W, COL_H,
             boxstyle="round,pad=0.0,rounding_size=0.012",
             facecolor=C_C, edgecolor="#E74C3C", linewidth=1.2, zorder=2))
ax.text(cols[2]+COL_W/2, COL_Y+COL_H-0.010, "방식 C — GenAI Python",
        ha="center", va="top", fontsize=FONT_MD, fontweight="bold", color="#7B241C", zorder=4)
ax.text(cols[2]+COL_W/2, COL_Y+COL_H-0.030, "3개 도메인  (genai_evidence.json 기반)",
        ha="center", va="top", fontsize=6.2, color="#7B241C", zorder=4)

c_items = [
    ("bedrock  B1~B4", "token 대비 commitment 손익분기\ncache read rate, 유사 질문 비율"),
    ("sagemaker  SM1~SM4", "autoscaling 존재, off-hours 스케줄\nGPU 사용률 p95"),
    ("ec2 (GPU)  G1~G4", "스케줄 부재, dev/training idle\nASG fixed capacity, 잔여 비용"),
]
c_y = COL_Y + COL_H - 0.062
for dname, logic in c_items:
    ax.text(cols[2]+0.010, c_y, dname,
            fontsize=FONT_SM, fontweight="bold", color="#7B241C", va="top", zorder=4)
    ax.text(cols[2]+0.010, c_y - 0.022, logic,
            fontsize=6.0, color="#333333", va="top", zorder=4)
    c_y -= 0.095

ax.text(cols[2]+COL_W/2, COL_Y + 0.030,
        "savings_group 별 최댓값만\n최종 합산에 포함",
        ha="center", va="bottom", fontsize=6.3, color="#7B241C", zorder=4,
        bbox=dict(fc="white", ec="#E74C3C", boxstyle="round,pad=0.4", lw=0.7))

# ─── Method D ─────────────────────────────────────────────────────────
ax.add_patch(FancyBboxPatch((cols[3], COL_Y), COL_W, COL_H,
             boxstyle="round,pad=0.0,rounding_size=0.012",
             facecolor=C_D, edgecolor="#8E44AD", linewidth=1.2, zorder=2))
ax.text(cols[3]+COL_W/2, COL_Y+COL_H-0.010, "방식 D — Claude Skill",
        ha="center", va="top", fontsize=FONT_MD, fontweight="bold", color="#4A235A", zorder=4)
ax.text(cols[3]+COL_W/2, COL_Y+COL_H-0.030, "+ Python fallback  /  4개 도메인",
        ha="center", va="top", fontsize=6.2, color="#4A235A", zorder=4)

d_items = [
    ("rds", "R1~R6", 2, 6),
    ("elb", "LB1~LB5", 4, 5),
    ("ecs", "E1~E4", 3, 4),
    ("elasticache", "EC1~EC5", 5, 5),
]
d_y = COL_Y + COL_H - 0.065
for dname, rules, py_n, total in d_items:
    ax.text(cols[3]+0.010, d_y, f"{dname}  {rules}",
            fontsize=FONT_SM, fontweight="bold", color="#4A235A", va="top", zorder=4)
    ax.text(cols[3]+0.010, d_y - 0.020,
            f"Python stub: {py_n}/{total}규칙  →  Skill이 나머지 커버",
            fontsize=6.0, color="#666666", va="top", zorder=4)
    d_y -= 0.075

ax.text(cols[3]+COL_W/2, COL_Y + 0.052,
        "skill_analysis.json\n존재하면 로드\n없으면 Python fallback",
        ha="center", va="bottom", fontsize=6.3, color="#4A235A", zorder=4,
        bbox=dict(fc="white", ec="#8E44AD", boxstyle="round,pad=0.4", lw=0.7))

arrow(ax, 0.5, S3_Y, 0.5, S3_Y - 0.012, lw=1.5)

# ══════════════════════════════════════════════════════════════════════
# SECTION 4 — RULE v2 PANEL  (right-side inset, y=0.355~0.575)
# floating panel inside section 3
# ══════════════════════════════════════════════════════════════════════
# Already inside S3 area — Rule v2 detail box placed at right-bottom of method A

# ══════════════════════════════════════════════════════════════════════
# SECTION 5 — OUTPUTS  (y=0.20~0.345)
# ══════════════════════════════════════════════════════════════════════
S5_Y, S5_H = 0.195, 0.148
section_header(ax, 0.02, S5_Y, 0.96, S5_H, "", C_OUT)
ax.text(0.5, S5_Y + S5_H - 0.010, "출력 결과물", ha="center", va="top",
        fontsize=FONT_LG, fontweight="bold", color="#2C3E50")

# Claude review middle step
arrow(ax, 0.5, S5_Y + S5_H - 0.002, 0.5, S5_Y + S5_H * 0.70 + 0.004, lw=1.2)
box(ax, 0.36, S5_Y + S5_H * 0.56, 0.28, 0.040, "#F8F9F9",
    "Claude → result/claude_review.json  (finding별 accept / reject)",
    fontsize=FONT_SM, edgecolor="#8E44AD", radius=0.010)
arrow(ax, 0.5, S5_Y + S5_H * 0.55, 0.5, S5_Y + S5_H * 0.45 + 0.002, lw=1.2)

ax.text(0.5, S5_Y + S5_H * 0.43, "python -m cloudsweep finalize  (source hash 검증)",
        ha="center", va="center", fontsize=FONT_SM, color="#2C3E50",
        bbox=dict(fc="#EBF5FB", ec="#2980B9", boxstyle="round,pad=0.4", lw=0.8))

arrow(ax, 0.5, S5_Y + S5_H * 0.40 - 0.003, 0.5, S5_Y + S5_H * 0.22 + 0.010, lw=1.2)

out_items = [
    ("cloudsweep_graph\n_state.json", "전체 finding,\nrule_id, evidence,\n절감액, TF 패치"),
    ("finops_report.md", "최종 Markdown\n보고서\n(accepted only)"),
    ("main_optimized.tf", "Terraform\n패치 적용 결과\n(hash 검증 후)"),
]
OW = 0.22
og = (0.88 - OW * len(out_items)) / (len(out_items) + 1)
for i, (fname, desc) in enumerate(out_items):
    ox = 0.06 + og * (i + 1) + OW * i
    oy = S5_Y + 0.008
    box(ax, ox, oy, OW, 0.068, "white", "", fontsize=FONT_SM,
        edgecolor="#27AE60", radius=0.012)
    ax.text(ox + OW/2, oy + 0.068 * 0.72, fname,
            ha="center", va="center", fontsize=FONT_SM, fontweight="bold",
            color="#1E8449", zorder=5)
    ax.text(ox + OW/2, oy + 0.068 * 0.28, desc,
            ha="center", va="center", fontsize=6.2, color="#555555", zorder=5)

# ══════════════════════════════════════════════════════════════════════
# SECTION 6 — RULE v2 + STATS FOOTER  (y=0.01~0.19)
# ══════════════════════════════════════════════════════════════════════
S6_Y, S6_H = 0.008, 0.182
section_header(ax, 0.02, S6_Y, 0.96, S6_H, "", C_RULE)
ax.text(0.5, S6_Y + S6_H - 0.010, "Rule v2 — severity_rule 구조 및 predicate 평가",
        ha="center", va="top", fontsize=FONT_LG, fontweight="bold", color="#7D6608")

# Left: predicate tree
PX, PY = 0.035, S6_Y + 0.015
ax.text(PX, PY + 0.145, "predicate 연산자", fontsize=FONT_SM, fontweight="bold", color="#333")
pred_lines = [
    ('{ "all": [...] }', "AND 조합"),
    ('{ "any": [...] }', "OR 조합"),
    ('{ "not": {...} }', "NOT"),
    ('{ "fact":"x", "op":"eq", "value":v }', "단일 비교"),
    ('{ "fact":"x", "op":"lt", "threshold":"k" }', "thresholds 참조"),
    ('  op: eq | ne | gt | gte | lt | lte | in | exists', ""),
]
for i, (code, meaning) in enumerate(pred_lines):
    ax.text(PX, PY + 0.120 - i * 0.021, code,
            fontsize=6.3, family="monospace", color="#0E6655", va="top")
    if meaning:
        ax.text(PX + 0.235, PY + 0.120 - i * 0.021, f"← {meaning}",
                fontsize=6.0, color="#555555", va="top")

# Middle: rule_type table
TX, TY = 0.395, S6_Y + 0.015
ax.text(TX, TY + 0.145, "rule_type", fontsize=FONT_SM, fontweight="bold", color="#333")
type_items = [
    ("finding", C_A,  "비용 절감 후보로 보고"),
    ("blocker", "#FADBD8", "blocked_by 목록의 finding 억제"),
    ("review",  C_B,  "Claude 판단 필요"),
]
for i, (rt, fc, desc) in enumerate(type_items):
    bx, by = TX, TY + 0.108 - i * 0.038
    ax.add_patch(FancyBboxPatch((bx, by), 0.085, 0.028,
                 boxstyle="round,pad=0.0,rounding_size=0.008",
                 facecolor=fc, edgecolor="#888", linewidth=0.6, zorder=3))
    ax.text(bx + 0.0425, by + 0.014, rt,
            ha="center", va="center", fontsize=FONT_SM, fontweight="bold",
            color="#1A252F", zorder=4)
    ax.text(bx + 0.096, by + 0.014, desc,
            ha="left", va="center", fontsize=6.2, color="#333", zorder=4)

# Right: stats
SX, SY = 0.700, S6_Y + 0.015
ax.text(SX, SY + 0.145, "현재 규칙 통계", fontsize=FONT_SM, fontweight="bold", color="#333")
stats = [
    ("도메인 수", "18개"),
    ("규칙 파일", "20개"),
    ("severity_rule 총계", "91개"),
    ("  structured predicate", "25개"),
    ("  blocker", "7개"),
    ("  string condition (미이관)", "66개"),
    ("테스트", "29 / 30 통과"),
    ("RuleEngine 도메인", "8개"),
]
for i, (k, v) in enumerate(stats):
    ax.text(SX, SY + 0.122 - i * 0.018, k,
            fontsize=6.5, color="#333", va="top")
    ax.text(SX + 0.178, SY + 0.122 - i * 0.018, v,
            fontsize=6.5, color="#1A5276", fontweight="bold", va="top", ha="right")

# ─── Save ─────────────────────────────────────────────────────────────
plt.tight_layout(pad=0)
fig.savefig("c:/Study/CloudSweep/cloudsweep_architecture.png",
            dpi=180, bbox_inches="tight", facecolor="#FAFAFA")
print("saved: cloudsweep_architecture.png")
