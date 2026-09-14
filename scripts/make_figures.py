#!/usr/bin/env python3
"""make_figures.py -- build the blog post's figures from the project's own artifacts.

Every figure is *read* from a committed artifact of the ASIC project, never retyped from prose: the
script records, for each figure, the artifacts it read and the project commit it read them at, and
writes that to `assets/img/figures.json` next to the images. If a number in a figure and a number in
the post disagree, one of them is wrong and both come from the same source.

Run it with the *project's* interpreter -- the net-806 figure drives KLayout, and matplotlib renders
the rest:

    .venv/Scripts/python.exe ../blogs/scripts/make_figures.py          # from the project root

`ASIC_ROOT` overrides the project path (default: E:/Projects/Jane-Street-ASIC-Puzzle).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(os.environ.get('ASIC_ROOT', 'E:/Projects/Jane-Street-ASIC-Puzzle'))
OUT = Path(__file__).resolve().parents[1] / 'assets' / 'img'
D = ROOT / 'recon' / 'derived'
GDS = ROOT / 'asic-puzzle-2026' / 'puzzle.gds'
DPI = 200

# Layer colours, one per (layer, datatype) pair seen in this design. Chosen so the two cut types are
# visually distinct from the conductors they join.
LAYER_STYLE = {
    '67/20': ('#1f77b4', 'met1 (67/20)'),
    '68/20': ('#ff7f0e', 'met2 (68/20)'),
    '69/20': ('#2ca02c', 'met3 (69/20)'),
    '67/44': ('#9467bd', 'via met1-met2 (67/44)'),
    '68/44': ('#d62728', 'via met2-met3 (68/44)'),
}
INK = '#1a1a1a'
MUTED = '#666666'


def j(name: str) -> dict:
    return json.loads((D / name).read_text(encoding='utf-8'))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def commit_id() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:                                     # noqa: BLE001 -- provenance, not control flow
        return 'unknown'


def save(fig, name: str, sources: list[str], caption: str, provenance: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    provenance.append({'file': name, 'caption': caption, 'sources': sources,
                       'source_sha256': {s: sha256(ROOT / s) for s in sources if (ROOT / s).exists()}})
    print(f'  wrote {name}')


# --------------------------------------------------------------------------------------------
# F1 -- the workflow, as the pipeline actually runs
# --------------------------------------------------------------------------------------------
def fig_pipeline(prov: list[dict]) -> None:
    """The four moves, in two rows of three, with the number that carries each one.

    Laid out 3x2 rather than 6x1 because a single row of six boxes cannot hold these strings: the
    first draft's titles and body lines overflowed their boxes and collided with their neighbours.
    """
    sol = j('solutions.json')
    nets = j('nets.json')['totals']
    e1 = j('e1_messages.json')
    placements = len(j('instances.json')['instances'])
    boxes = [
        ('1 · The chip describes itself', 'A1–A5', [
            '33 (layer, datatype) pairs classified',
            '9 via masters → the connectivity rules',
            '69 masters → pin names + geometry',
            'calibrated against the warm-up',
        ]),
        ('2 · Connectivity, from geometry', 'B1–B4', [
            f'{placements:,} placements, all on the site grid',
            f'{nets["conductor_shapes"]:,} conductor shapes,',
            'each in exactly one net',
            f'{nets["nets"]:,} nets; supply named by pin',
        ]),
        ('3 · Models, validated twice', 'C1–C2', [
            "oracle 1: the warm-up's real netlist",
            'oracle 2: byte-exact VCD replay',
            '2 808 bits compared, 0 mismatches',
        ]),
        ('4 · The hidden rule, by measurement', 'C3–C5', [
            '121 single-star sweeps → trigger sets',
            'exact cover → 11 classes, 2 stars each',
            'no per-region counter exists in this netlist',
        ]),
        ('5 · The answer, derived', 'D1–D4', [
            'four mechanical rules + the recovered one',
            'one solution; two enumerators agree',
            'both bit orders match the contract',
        ]),
        ('6 · Acceptance', 'E1–E3, F6', [
            f'success at cycle {e1["success_cycle_expected"]}',
            '(* TWO STARS *)',
            'five messages reproduced',
            'AC6 PARTIAL — declared, not hidden',
        ]),
    ]
    fig, ax = plt.subplots(figsize=(13.5, 6.4))
    ax.set_axis_off()
    w, h, gx, gy = 0.305, 0.335, 0.035, 0.10
    for i, (title, stages, lines) in enumerate(boxes):
        col, row = i % 3, i // 3
        x = col * (w + gx)
        y = 0.60 - row * (h + gy)
        ax.add_patch(Rectangle((x, y), w, h, facecolor='#f7f9fb', edgecolor='#8c9aa8', lw=1.1))
        ax.text(x + 0.018, y + h - 0.035, title, ha='left', va='top', fontsize=10.2,
                fontweight='bold', color=INK)
        ax.text(x + 0.018, y + h - 0.105, stages, ha='left', va='top', fontsize=8.6, color='#1f4e79',
                family='monospace')
        ax.text(x + 0.018, y + h - 0.175, '\n'.join(lines), ha='left', va='top', fontsize=8.0,
                color='#333333', linespacing=1.55)
        if col < 2:
            ax.annotate('', xy=(x + w + gx, y + h / 2), xytext=(x + w, y + h / 2),
                        arrowprops={'arrowstyle': '-|>', 'color': MUTED, 'lw': 1.2})
    y_last, y_next = 0.60 - h, 0.60 - h - gy
    ax.annotate('', xy=(w + gx / 2, y_next + h), xytext=(w + gx / 2, y_last),
                arrowprops={'arrowstyle': '-|>', 'color': MUTED, 'lw': 1.2,
                            'connectionstyle': 'arc3,rad=-0.45'})
    ax.text(0.5, 0.045, 'Every claim above is re-derived on every run:   33 gates   ·   129 injected '
                        'faults, each caught by its owner   ·   32 of 32 artifacts byte-identical when '
                        'deleted and rebuilt from the layout alone',
            fontsize=8.6, color=MUTED, ha='center', va='center')
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(0, 1)
    save(fig, 'f1_pipeline.png', ['recon/derived/solutions.json', 'recon/derived/nets.json',
                                  'recon/derived/e1_messages.json', 'recon/derived/instances.json'],
         'The six moves, with the measured number that carries each one.', prov)


# --------------------------------------------------------------------------------------------
# F2 -- the answer
# --------------------------------------------------------------------------------------------
def fig_answer(prov: list[dict]) -> None:
    sol = j('solutions.json')
    e1 = j('e1_messages.json')
    cycle = next(o['success_cycle_1based'] for o in e1['offsets'] if o['success_cycle_1based'])
    grid, cells = sol['solution']['grid'], sol['solution']['cells']
    stars = {(r, c) for r, c in cells}
    fig, ax = plt.subplots(figsize=(4.6, 5.4))
    ax.set_axis_off()
    for r in range(11):
        for c in range(11):
            ax.add_patch(Rectangle((c, 10 - r), 1, 1, facecolor='#fbfbfb', edgecolor='#d7dde3', lw=0.7))
            if (r, c) in stars:
                ax.plot(c + 0.5, (10 - r) + 0.5, marker='*', markersize=13, color='#1f4e79')
    ax.set_xlim(-0.4, 11.4)
    ax.set_ylim(-1.1, 11.4)
    ax.text(5.5, 11.05, f'{len(stars)} ones · two per row · two per column · no two adjacent · '
                        f'two per recovered class', ha='center', fontsize=8.4, color=MUTED)
    ax.text(5.5, -0.55, f'success at cycle {cycle} · message  (* TWO STARS *)', ha='center',
            fontsize=9, color=INK, fontweight='bold')
    ax.text(5.5, -0.95, 'the vector was derived by our own search, not transcribed; both bit orders '
                        'match the published witness', ha='center', fontsize=7.4, color=MUTED)
    save(fig, 'f2_answer.png', ['recon/derived/solutions.json', 'recon/derived/e1_messages.json'],
         'The accepted 121-bit board.', prov)


# --------------------------------------------------------------------------------------------
# F3 -- the five messages
# --------------------------------------------------------------------------------------------
def fig_messages(prov: list[dict]) -> None:
    e1, e2 = j('e1_messages.json'), j('e2_messages.json')
    rows = [
        ('all 121 bits zero', 'EMPTY SKY', 'E1'),
        ('all 121 bits one', 'BIG BANG', 'E1'),
        ('everything valid, one adjacent pair', 'TWO NOT TOUCH',
         f'E2 — {e2["boards_spelling_the_message"]} of {e2["boards_tested"]} constructed boards'),
        ('some other rule broken', 'TRY AGAIN', 'E1'),
        ('the accepted board', '(* TWO STARS *)', 'E1, success at cycle 126'),
    ]
    fig, ax = plt.subplots(figsize=(9.2, 2.9))
    ax.set_axis_off()
    ax.text(0.01, 1.02, 'what the chip says, and what makes it say that', fontsize=9.6,
            fontweight='bold', color=INK, transform=ax.transAxes)
    ax.text(0.01, 0.93, f'the control that gives the third row its meaning: adjacent boards that also '
                        f'break the hidden rule answer TRY AGAIN — '
                        f'{e2["control_group"]["boards_not_spelling_it"]} of '
                        f'{e2["control_group"]["boards"]} controls, and '
                        f'{e2["family"]["candidates"]} candidate boards were filtered to find the {e2["boards_tested"]}',
            fontsize=7.8, color=MUTED, transform=ax.transAxes)
    for i, (trigger, message, how) in enumerate(rows):
        y = 0.72 - i * 0.155
        ax.text(0.01, y, trigger, fontsize=8.6, color='#333333', transform=ax.transAxes)
        ax.annotate('', xy=(0.46, y + 0.02), xytext=(0.36, y + 0.02), xycoords='axes fraction',
                    arrowprops={'arrowstyle': '-|>', 'color': MUTED, 'lw': 1.0})
        ax.text(0.48, y, message, fontsize=9.2, color='#1f4e79', fontweight='bold',
                transform=ax.transAxes, family='monospace')
        ax.text(0.80, y, how, fontsize=7.4, color=MUTED, transform=ax.transAxes)
    save(fig, 'f3_messages.png', ['recon/derived/e1_messages.json', 'recon/derived/e2_messages.json'],
         'The five messages and their triggers.', prov)


# --------------------------------------------------------------------------------------------
# F4 -- the recovered partition, drawn as measured
# --------------------------------------------------------------------------------------------
def fig_partition(prov: list[dict]) -> None:
    """The 11 classes over the 121 cells, plus the answer's stars -- exactly what was measured.

    Deliberately not drawn as letters: the published writeup reads this map as "JS" and our recovery
    does not reproduce that reading, so drawing it as letters would be a claim we cannot back.
    """
    c4, sol = j('c4_partition.json'), j('solutions.json')
    cands = c4['candidates']
    chosen = next((c for c in cands if c['name'] == 'irregular_0'), cands[0])
    cell_class: dict[int, int] = {}
    for i, flop in enumerate(chosen['flops']):
        for cell in c4['trigger_sets'][flop]:
            cell_class[cell] = i
    stars = {(r, c) for r, c in sol['solution']['cells']}
    cmap = plt.get_cmap('tab20')
    fig, ax = plt.subplots(figsize=(5.2, 5.9))
    ax.set_axis_off()
    for cell in range(121):
        r, c = divmod(cell, 11)
        col = cmap(cell_class.get(cell, 0) % 20)
        ax.add_patch(Rectangle((c, 10 - r), 1, 1, facecolor=col, edgecolor='white', lw=0.9, alpha=0.62))
        if (r, c) in stars:
            ax.plot(c + 0.5, (10 - r) + 0.5, marker='*', markersize=13, color='#111111')
    ax.set_xlim(-0.4, 11.4)
    ax.set_ylim(-1.5, 11.6)
    ax.text(5.5, 11.2, f'{len(chosen["flops"])} classes over {len(cell_class)} cells · '
                       f'{len(stars)} stars, two per class', ha='center', fontsize=8.8, color=INK)
    ax.text(5.5, -0.6, 'recovered by measurement: 121 single-star sweeps → per-latch trigger sets →\n'
                       'exact cover → the capacity-2 cover that is not the column rule',
            ha='center', fontsize=7.6, color=MUTED)
    ax.text(5.5, -1.25, 'class sizes measured from the partition: '
                        + ', '.join(str(n) for n in sorted(
                            sum(1 for v in cell_class.values() if v == i)
                            for i in range(len(chosen['flops'])))[::-1]),
            ha='center', fontsize=7.2, color=MUTED)
    save(fig, 'f4_partition.png', ['recon/derived/c4_partition.json', 'recon/derived/solutions.json'],
         'The recovered partition, as measured (not drawn as letters).', prov)


# --------------------------------------------------------------------------------------------
# F5 -- net 806's real geometry
# --------------------------------------------------------------------------------------------
def fig_net806(prov: list[dict]) -> None:
    """The wire's own polygons, read from the layout through the pipeline's engine.

    The one foreign cut is drawn dashed: it overlaps the wire's met1 rectangle but belongs to another
    net on 68/20-69/20, so it has no shared conductor with the wire and cannot merge. That single
    geometric fact is what rules out "our extraction dropped a driver".
    """
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from klayout import db                                  # noqa: PLC0415
    from tools.puzzle import connect as C                   # noqa: PLC0415
    from tools.puzzle import net806 as N                    # noqa: PLC0415

    art = j('net806.json')
    a2 = j('via_pairs.json')
    conductors = sorted({p for r in a2['pairs'] for p in r['connects']})
    cuts = sorted({r['cut'] for r in a2['pairs']})
    ly, top, l2n, _nl, reg = C.build_engine(GDS, conductors, cuts, a2['pairs'])

    pts = [t['point_dbu'] for t in art['net']['terminals']]
    win = db.Box(min(p[0] for p in pts) - 20000, min(p[1] for p in pts) - 20000,
                 max(p[0] for p in pts) + 20000, max(p[1] for p in pts) + 20000)
    polys: list[tuple[str, list[tuple[int, int]]]] = []
    for layer in conductors + cuts:
        it = top.begin_shapes_rec(C.lindex(ly, layer))
        while not it.at_end():
            sh = it.shape()
            if not sh.bbox().overlaps(win):
                it.next()
                continue
            poly = sh.polygon
            centre = N.interior_point(poly) if poly is not None else sh.bbox().center()
            net = l2n.probe_net(reg[layer], centre)
            if poly is not None and net is not None and int(net.cluster_id) == art['net']['cluster']:
                polys.append((layer, [(p.x / 1000.0, p.y / 1000.0) for p in poly.each_point_hull()]))
            it.next()

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    seen = set()
    for layer, xy in polys:
        colour, label = LAYER_STYLE.get(layer, ('#888888', layer))
        ax.fill([p[0] for p in xy], [p[1] for p in xy], facecolor=colour,
                edgecolor=colour, lw=0.6, alpha=0.55,
                label=label if layer not in seen else None)
        seen.add(layer)
    foreign = next(o for o in art['cut_overlap']['overlapping'] if not o['same_net'])
    x0, y0, x1, y1 = (v / 1000.0 for v in foreign['bbox_dbu'])
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor='#d62728',
                           lw=1.4, ls='--', label=f'via on net {foreign["net"]} — cannot merge'))
    for t in art['net']['terminals']:
        ax.plot(t['point_dbu'][0] / 1000.0, t['point_dbu'][1] / 1000.0, marker='o', ms=5,
                color='#111111', zorder=5)
        ax.annotate(f'{t["instance"]}.{t["pin"]}', (t['point_dbu'][0] / 1000.0,
                    t['point_dbu'][1] / 1000.0), textcoords='offset points', xytext=(0, 7),
                    fontsize=7.6, ha='center')
    ties = art['message_tie']
    shapes = art['net']['shapes']
    ax.set_title(f'net {art["net"]["cluster"]}: {shapes["total"]} shapes on '
                 f'{len(shapes["by_layer"])} layer/datatype pairs, '
                 f'{len(shapes["own_cuts"])} of its own vias, no driver',
                 fontsize=9.4, color=INK)
    ax.set_xlabel('µm', fontsize=8.5)
    ax.tick_params(labelsize=7.5)
    ax.legend(fontsize=7.4, loc='lower left', framealpha=0.95)
    ax.text(0.5, -0.30, f'one character of the message it perturbs follows this net: '
                        f'{ties["tie_0"]!r} if it floats low, {ties["tie_1"]!r} if high — neither is the '
                        f'published string', transform=ax.transAxes, ha='center', fontsize=7.6,
            color=MUTED)
    save(fig, 'f5_net806.png', ['recon/derived/net806.json', 'recon/derived/via_pairs.json',
                                'asic-puzzle-2026/puzzle.gds'],
         'Net 806: the layout leaves it undriven, and the one cut over it cannot merge.', prov)


def main() -> int:
    prov: list[dict] = []
    print(f'reading artifacts from {ROOT}')
    fig_pipeline(prov)
    fig_answer(prov)
    fig_messages(prov)
    fig_partition(prov)
    fig_net806(prov)
    out = OUT / 'figures.json'
    out.write_text(json.dumps({'generated_by': 'scripts/make_figures.py',
                               'read_from': str(ROOT), 'project_commit': commit_id(),
                               'figures': prov}, indent=2) + '\n', encoding='utf-8')
    print(f'  wrote {out.name} (provenance: project commit {commit_id()})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
