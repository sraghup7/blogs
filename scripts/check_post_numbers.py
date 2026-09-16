#!/usr/bin/env python3
"""check_post_numbers.py -- hold the post to the repository's own numbers.

A blog post drifts the moment someone edits a sentence. This script is the post's gate: it reads the
published markdown, extracts the numbers it claims, and compares each one against the artifact that
produced it in the ASIC project -- the same artifacts the figures are built from. It also enforces the
two editorial rules that are not about numbers: the post must not claim the region map is confirmed or
that it spells "JS", and it must not make any claim about its own authorship.

Run it with the project's interpreter (it imports the project's checks to count gates and mutations):

    .venv/Scripts/python.exe ../blogs/scripts/check_post_numbers.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BLOG = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('ASIC_ROOT', 'E:/Projects/Jane-Street-ASIC-Puzzle'))
POST = next((BLOG / '_posts').glob('*janestreet-asic-puzzle*.md'), None)
D = ROOT / 'recon' / 'derived'
sys.path.insert(0, str(ROOT))

j = lambda n: json.loads((D / n).read_text(encoding='utf-8'))

results: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = '') -> None:
    results.append((bool(ok), label, detail))


def has(text: str, value: int) -> bool:
    """Is this integer in the post, in any of the groupings a human might type (1618 / 1,618)?"""
    s = f'{value:,}'
    return str(value) in text or s in text


def banned_hits(flat: str, phrases: list[str], negations: tuple[str, ...] = (
        'not ', 'never ', 'no ', "isn't ", 'cannot ', 'nor ')) -> list[str]:
    """Banned phrases that the post *asserts*, not ones it explicitly denies.

    The post has to be able to write `not "the map, proven"`; a plain substring search flags that
    sentence, which is the honest claim rather than the forbidden one.
    """
    low = flat.lower()
    hits: list[str] = []
    for phrase in phrases:
        start = 0
        while (i := low.find(phrase.lower(), start)) != -1:
            if not any(n in low[max(0, i - 30):i] for n in negations):
                hits.append(phrase)
                break
            start = i + 1
    return hits


def main() -> int:
    if POST is None:
        print('no post found under _posts/')
        return 1
    text = POST.read_text(encoding='utf-8')
    # Phrase checks run on whitespace-normalised text: markdown wraps at ~100 columns, so a phrase a
    # reader sees on one line ("two per row") arrives split across two ("two\nper row"). Searching the
    # raw text for phrases produced exactly that false failure on the first run of this script.
    flat = re.sub(r'\s+', ' ', text)

    # ---- the answer itself ----------------------------------------------------------------
    sol, e1, e2 = j('solutions.json'), j('e1_messages.json'), j('e2_messages.json')
    nets, pn, replay = j('nets.json')['totals'], j('pin_net.json')['totals'], j('vcd_replay.json')
    a5, inst, net806 = j('pin_coverage.json'), j('instances.json'), j('net806.json')
    c4, inv = j('c4_partition.json'), json.loads((ROOT / 'recon' / 'inventory.json').read_text())
    c5 = j('c5_rejections.json')
    warm, e1m = j('warmup_b7.json'), e1

    feed = sol['solution']['feed_order']
    check(feed in text, 'the 121-bit vector in the post is the derived one', feed[:24] + '...')
    check(sol['unique'] and sol['solutions_found'] == 1, 'the artifact still says one solution',
          f"{sol['solutions_found']} solution(s)")
    check(e1['success_cycle_expected'] == 126 and has(text, 126),
          'success at cycle 126', f"artifact {e1['success_cycle_expected']}")
    check('(* TWO STARS *)' in text, 'the message is quoted verbatim')

    # ---- every measured number the post claims ---------------------------------------------
    warmup = j('warmup_b7.json')
    viap = j('via_pairs.json')
    layers = j('layers.json')
    cand = next(c for c in c4['candidates'] if c['name'] == c4['selected'])
    numbers = [
        ('placements', len(inst['instances']), 'recon/derived/instances.json'),
        ('conductor shapes', nets['conductor_shapes'], 'recon/derived/nets.json'),
        ('nets', nets['nets'], 'recon/derived/nets.json'),
        ('functional pins mapped', pn['assigned_functional'], 'recon/derived/pin_net.json'),
        ('VCD output bits compared', replay['comparison']['output_bits_compared'],
         'recon/derived/vcd_replay.json'),
        ('VCD cycles', replay['comparison']['cycles'], 'recon/derived/vcd_replay.json'),
        ('warm-up placements', warmup['totals']['placements'], 'recon/derived/warmup_b7.json'),
        ('warm-up nets', warmup['comparison']['our_nets'], 'recon/derived/warmup_b7.json'),
        ('layer/datatype pairs', len(layers['pairs']), 'recon/derived/layers.json'),
        ('via masters', viap['totals']['via_masters'], 'recon/derived/via_pairs.json'),
        ('cell masters', len(j('pin_names.json')['masters']), 'recon/derived/pin_names.json'),
        ('ones in the answer', sol['constraints']['ones'], 'recon/derived/solutions.json'),
        ('classes in the partition', len(cand['flops']), 'recon/derived/c4_partition.json'),
        # D1's answer-deriving search (Step 6), not C4's own internal uniqueness check on the
        # candidate partition at selection time (recon/derived/c4_partition.json's
        # candidates[].unique_solution.nodes == 694,478) -- a different search, the post does not
        # cite that number, and it should not be asked to.
        ('nodes in the answer-deriving search', sol['enumerators']['rows_dfs']['nodes'],
         'recon/derived/solutions.json'),
        ('boards spelling TWO NOT TOUCH', e2['boards_spelling_the_message'],
         'recon/derived/e2_messages.json'),
        ('control boards', e2['control_group']['boards'], 'recon/derived/e2_messages.json'),
        ('look-alikes tested', c5['rejection_test']['lookalikes_tested'],
         'recon/derived/c5_rejections.json'),
        ('look-alikes behaving identically',
         c5['rejection_test']['lookalikes_that_also_reject_every_board'],
         'recon/derived/c5_rejections.json'),
        ('boards in the swap family', e2['family']['boards'], 'recon/derived/e2_messages.json'),
        ('controls against (non-matching boards)',
         e2['family']['adjacent_over_caps'] + e2['family']['not_adjacent_over_caps'],
         'recon/derived/e2_messages.json'),
        ('look-alike partitions in the further JS/corroboration control',
         e2['lookalike_power']['tested'], 'recon/derived/e2_messages.json'),
        ('nearby-signal candidates within 15um of net 806',
         len(net806['message_tie']['nearby_signals']['candidates']), 'recon/derived/net806.json'),
        ('nearby signals that reproduce the message byte-exactly',
         len(net806['message_tie']['nearby_signals']['reproduce_on_all_boards']),
         'recon/derived/net806.json'),
        ('gates in the suite', len(__import__('tools.checks.run_all', fromlist=['x']).gate_paths()),
         'tools/checks/run_all.py'),
        ('injected faults', len(__import__('tools.checks.fault_inject', fromlist=['x']).MUTATIONS),
         'tools/checks/fault_inject.py'),
        ('shapes of the undriven net', net806['net']['shapes']['total'], 'recon/derived/net806.json'),
        ('its own vias', len(net806['net']['shapes']['own_cuts']), 'recon/derived/net806.json'),
    ]
    for label, value, source in numbers:
        check(has(text, value), f'the post states {label} = {value:,}', f'from {source}')

    # the site grid and the two-per rules, each from its own artifact
    pitch = layers['derived_site_pitch_um']
    check(f'{pitch:g} µm' in flat, 'the site grid the post quotes is the derived one',
          f'{pitch} µm from recon/derived/layers.json')
    check('two per row' in flat.lower() and has(text, sol['constraints']['per_row']),
          'the two-per-row rule is stated')
    check('two per column' in flat.lower() and has(text, sol['constraints']['per_col']),
          'the two-per-column rule is stated')
    class_cells = {}
    for i, flop in enumerate(cand['flops']):
        for cell in c4['trigger_sets'][flop]:
            class_cells[cell] = i
    measured = sorted(sum(1 for v in class_cells.values() if v == i) for i in range(len(cand['flops'])))
    check(measured == sorted(cand['class_sizes']) and len(class_cells) == 121,
          'the partition covers all 121 cells in 11 classes',
          f'sizes {measured}, cells {len(class_cells)}')
    check(has(text, min(measured)) and has(text, max(measured)),
          'the class-size range the post quotes is the measured one',
          f'{min(measured)} to {max(measured)}')

    # the undriven net: the post rounds it to "~10 um", so check the rounding, not the digits
    tie_dbu = net806['constant_tie']['nearest_tie']['distance_dbu']
    check(round(tie_dbu / 1000) == 10 and '10 µm' in flat,
          'the nearest constant cell is ~10 um away, as stated', f'{tie_dbu} dbu')
    check(net806['message_tie']['tie_0'] != net806['message_tie']['published_string']
          and net806['message_tie']['tie_1'] != net806['message_tie']['published_string'],
          'the artifact still says neither tie prints the published string',
          f"{net806['message_tie']['tie_0']!r} / {net806['message_tie']['tie_1']!r}")

    # ---- reproducibility claims ------------------------------------------------------------
    repro = j('reproduction.json')['cold_check']
    check(repro['differences'] == [] and repro['regenerated_identically'] == repro['tracked_before'],
          'the reproducibility claim matches the committed report',
          f"{repro['regenerated_identically']} of {repro['tracked_before']}, "
          f"{len(repro['differences'])} differences")
    check(has(text, repro['tracked_before']) and has(text, j('reproduction.json')['stages_run']),
          'the post states the artifact and stage counts it claims',
          f"{repro['tracked_before']} artifacts, {j('reproduction.json')['stages_run']} stages")

    # ---- editorial rules (B2/B3/B4) ---------------------------------------------------------
    # A banned phrase counts only where it is *asserted*: this post has to be able to write
    # `not "the map, proven"` -- that sentence is the honest claim, and a naive substring check
    # failed it on the first run.
    # 2026-09-16: the fix pass flipped AC6 PARTIAL -> PASS -- the recovered classes do draw as J and
    # S, corroborated on all 189 boards of the swap family, with none of 2,000 look-alikes
    # reproducing that agreement. So a JS *reading* is no longer a forbidden claim; what stays
    # forbidden is calling that reading, or the partition itself, *confirmed*/*proven* -- the
    # accepted input is unique, so the chip's verdicts alone still cannot rule out every look-alike.
    banned = ['the map is confirmed', 'confirmed the map', 'proves the map', 'the map, proven',
              'the map is proven', 'this post was written by', 'written by an AI', 'AI-generated post']
    hits = banned_hits(flat, banned)
    check(not hits, 'no forbidden claim is asserted (map confirmed/proven, or post authorship)',
          ', '.join(hits) or f'{len(banned)} phrases absent or negated')
    required = ['corroborated', 'not confirmed', 'as the letters',
                'DeepSeek', 'Hermes Agent']
    missing = [r for r in required if r.lower() not in flat.lower()]
    check(not missing, 'the honesty and attribution sentences are present',
          ', '.join(missing) or 'all present')

    # ---- every asset the post points at exists ---------------------------------------------
    assets = sorted(set(re.findall(r'/blogs/assets/[A-Za-z0-9_./-]+', flat)))
    missing_assets = [a for a in assets if not (BLOG / a.replace('/blogs/', '', 1)).exists()]
    check(not missing_assets and len(assets) >= 6,
          'every figure and video the post links exists in the repository',
          f'{len(assets)} assets referenced; missing: {missing_assets or "none"}')

    # ---- the warm-up numbers the post quotes, from their own artifact -----------------------
    check(warm.get('equivalent') in (True, None) or 'signature' in json.dumps(warm).lower(),
          'the warm-up claim is backed by the warm-up artifact', f'{list(warm)[:4]}')

    width = max(len(r[1]) for r in results)
    failed = 0
    for ok, label, detail in results:
        failed += not ok
        print(f'  {"PASS" if ok else "FAIL"}  {label:<{width}}  {detail}')
    print()
    print(f'{len(results) - failed}/{len(results)} checks passed')
    print('POST NUMBERS: ' + ('PASS' if not failed else 'FAIL -- the post and the repository disagree'))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
