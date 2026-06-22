import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib as mpl

mpl.rcParams['font.family'] = 'Malgun Gothic'
mpl.rcParams['axes.unicode_minus'] = False

# ── 공통 팔레트 (dark navy) ──────────────────────────────────────────
BG     = '#0F1B2D'
PANEL  = '#1C2B3A'
TEXT   = '#E8F4FD'
MUTED  = '#7A9BB5'
BLUE   = '#58A6FF'
GREEN  = '#3FB950'
YELLOW = '#D29922'
RED    = '#F85149'
PURPLE = '#BC8CFF'

def rbox(ax, x, y, w, h, fc, ec, lw=1.5, r=0.12, zorder=3):
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f'round,pad=0.0,rounding_size={r}',
                       facecolor=fc, edgecolor=ec, linewidth=lw, zorder=zorder)
    ax.add_patch(p)

def arr(ax, x0, y0, x1, y1, color=BLUE, lw=1.8, style='->'):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw), zorder=10)

# ════════════════════════════════════════════════════════════════════
# IMAGE 1 — 파이프라인 흐름
# ════════════════════════════════════════════════════════════════════
def draw_pipeline():
    fig = plt.figure(figsize=(13, 20), facecolor=BG)
    ax = fig.add_axes([0.03, 0.01, 0.94, 0.98], facecolor=BG)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 20)
    ax.axis('off')

    # 타이틀
    ax.text(6.5, 19.5, 'CloudSweep', ha='center', fontsize=32, fontweight='bold', color=BLUE)
    ax.text(6.5, 18.9, '분석 실행 파이프라인', ha='center', fontsize=18, color=TEXT)

    # ── 입력 파일 ────────────────────────────────────────────────────
    ax.text(6.5, 18.3, '입력 파일  (모두 선택 사항)', ha='center', fontsize=12, color=MUTED)
    inputs = [
        ('main.tf', '#56D364', '#0D2010'),
        ('metrics\n.json', '#58A6FF', '#0D1A2E'),
        ('cost_report\n.json', '#D29922', '#2A1E00'),
        ('genai_evidence\n.json', '#BC8CFF', '#1E0D2A'),
        ('{domain}_skill\n_analysis.json', '#7A9BB5', '#141E2A'),
    ]
    IW, IH = 2.1, 1.1
    gap = (11 - IW * 5) / 6
    for i, (name, ec, fc) in enumerate(inputs):
        ix = 1 + gap * (i + 1) + IW * i
        iy = 17.0
        rbox(ax, ix, iy, IW, IH, fc, ec, lw=1.8)
        ax.text(ix + IW / 2, iy + IH / 2, name, ha='center', va='center',
                fontsize=10.5, color=TEXT, zorder=4, linespacing=1.35, fontweight='bold')

    arr(ax, 6.5, 16.95, 6.5, 16.6)
    ax.text(6.5, 16.4, 'python -m cloudsweep <WORK_DIR>', ha='center',
            fontsize=11, color=BLUE, family='monospace')

    # ── LangGraph 박스 ───────────────────────────────────────────────
    LG_Y0, LG_Y1 = 6.6, 16.1
    rbox(ax, 0.3, LG_Y0, 12.4, LG_Y1 - LG_Y0, PANEL, BLUE, lw=2.0, r=0.3, zorder=1)
    ax.text(0.75, LG_Y1 - 0.3, 'LangGraph', fontsize=14, fontweight='bold',
            color=BLUE, va='top', zorder=4)

    steps = [
        ('① Evidence Inventory', '존재 파일 목록 수집', BLUE),
        ('② Execution Plan', '분석 경로 결정', BLUE),
        ('③ Domain Detection', '18개 도메인 관련성 탐지', BLUE),
        ('④ Domain Analysis', '도메인별 병렬 fan-out  ★ 핵심', '#58D4FF'),
        ('⑤ Collect Results', 'finding 집계 · Terraform 패치 생성', BLUE),
        ('⑥ MCP Enrichment', '실시간 AWS 가격 · 공식 문서 보강', BLUE),
        ('⑦ Cross-Domain Review', '교차 서비스 패턴 확인', BLUE),
        ('⑧ Report Generation', 'state.json 저장', BLUE),
    ]
    SW, SH, SX = 11.4, 0.88, 0.9
    sy = LG_Y1 - 0.60
    for i, (title, sub, tc) in enumerate(steps):
        top = sy - i * 1.04
        bot = top - SH
        hi = (i == 3)
        rbox(ax, SX, bot, SW, SH,
             fc='#0D2440' if hi else '#132030',
             ec='#58D4FF' if hi else '#2A4A6A',
             lw=2.2 if hi else 1.0)
        ax.text(SX + 0.28, bot + SH / 2, title,
                ha='left', va='center', fontsize=12.5, fontweight='bold',
                color='#58D4FF' if hi else TEXT, zorder=4)
        ax.text(SX + SW - 0.2, bot + SH / 2, sub,
                ha='right', va='center', fontsize=10.5, color=MUTED, zorder=4)
        if i < len(steps) - 1:
            arr(ax, 6.5, bot, 6.5, bot - 0.01, lw=1.3)

    # 인터럽트 노트
    int_y = LG_Y0 + (LG_Y1 - LG_Y0) * 0.32
    ax.text(12.0, int_y,
            '⑤ 이후\nHIGH severity\n+ LOW confidence\n→ interrupt',
            ha='center', va='center', fontsize=9.5, color=RED,
            bbox=dict(fc='#2D0A08', ec=RED, boxstyle='round,pad=0.5', lw=1.5), zorder=6)
    arr(ax, 12.1, int_y + 0.6, 12.1, int_y + 0.05, color=RED, lw=1.2)

    # ── Claude review ────────────────────────────────────────────────
    arr(ax, 6.5, LG_Y0, 6.5, LG_Y0 - 0.35)
    CR_Y = LG_Y0 - 1.3
    rbox(ax, 1.8, CR_Y, 9.4, 0.85, '#200A3A', PURPLE, lw=2.0)
    ax.text(6.5, CR_Y + 0.425,
            'Claude  →  result/claude_review.json\n(finding별 accept / reject)',
            ha='center', va='center', fontsize=12, color=PURPLE, zorder=4)

    # ── Finalize ─────────────────────────────────────────────────────
    arr(ax, 6.5, CR_Y, 6.5, CR_Y - 0.35)
    FIN_Y = CR_Y - 1.2
    rbox(ax, 2.5, FIN_Y, 8.0, 0.75, '#0A1E0E', GREEN, lw=2.0)
    ax.text(6.5, FIN_Y + 0.375,
            'python -m cloudsweep finalize\n(source hash 검증 → accepted만 합산)',
            ha='center', va='center', fontsize=11.5, color=GREEN, zorder=4,
            family='monospace')

    # ── 출력 ────────────────────────────────────────────────────────
    arr(ax, 6.5, FIN_Y, 6.5, FIN_Y - 0.35)
    ax.text(6.5, FIN_Y - 0.55, '출력 파일', ha='center', fontsize=12, color=MUTED)
    outputs = [
        ('finops_report.md', '최종 보고서\n(accepted finding)'),
        ('main_optimized.tf', 'Terraform 패치\n적용 결과'),
    ]
    OW = 4.5
    for i, (fname, desc) in enumerate(outputs):
        ox = 1.5 + i * 5.5
        oy = FIN_Y - 1.85
        rbox(ax, ox, oy, OW, 1.15, '#0A1E0E', GREEN, lw=1.5)
        ax.text(ox + OW / 2, oy + 0.78, fname,
                ha='center', va='center', fontsize=11, fontweight='bold',
                color=GREEN, zorder=4, family='monospace')
        ax.text(ox + OW / 2, oy + 0.32, desc,
                ha='center', va='center', fontsize=10, color=MUTED, zorder=4)

    fig.savefig('c:/Study/CloudSweep/arch_1_pipeline.png',
                dpi=150, bbox_inches='tight', facecolor=BG)
    print('saved arch_1_pipeline.png')
    plt.close()


# ════════════════════════════════════════════════════════════════════
# IMAGE 2 — 도메인 분석 4가지 방식
# ════════════════════════════════════════════════════════════════════
def draw_domains():
    fig = plt.figure(figsize=(20, 14), facecolor=BG)
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.96], facecolor=BG)
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 14)
    ax.axis('off')

    ax.text(10, 13.5, '도메인 분석 방식', ha='center', fontsize=26,
            fontweight='bold', color=TEXT)
    ax.text(10, 13.0, '18개 도메인은 복잡도에 따라 4가지 방식 중 하나로 분석된다',
            ha='center', fontsize=14, color=MUTED)

    cards = [
        {
            'title': '방식 A\nRuleEngine',
            'count': '8개 도메인',
            'ec': GREEN, 'fc': '#0A1E10',
            'badge': '#3FB950',
            'items': [
                ('cloudwatch',       'C1  — log retention 없음'),
                ('cloudwatch-alarm', 'M1,M2  — high-res alarm'),
                ('sqs',              'Q1  — short polling'),
                ('kinesis',          'K1 / K5(B)  — EFO 낭비'),
                ('ebs',              'S1 / S2(B)  — 고아 snapshot'),
                ('nat',              'N1  — S3 endpoint 우회 가능'),
                ('tgw',              'T2  — attachment 부족'),
                ('organizations',    'O1  — consolidated billing'),
            ],
            'mech': '_findings_from_engine()\n→ JSON predicate 평가\n→ blocker 집행\n→ savings_fraction 계산',
            'mech_color': GREEN,
        },
        {
            'title': '방식 B\nPython 직접',
            'count': '3개 도메인',
            'ec': YELLOW, 'fc': '#1E1500',
            'badge': YELLOW,
            'items': [
                ('lambda',    'L1  — p99/allocated < 0.2'),
                ('s3',        'V1  — lifecycle config 없음'),
                ('dynamodb',  'D1  — provisioned 과잉'),
            ],
            'mech': '리소스별 계산이 다르거나\n교차 블록 참조 필요\n→ Python if/for 유지\n→ rule_id는 POLICY:sub 형식 통일',
            'mech_color': YELLOW,
        },
        {
            'title': '방식 C\nGenAI Python',
            'count': '3개 도메인',
            'ec': RED, 'fc': '#1E0A08',
            'badge': RED,
            'items': [
                ('bedrock',   'B1~B4  — 처리량 commitment, cache'),
                ('sagemaker', 'SM1~SM4  — autoscaling, GPU'),
                ('ec2 (GPU)', 'G1~G4  — 미스케줄, idle, ASG'),
            ],
            'mech': 'genai_evidence.json 기반\n→ Terraform 없어도 동작\n→ savings_group별 최댓값만\n   최종 합산에 포함',
            'mech_color': RED,
        },
        {
            'title': '방식 D\nClaude Skill',
            'count': '4개 도메인',
            'ec': PURPLE, 'fc': '#160A22',
            'badge': PURPLE,
            'items': [
                ('rds',          'R1~R6  (Python: R1,R2만 구현)'),
                ('elb',          'LB1~LB5  (Python: LB1~LB4)'),
                ('ecs',          'E1~E4  (Python: E1~E3)'),
                ('elasticache',  'EC1~EC5  (Python: 전체)'),
            ],
            'mech': '{domain}_skill_analysis.json\n→ 존재하면 Skill 결과 사용\n→ 없으면 Python fallback\n   (CLI 단독 실행 항상 동작)',
            'mech_color': PURPLE,
        },
    ]

    CW = 4.6
    CX_START = 0.2
    CY0, CY1 = 0.3, 12.6

    for i, c in enumerate(cards):
        cx = CX_START + i * (CW + 0.15)
        ch = CY1 - CY0

        # 카드 배경
        rbox(ax, cx, CY0, CW, ch, c['fc'], c['ec'], lw=2.5, r=0.2)

        # 헤더 배지
        rbox(ax, cx + 0.15, CY1 - 1.35, CW - 0.3, 1.15,
             fc=c['fc'], ec=c['ec'], lw=1.0, r=0.12)
        ax.text(cx + CW / 2, CY1 - 0.55, c['title'],
                ha='center', va='center', fontsize=16, fontweight='bold',
                color=c['badge'], zorder=4, linespacing=1.3)
        ax.text(cx + CW / 2, CY1 - 1.1, c['count'],
                ha='center', va='center', fontsize=12, color=MUTED, zorder=4)

        # 도메인 리스트
        item_y = CY1 - 1.65
        for dname, rule in c['items']:
            ax.text(cx + 0.35, item_y, dname,
                    fontsize=12, fontweight='bold', color=TEXT,
                    va='top', zorder=4)
            ax.text(cx + 0.35, item_y - 0.30, rule,
                    fontsize=10, color=MUTED, va='top', zorder=4,
                    family='monospace')
            item_y -= 0.72

        # 구분선
        sep_y = CY0 + 2.6
        ax.plot([cx + 0.2, cx + CW - 0.2], [sep_y, sep_y],
                color=c['ec'], lw=0.8, alpha=0.5, zorder=4)

        # 메커니즘 설명
        ax.text(cx + CW / 2, sep_y - 0.25, c['mech'],
                ha='center', va='top', fontsize=10.5,
                color=c['mech_color'], zorder=4, linespacing=1.5,
                bbox=dict(fc='#00000040', boxstyle='round,pad=0.4'))

    # (B) 주석
    ax.text(10, 0.12, '(B) = Blocker  —  triggered 시 blocked_by 목록의 finding 억제',
            ha='center', fontsize=11, color=MUTED)

    fig.savefig('c:/Study/CloudSweep/arch_2_domains.png',
                dpi=150, bbox_inches='tight', facecolor=BG)
    print('saved arch_2_domains.png')
    plt.close()


# ════════════════════════════════════════════════════════════════════
# IMAGE 3 — Rule v2 구조
# ════════════════════════════════════════════════════════════════════
def draw_rules():
    fig = plt.figure(figsize=(17, 13), facecolor=BG)
    ax = fig.add_axes([0.03, 0.02, 0.94, 0.96], facecolor=BG)
    ax.set_xlim(0, 17)
    ax.set_ylim(0, 13)
    ax.axis('off')

    ax.text(8.5, 12.5, 'Rule v2  —  severity_rule 구조와 predicate 평가',
            ha='center', fontsize=22, fontweight='bold', color=TEXT)

    # ── 좌: predicate 연산자 ─────────────────────────────────────────
    rbox(ax, 0.3, 0.4, 7.8, 11.7, PANEL, BLUE, lw=1.5, r=0.2)
    ax.text(4.2, 11.75, 'predicate  연산자', ha='center', fontsize=16,
            fontweight='bold', color=BLUE, va='top')

    ops = [
        ('{ "all": [ ... ] }',              'AND  —  전부 참이어야'),
        ('{ "any": [ ... ] }',              'OR  —  하나라도 참이면'),
        ('{ "not": { ... } }',              'NOT  —  반전'),
        ('{ "fact": "x", "op": "eq",\n  "value": true }',   '단일 값 비교'),
        ('{ "fact": "x", "op": "lt",\n  "threshold": "k" }','thresholds 딕셔너리 참조'),
        ('  op 목록:',                       'eq · ne · gt · gte · lt · lte · in · exists'),
    ]
    oy = 11.1
    for code, desc in ops:
        rbox(ax, 0.55, oy - 1.1, 7.3, 1.0, '#0D1A2A', '#2A4A6A', lw=1.0, r=0.1)
        ax.text(0.80, oy - 0.4, code, fontsize=11, va='center',
                color='#58D4FF', zorder=4, family='monospace')
        ax.text(0.80, oy - 0.82, f'→  {desc}', fontsize=10, va='center',
                color=MUTED, zorder=4)
        oy -= 1.25

    # 예시 predicate (DynamoDB D1)
    ax.text(4.2, oy + 0.1, '예시  (DynamoDB D1)', ha='center', fontsize=12,
            color=MUTED, va='bottom')
    example = ('{ "all": [\n'
               '  { "fact": "billing_mode", "op": "eq", "value": "PROVISIONED" },\n'
               '  { "not": { "fact": "has_autoscaling", "op": "eq", "value": true } },\n'
               '  { "any": [\n'
               '    { "fact": "is_problem", "op": "eq", "value": true },\n'
               '    { "fact": "max_capacity_utilization",\n'
               '      "op": "lt", "threshold": "capacity_utilization_threshold" }\n'
               '  ]}\n'
               ']}')
    rbox(ax, 0.55, 0.5, 7.3, oy - 0.3, '#050E1A', '#3A5A7A', lw=1.0, r=0.1)
    ax.text(0.80, oy - 0.35, example, fontsize=9.5, va='top',
            color='#79C0FF', zorder=4, family='monospace', linespacing=1.45)

    # ── 우: rule_type + blocker 메커니즘 ─────────────────────────────
    rbox(ax, 8.6, 6.5, 8.1, 5.6, PANEL, GREEN, lw=1.5, r=0.2)
    ax.text(12.65, 11.75, 'rule_type', ha='center', fontsize=16,
            fontweight='bold', color=GREEN, va='top')

    types = [
        ('finding', '#0A1E10', GREEN,
         '비용 절감 후보로 보고\nsavings_fraction × domain_monthly / n'),
        ('blocker', '#1E0A08', RED,
         'blocked_by 목록의 finding을\n같은 리소스에서 억제'),
        ('review',  '#1A1500', YELLOW,
         'Claude 판단 필요\n자동 행동 금지'),
    ]
    ty = 11.1
    for rt, fc, ec, desc in types:
        rbox(ax, 8.85, ty - 1.5, 7.6, 1.38, fc, ec, lw=1.5, r=0.12)
        ax.text(9.2, ty - 0.55, rt, fontsize=14, fontweight='bold',
                color=ec, va='center', zorder=4)
        ax.text(9.2, ty - 1.05, desc, fontsize=10.5, color=MUTED,
                va='center', zorder=4, linespacing=1.4)
        ty -= 1.65

    # blocker 메커니즘 다이어그램
    rbox(ax, 8.6, 0.4, 8.1, 5.9, PANEL, PURPLE, lw=1.5, r=0.2)
    ax.text(12.65, 6.0, 'Blocker 집행 메커니즘', ha='center', fontsize=14,
            fontweight='bold', color=PURPLE, va='top')

    blockers = [
        ('S2', 'ebs',          'S1',           'AMI / Backup 참조 존재'),
        ('K5', 'kinesis',      'K1, K2',        '스로틀 발생'),
        ('D7', 'dynamodb',     'D1, D2, D3',    '읽기/쓰기 스로틀'),
        ('V3', 's3',           'V1, V2, V4',    'Object Lock / legal hold'),
        ('R6', 'rds',          'R1~R3, R5',     'CPU peak 높음 OR 메모리 부족'),
        ('LB5','elb',          'LB1~LB3',       '삭제 방지 OR DR 역할'),
        ('EC5','elasticache',  'EC1~EC3',        '엔진 EOL'),
    ]
    # 헤더
    hx = [8.85, 9.75, 10.65, 12.05]
    headers = ['ID', '도메인', '억제 대상', '조건']
    for hxi, h in zip(hx, headers):
        ax.text(hxi, 5.55, h, fontsize=11, fontweight='bold',
                color=MUTED, va='top')
    ax.plot([8.85, 16.45], [5.42, 5.42], color='#2A3A4A', lw=0.8)

    by = 5.15
    for bid, domain, blocks, cond in blockers:
        rbox(ax, 8.82, by - 0.52, 7.82, 0.50, '#1A0B28', '#4A3060', lw=0.8, r=0.08)
        ax.text(8.95,  by - 0.26, bid,    fontsize=11, color=PURPLE, va='center',
                fontweight='bold', zorder=4)
        ax.text(9.85,  by - 0.26, domain, fontsize=10.5, color=TEXT,  va='center', zorder=4)
        ax.text(10.75, by - 0.26, blocks, fontsize=10,   color=RED,   va='center',
                zorder=4, family='monospace')
        ax.text(12.2,  by - 0.26, cond,   fontsize=9.5,  color=MUTED, va='center', zorder=4)
        by -= 0.64

    ax.text(12.65, 0.55,
            'missing_evidence_policy: "assume_triggered"\n→ 판단 근거가 없으면 blocker 켜진 것으로 보수적 처리',
            ha='center', va='bottom', fontsize=10, color=YELLOW)

    # ── 통계 ─────────────────────────────────────────────────────────
    stats_y = 0.3
    stats = [
        ('도메인', '18'),
        ('규칙 파일', '20'),
        ('severity_rule 총계', '91'),
        ('structured predicate', '25'),
        ('blockers', '7'),
        ('테스트 통과', '29/30'),
    ]
    # stats panel removed — too cramped, keep it in text

    fig.savefig('c:/Study/CloudSweep/arch_3_rules.png',
                dpi=150, bbox_inches='tight', facecolor=BG)
    print('saved arch_3_rules.png')
    plt.close()


draw_pipeline()
draw_domains()
draw_rules()
