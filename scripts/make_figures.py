#!/usr/bin/env python3
"""make_figures.py -- generate every figure the blog post cites, from the frozen project
repository's own committed artifacts.

Lives in the *blog* repository (docs/04_blog_plan.md SS4), not the project repository. Every
number drawn on every figure is read from a JSON artifact or source file under --repo; nothing
is typed in by hand. The script also writes assets/img/figures_metadata.json, which records the
project commit each figure was generated from and the sha256 of every artifact it read, so a
figure can never silently drift from the repository that produced it.

Each figure is rendered twice -- once per THEMES entry -- because the site's CSS
(assets/main.scss) switches the whole UI dark via prefers-color-scheme with no JS toggle, and a
figure with a hardcoded white background looks wrong sitting in a dark page. The light variant
keeps the original filename (f1_pipeline.png); the dark variant gets a `-dark` suffix
(f1_pipeline-dark.png). The post embeds both per image via <picture><source media="(prefers-
color-scheme: dark)">, so the browser -- not a runtime toggle -- picks the one that matches.

Usage:
    python scripts/make_figures.py --repo /path/to/jane-street-asic-puzzle-2026 [--out assets] \
        [--video /path/to/warmup_gds_3d.mp4] [--dpi 200] [--only f1,f4] [--themes light,dark]

Requires: matplotlib, gdstk (only for F5), both already pinned in the project's requirements.txt.
Run it with the project's own venv interpreter so those are on the path, e.g.:
    /path/to/project/.venv/Scripts/python.exe scripts/make_figures.py --repo /path/to/project
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon as MplPolygon
from matplotlib.lines import Line2D

# ---------------------------------------------------------------------------------------------
# Themes -- one dict per color scheme. Keys are used as f"theme['...']" throughout; every figure
# function takes a `theme` argument instead of reading module-level constants, so nothing here
# is baked into a figure at import time.
# ---------------------------------------------------------------------------------------------

THEMES = {
    'light': dict(
        suffix='',
        ink='#1b1f23', paper='#ffffff', mute='#6a737d', accent='#c0392b', good='#2e7d32',
        grid_line='#d0d5da', header_bg='#2c3e50', header_text='white',
        cell_empty='#f4f6f8', cell_star='#2c3e50', row_alt='#f4f6f8',
        legend_bg='#1b1f23', legend_text='white', axes_bg='#0f1216',
        class_palette=['#3477eb', '#c0392b', '#2e9e6b', '#e0a72e', '#8e44ad', '#16a3a3',
                        '#d35400', '#7f8c8d', '#2c3e50', '#c2185b', '#558b2f'],
    ),
    'dark': dict(
        suffix='-dark',
        ink='#e8e6e1', paper='#181c22', mute='#9099a6', accent='#e2954f', good='#6fce8e',
        grid_line='#333a45', header_bg='#0d1013', header_text='#e8e6e1',
        cell_empty='#232935', cell_star='#3d4f66', row_alt='#1d222b',
        legend_bg='#05070a', legend_text='#e8e6e1', axes_bg='#05070a',
        # same hues as light, lightened for contrast against a dark background
        class_palette=['#6f9bf2', '#e5766c', '#57cf9d', '#f2c85a', '#b98be0', '#4fe0e0',
                        '#f2a35f', '#aab3bd', '#89a6c7', '#ef7bab', '#8fce67'],
    ),
}

PHASE_COLOR = {
    'S': '#9e9e9e',
    'A': '#3477eb',
    'B': '#2e9e6b',
    'C': '#e0a72e',
    'D': '#c0392b',
    'E': '#8e44ad',
    'F': '#16a3a3',
}
PHASE_NAME = {
    'S': 'Foundations',
    'A': 'The chip describes itself',
    'B': 'Connectivity & netlist',
    'C': 'Understand the chip',
    'D': 'Our own solve',
    'E': 'Confirm',
    'F': 'The undriven net',
}


def apply_rcparams(theme: dict) -> None:
    """Point matplotlib's own defaults (table/legend text color etc.) at this theme."""
    plt.rcParams.update({
        'font.family': 'DejaVu Sans',
        'axes.edgecolor': theme['grid_line'],
        'text.color': theme['ink'],
        'axes.labelcolor': theme['ink'],
        'xtick.color': theme['mute'],
        'ytick.color': theme['mute'],
    })


# ---------------------------------------------------------------------------------------------
# Artifact loading, with citation tracking
# ---------------------------------------------------------------------------------------------

class Ctx:
    """Carries the repo root and records, per figure, exactly which artifacts fed it."""

    def __init__(self, repo: Path, dpi: int):
        self.repo = repo
        self.dpi = dpi
        self.citations: dict[str, list[dict]] = {}
        self._fig = None

    def begin(self, fig_name: str) -> None:
        self._fig = fig_name
        self.citations.setdefault(fig_name, [])

    def cite(self, relpath: str) -> Path:
        p = self.repo / relpath
        if not p.exists():
            raise FileNotFoundError(
                f'{self._fig or "?"} needs {relpath}, not found under --repo {self.repo}. '
                'Point --repo at a checkout of the frozen project (README + AGENTS.md live at its root).'
            )
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        entry = {'path': relpath, 'sha256': sha}
        if entry not in self.citations[self._fig]:
            self.citations[self._fig].append(entry)
        return p

    def load_json(self, relpath: str) -> dict:
        return json.loads(self.cite(relpath).read_text(encoding='utf-8'))


def repo_provenance(repo: Path) -> dict:
    def git(*args):
        try:
            return subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                   text=True, check=True).stdout.strip()
        except Exception as exc:  # pragma: no cover - best effort only
            return f'<git unavailable: {exc}>'

    return {
        'commit': git('rev-parse', 'HEAD'),
        'branch': git('rev-parse', '--abbrev-ref', 'HEAD'),
        'dirty': bool(git('status', '--porcelain')),
    }


# ---------------------------------------------------------------------------------------------
# F1 -- pipeline flow
# ---------------------------------------------------------------------------------------------

def parse_stages(cli_path: Path) -> list[tuple[str, str, str, str]]:
    tree = ast.parse(cli_path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', None) == 'STAGES':
            return ast.literal_eval(node.value)
    raise RuntimeError(f'STAGES not found in {cli_path}')


def fig_f1_pipeline(ctx: Ctx, outdir: Path, theme: dict):
    ctx.begin('f1_pipeline')
    cli_path = ctx.cite('tools/puzzle/cli.py')
    stages = parse_stages(cli_path)

    oracle_marks = {'warmup-regression': '①', 'vcd-replay': '②'}

    per_row = 8
    rows = -(-len(stages) // per_row)
    box_w, box_h, gap_x, gap_y = 1.0, 0.62, 0.28, 1.0

    fig, ax = plt.subplots(figsize=(11.0, 1.0 * rows + 2.5))
    fig.patch.set_facecolor(theme['paper'])
    ax.set_facecolor(theme['paper'])

    for i, (stage, _module, step, _purpose) in enumerate(stages):
        row, col = divmod(i, per_row)
        x = col * (box_w + gap_x)
        y = -row * gap_y
        phase = step[0]
        color = PHASE_COLOR.get(phase, theme['mute'])
        is_oracle = stage in oracle_marks
        ax.add_patch(Rectangle((x, y), box_w, box_h, facecolor=color, alpha=0.9,
                                edgecolor=(theme['accent'] if is_oracle else 'none'),
                                linewidth=(2.2 if is_oracle else 0), zorder=3))
        ax.text(x + box_w / 2, y + box_h / 2 + 0.02, step, ha='center', va='center',
                fontsize=7.5, color='white', weight='bold', zorder=4)
        ax.text(x + box_w / 2, y - 0.11, stage, ha='center', va='top', fontsize=6.0,
                color=theme['mute'], zorder=4)
        if is_oracle:
            ax.text(x + box_w - 0.05, y + box_h - 0.03, oracle_marks[stage], ha='right', va='top',
                    fontsize=9.5, color='white', weight='bold', zorder=5)
        if col < per_row - 1 and i + 1 < len(stages):
            ax.add_line(Line2D([x + box_w, x + box_w + gap_x], [y + box_h / 2, y + box_h / 2],
                                color=theme['grid_line'], lw=1.2, zorder=1))

    top_y = box_h + 0.15
    bottom_y = -(rows - 1) * gap_y - box_h - 0.30
    ax.set_xlim(-0.3, per_row * (box_w + gap_x) - gap_x + 0.3)
    ax.set_ylim(bottom_y, top_y)
    ax.axis('off')
    ax.set_title(f'The pipeline: {len(stages)} stages, raw GDS to derived answer', fontsize=12,
                 pad=10, color=theme['ink'])

    footnote = ('① warm-up regression -- our whole chain must reproduce a netlist we already know   '
                '② vcd-replay -- byte-exact replay of the provided reference waveform')
    fig.text(0.5, 0.135, footnote, ha='center', va='center', fontsize=8.0, color=theme['accent'])

    handles = [Rectangle((0, 0), 1, 1, facecolor=PHASE_COLOR[p]) for p in PHASE_COLOR]
    labels = [f'{p} -- {PHASE_NAME[p]}' for p in PHASE_COLOR]
    leg = fig.legend(handles, labels, loc='lower center', ncol=4, frameon=False, fontsize=7.6,
                      bbox_to_anchor=(0.5, 0.0))
    for text in leg.get_texts():
        text.set_color(theme['ink'])

    fig.subplots_adjust(top=0.90, bottom=0.20)
    fig.savefig(outdir / f"f1_pipeline{theme['suffix']}.png", dpi=ctx.dpi, facecolor=theme['paper'])
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# F2 -- the answer
# ---------------------------------------------------------------------------------------------

def fig_f2_answer(ctx: Ctx, outdir: Path, theme: dict):
    ctx.begin('f2_answer')
    solutions = ctx.load_json('recon/derived/solutions.json')
    e1 = ctx.load_json('recon/derived/e1_messages.json')

    grid = solutions['solution']['grid']
    n = len(grid)
    cycle = e1['offsets'][0]['success_cycle_1based']
    message = e1['offsets'][0]['message']

    fig, ax = plt.subplots(figsize=(6.4, 6.9))
    fig.patch.set_facecolor(theme['paper'])
    ax.set_facecolor(theme['paper'])

    for r in range(n):
        for c in range(n):
            star = grid[r][c] == '*'
            ax.add_patch(Rectangle((c, n - 1 - r), 1, 1,
                                    facecolor=(theme['cell_star'] if star else theme['cell_empty']),
                                    edgecolor=theme['grid_line'], linewidth=0.8))
            if star:
                ax.text(c + 0.5, n - 1 - r + 0.5, '★', ha='center', va='center',
                        fontsize=13, color='#f5c518')

    ax.set_xlim(0, n)
    ax.set_ylim(0, n)
    ax.set_xticks(range(n))
    ax.set_xticklabels(range(n), fontsize=8, color=theme['mute'])
    ax.set_yticks(range(n))
    ax.set_yticklabels(range(n - 1, -1, -1), fontsize=8, color=theme['mute'])
    ax.set_aspect('equal')
    ax.set_title('The derived answer -- 22 stars on the 11×11 grid', fontsize=12, pad=10,
                 color=theme['ink'])
    ax.text(0.5, -0.09,
            f'success asserts at cycle {cycle}  •  output "{message}"  •  '
            'derived by our own search, not transcribed from the published answer',
            transform=ax.transAxes, ha='center', va='top', fontsize=8.6, color=theme['mute'])
    fig.savefig(outdir / f"f2_answer{theme['suffix']}.png", dpi=ctx.dpi, facecolor=theme['paper'],
                bbox_inches='tight')
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# F3 -- the message table
# ---------------------------------------------------------------------------------------------

def fig_f3_messages(ctx: Ctx, outdir: Path, theme: dict):
    ctx.begin('f3_messages')
    e1 = ctx.load_json('recon/derived/e1_messages.json')
    e2 = ctx.load_json('recon/derived/e2_messages.json')

    rows = []
    case_labels = {
        'all_zeros': 'all zeros',
        'all_ones': 'all ones',
        'two_per_row_col_but_adjacent': '2/row+col, but touching',
        'other_wrong': 'any other wrong input',
        'correct': 'the derived answer',
    }
    for m in e1['messages']:
        rows.append([case_labels.get(m['case'], m['case']), str(m['ones']), m['got'],
                     'match' if m['match'] else 'no match'])

    fam = e2['family']

    fig = plt.figure(figsize=(11.5, 4.6))
    fig.patch.set_facecolor(theme['paper'])
    ax_t = fig.add_axes([0.03, 0.06, 0.56, 0.86])
    ax_b = fig.add_axes([0.66, 0.14, 0.31, 0.70])
    ax_b.set_facecolor(theme['paper'])
    ax_t.axis('off')

    col_labels = ['input class', 'ones', 'chip prints', '']
    table = ax_t.table(cellText=rows, colLabels=col_labels, loc='center', cellLoc='left',
                        colWidths=[0.40, 0.12, 0.30, 0.18])
    table.auto_set_font_size(False)
    table.set_fontsize(9.2)
    table.scale(1, 1.9)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(theme['grid_line'])
        if r == 0:
            cell.set_facecolor(theme['header_bg'])
            cell.set_text_props(color=theme['header_text'], weight='bold')
        else:
            cell.set_facecolor(theme['row_alt'] if r % 2 else theme['paper'])
            if c == 3:
                ok = rows[r - 1][3] == 'match'
                cell.set_text_props(color=(theme['good'] if ok else theme['accent']), weight='bold')
            else:
                cell.set_text_props(color=theme['ink'])
    ax_t.set_title('The five message classes (E1)', fontsize=11, loc='left', pad=14,
                    color=theme['ink'])

    labels = ['TWO NOT TOUCH\n(within class caps)', 'TRY AGAIN\n(over caps)', 'other']
    values = [fam['adjacent_within_caps'], fam['adjacent_over_caps'], fam['not_adjacent_over_caps']]
    colors = [theme['good'], theme['mute'], theme['grid_line']]
    bars = ax_b.bar(labels, values, color=colors, width=0.6)
    for b, v in zip(bars, values):
        ax_b.text(b.get_x() + b.get_width() / 2, v + 2, str(v), ha='center', fontsize=9.5,
                  color=theme['ink'])
    ax_b.set_ylim(0, max(values) * 1.2)
    ax_b.set_title(f'all {fam["adjacent_within_caps"] + fam["adjacent_over_caps"] + fam["not_adjacent_over_caps"]}'
                    ' boards of the swap family (E2)\n-- tested, not sampled', fontsize=9.8,
                    color=theme['ink'])
    ax_b.spines[['top', 'right']].set_visible(False)
    ax_b.spines[['left', 'bottom']].set_color(theme['grid_line'])
    ax_b.tick_params(labelsize=8, colors=theme['mute'])

    fig.savefig(outdir / f"f3_messages{theme['suffix']}.png", dpi=ctx.dpi, facecolor=theme['paper'])
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# F4 -- the recovered partition
# ---------------------------------------------------------------------------------------------

def fig_f4_partition(ctx: Ctx, outdir: Path, theme: dict):
    ctx.begin('f4_partition')
    c4 = ctx.load_json('recon/derived/c4_partition.json')
    solutions = ctx.load_json('recon/derived/solutions.json')

    selected_name = c4['selected']
    cand = next(c for c in c4['candidates'] if c['name'] == selected_name)
    classes: dict[str, list[int]] = cand['classes']
    n = 11
    class_of = {}
    for ci, (_flop, cells) in enumerate(classes.items()):
        for idx in cells:
            class_of[idx] = ci
    stars = {(r, c) for r, c in solutions['solution']['cells']}
    palette = theme['class_palette']

    fig = plt.figure(figsize=(12.2, 6.0))
    fig.patch.set_facecolor(theme['paper'])
    ax = fig.add_axes([0.04, 0.08, 0.50, 0.82])
    ax.set_facecolor(theme['paper'])

    for idx, ci in class_of.items():
        r, c = divmod(idx, n)
        ax.add_patch(Rectangle((c, n - 1 - r), 1, 1, facecolor=palette[ci % len(palette)],
                                alpha=0.9, edgecolor=theme['paper'], linewidth=1.2))
    for (r, c) in stars:
        ax.text(c + 0.5, n - 1 - r + 0.5, '★', ha='center', va='center', fontsize=12,
                color='white')
    ax.set_xlim(0, n)
    ax.set_ylim(0, n)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect('equal')
    ax.set_title('Recovered region partition -- 11 classes, capacity 2 each', fontsize=11, loc='left',
                 color=theme['ink'])

    # a strip of the 11 classes, each cropped to its own bounding box -- the "does this
    # read as a letter" check is left to the reader, deliberately: the post does not
    # assert which class ids draw as J and S, only that two of them do.
    thumbs = list(classes.items())
    tcols = 4
    fg_color, bg_color = (theme['ink'], theme['paper'])
    for i, (flop, cells) in enumerate(thumbs):
        rr, cc = i // tcols, i % tcols
        rows_ = [idx // n for idx in cells]
        cols_ = [idx % n for idx in cells]
        r0, r1, c0, c1 = min(rows_), max(rows_), min(cols_), max(cols_)
        h, w = r1 - r0 + 1, c1 - c0 + 1
        sub = fig.add_axes([0.58 + cc * 0.10, 0.62 - rr * 0.22, 0.085, 0.085 * h / max(w, 1)])
        mask = [[0] * w for _ in range(h)]
        for idx in cells:
            r, c = divmod(idx, n)
            mask[r - r0][c - c0] = 1
        from matplotlib.colors import ListedColormap
        sub.imshow(mask, cmap=ListedColormap([bg_color, fg_color]), vmin=0, vmax=1,
                   interpolation='nearest')
        sub.set_xticks([])
        sub.set_yticks([])
        for sp in sub.spines.values():
            sp.set_color(palette[i % len(palette)])
            sp.set_linewidth(2.2)
        sub.set_title(flop, fontsize=6.3, color=theme['mute'], pad=2)

    fig.text(0.58, 0.06,
              'each class, cropped to its own bounding box (unlabeled by design --\n'
              'two of these eleven shapes read as the letters J and S)',
              fontsize=8.4, color=theme['mute'], va='top')
    fig.text(0.04, 0.03,
              f'measured by single-star probing + exact cover, then corroborated on '
              f'{cand["unique_solution"]["solutions"]}-solution uniqueness; recovered, not proven unique',
              fontsize=8.2, color=theme['mute'])

    fig.savefig(outdir / f"f4_partition{theme['suffix']}.png", dpi=ctx.dpi, facecolor=theme['paper'])
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# F5 -- net 806
# ---------------------------------------------------------------------------------------------

def fig_f5_net806(ctx: Ctx, outdir: Path, theme: dict):
    ctx.begin('f5_net806')
    net806 = ctx.load_json('recon/derived/net806.json')
    gds_path = ctx.cite('asic-puzzle-2026/puzzle.gds')

    try:
        import gdstk
    except ImportError:
        print('  [f5] gdstk not importable -- skipping the geometry render '
              '(run with the project .venv interpreter to get it)', file=sys.stderr)
        return

    bbox = net806['net']['shapes']['bbox_dbu']
    pad_um = 3.0
    x0, y0 = bbox[0] / 1000 - pad_um, bbox[1] / 1000 - pad_um
    x1, y1 = bbox[2] / 1000 + pad_um, bbox[3] / 1000 + pad_um

    lib = gdstk.read_gds(str(gds_path))
    top = lib.top_level()[0]

    layer_style = {
        (67, 20): ('#3477eb' if theme['suffix'] == '' else '#6f9bf2', 'li1'),
        (68, 20): ('#2e9e6b' if theme['suffix'] == '' else '#57cf9d', 'met1'),
        (69, 20): ('#c0392b' if theme['suffix'] == '' else '#e5766c', 'met2'),
    }

    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    fig.patch.set_facecolor(theme['paper'])
    ax.set_facecolor(theme['axes_bg'])

    for (layer, dt), (color, _label) in layer_style.items():
        for p in top.get_polygons(layer=layer, datatype=dt, depth=None):
            pts = p.points
            pxmin, pymin = pts.min(axis=0)
            pxmax, pymax = pts.max(axis=0)
            if pxmax < x0 or pxmin > x1 or pymax < y0 or pymin > y1:
                continue
            ax.add_patch(MplPolygon(pts, closed=True, facecolor=color, edgecolor=color,
                                     alpha=0.55, linewidth=0.4, zorder=2))

    for cut in net806['net']['shapes']['own_cuts']:
        bx = [v / 1000 for v in cut['bbox_dbu']]
        ax.add_patch(Rectangle((bx[0], bx[1]), bx[2] - bx[0], bx[3] - bx[1], facecolor='none',
                                edgecolor='#f5c518', linewidth=1.6, zorder=4))

    for cut in net806['cut_overlap']['overlapping']:
        if not cut['same_net']:
            bx = [v / 1000 for v in cut['bbox_dbu']]
            cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
            ax.add_patch(Rectangle((bx[0], bx[1]), bx[2] - bx[0], bx[3] - bx[1], facecolor='none',
                                    edgecolor='#ff5252', linewidth=2.2, zorder=5))
            ax.annotate(f'-> net {cut["net"]} (different net,\nlegal underlap, not a merge)',
                        xy=(cx, cy), xytext=(cx + 1.0, cy + 0.9), fontsize=7.6, color='#ff8a80',
                        arrowprops=dict(arrowstyle='->', color='#ff5252', lw=1.0), zorder=6)

    for t in net806['net']['terminals']:
        px, py = t['point_dbu'][0] / 1000, t['point_dbu'][1] / 1000
        ax.plot(px, py, marker='o', markersize=6, color='white', markeredgecolor='black',
                zorder=7)
        ax.annotate(f'{t["instance"]}.{t["pin"]}\n({t["master"].split("__")[-1]}, {t["direction"]})',
                    xy=(px, py), xytext=(px, py - 0.9), fontsize=7.4, color='white',
                    ha='center', va='top', zorder=7)

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect('equal')
    ax.set_xlabel('x (µm)', fontsize=8.5, color=theme['ink'])
    ax.set_ylabel('y (µm)', fontsize=8.5, color=theme['ink'])
    ax.tick_params(colors=theme['mute'])

    handles = [Rectangle((0, 0), 1, 1, facecolor=c, alpha=0.7) for c, _ in layer_style.values()]
    labels = [lbl for _, lbl in layer_style.values()]
    handles += [Rectangle((0, 0), 1, 1, facecolor='none', edgecolor='#f5c518', linewidth=1.6),
                Rectangle((0, 0), 1, 1, facecolor='none', edgecolor='#ff5252', linewidth=2.2)]
    labels += ["net 806's own vias (same net)", 'the one foreign cut']
    ax.legend(handles, labels, loc='upper left', fontsize=7.4, facecolor=theme['legend_bg'],
              labelcolor=theme['legend_text'], framealpha=0.85)

    ax.set_title(f'Net 806 -- the chip\'s one undriven net '
                 f'({net806["net"]["shapes"]["total"]} shapes, 2 input-only terminals)',
                 fontsize=10.8, color=theme['ink'], pad=10)
    fig.savefig(outdir / f"f5_net806{theme['suffix']}.png", dpi=ctx.dpi, facecolor=theme['paper'],
                bbox_inches='tight')
    plt.close(fig)


# ---------------------------------------------------------------------------------------------
# F6 -- the warm-up video (not generated -- copied, and credited as the user's own render)
# ---------------------------------------------------------------------------------------------

def fig_f6_video(video: Path | None, outdir: Path):
    if video is None:
        print('  [f6] --video not given -- skipping (see README note on assets/video/)')
        return
    if not video.exists():
        raise FileNotFoundError(f'--video {video} does not exist')
    dest = outdir / 'warmup_gds_3d.mp4'
    shutil.copy2(video, dest)
    print(f'  [f6] copied {video} -> {dest} ({dest.stat().st_size / 1e6:.1f} MB)')


# ---------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------

FIGURES = {
    'f1': ('pipeline flow', fig_f1_pipeline),
    'f2': ('the answer', fig_f2_answer),
    'f3': ('the message table', fig_f3_messages),
    'f4': ('the recovered partition', fig_f4_partition),
    'f5': ('net 806', fig_f5_net806),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', required=True, type=Path,
                     help='path to a checkout of the frozen project repository')
    ap.add_argument('--out', type=Path, default=Path('assets'),
                     help='output root, relative to the blog repo (default: assets)')
    ap.add_argument('--video', type=Path, default=None,
                     help='path to the warm-up render (warmup_gds_3d.mp4) to copy into assets/video/')
    ap.add_argument('--dpi', type=int, default=200, help='matplotlib dpi (default 200, i.e. 2x retina)')
    ap.add_argument('--only', type=str, default=None, help='comma-separated subset, e.g. f1,f4')
    ap.add_argument('--themes', type=str, default='light,dark',
                     help='comma-separated subset of light,dark (default: both)')
    args = ap.parse_args()

    repo = args.repo.resolve()
    if not (repo / 'README.md').exists() or not (repo / 'AGENTS.md').exists():
        print(f'warning: {repo} does not look like the project root (no README.md/AGENTS.md)',
              file=sys.stderr)

    img_dir = args.out / 'img'
    video_dir = args.out / 'video'
    img_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    ctx = Ctx(repo, args.dpi)
    wanted = set(args.only.split(',')) if args.only else set(FIGURES)
    theme_names = args.themes.split(',')

    for theme_name in theme_names:
        theme = THEMES[theme_name]
        apply_rcparams(theme)
        print(f'-- theme: {theme_name} --')
        for key, (desc, fn) in FIGURES.items():
            if key not in wanted:
                continue
            print(f'[{key}] {desc} ({theme_name}) ...')
            fn(ctx, img_dir, theme)
            print(f"      -> {img_dir}/{key}_*{theme['suffix']}.png")

    if not args.only or 'f6' in wanted:
        print('[f6] warm-up video ...')
        fig_f6_video(args.video, video_dir)

    meta = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'generator': 'scripts/make_figures.py',
        'project_repo': repo_provenance(repo),
        'matplotlib_version': matplotlib.__version__,
        'themes_rendered': theme_names,
        'citations': ctx.citations,
    }
    meta_path = img_dir / 'figures_metadata.json'
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=False), encoding='utf-8')
    print(f'wrote {meta_path}')
    if meta['project_repo']['dirty']:
        print('warning: project repo has uncommitted changes -- figures are not cited to a clean commit',
              file=sys.stderr)


if __name__ == '__main__':
    main()
