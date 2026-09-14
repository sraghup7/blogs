---
layout: post
title: "Reverse-engineering Jane Street's ASIC puzzle: the route I took"
date: 2026-09-14
categories: [hardware]
tags: [asic, reverse-engineering, gds, verilog, klayout, sky130, jane-street]
permalink: /janestreet-asic-puzzle/
description: "How I recovered a gate-level netlist from a GDSII layout with no schematic, found the chip's hidden rule by measuring it, and derived the 121-bit input that makes it print TWO STARS — including two results that disagree with the published writeup, and one I could not prove."
---

**I know I'm late to the party, but here is the methodology I used to tackle Jane Street's ASIC
reverse-engineering problem.**

Submissions closed on 4 September 2026, and the answer has been public for a while, so nothing here is
a competitive entry. What I want to write down is the *route*: a layout file plus a promise that a chip
prints a message, and everything I had to build in between. I derived the answer independently, by a
route I chose rather than one I copied — which turned out to matter, because it produced two
measurements that disagree with the published writeup, and one result I could not prove at all.

## A trading firm, a chip, and no schematic

Jane Street is a quantitative trading firm that likes to release hard problems — puzzles, games,
competitions — as a way of meeting people who enjoy them. This one was different from their usual
fare: instead of a puzzle *about* hardware, it shipped hardware work.

In 2026 they taped out a small chip on the open **SkyWater 130 nm** process and published the final
**GDSII layout** — the file you send to a fab, which is polygons on layers and nothing else. Alongside
it came a reference VCD (a waveform log of some inputs and outputs), and a much smaller **warm-up
design** handed over *with* its correct netlist, so you could calibrate your tools against a design
where you already knew the answer.

The chip reads a 121-bit bitmap, one bit per clock cycle, and then answers with a short ASCII message.
A single output line, `success`, is its verdict. The task is to find the input that makes it succeed,
and read what it prints.

## The problem in my own words

Take 121 bits, almost all zero. The interface is small: a reset, a clock, an enable, a single serial
data line, an 8-bit output bus, and `success`. The timing is fixed — 3 cycles of reset, 1 idle cycle,
then exactly 121 bits fed in one per cycle — and the chip prints its message a few cycles after the
last bit arrives.

The catch is what you are given: **polygons, not a netlist.** There is no schematic, no library of
standard cells in a form a simulator reads, no list of which polygon is connected to which. So this is
two problems stacked:

1. recover a gate-level netlist from geometry alone — work out what each cell is, which cells exist,
   where they sit, and how they are wired; and
2. work out which of the 2<sup>121</sup> possible inputs the chip will accept, and what makes it say so.

Most people who solved it had a PDK library and a formal verification stack. I had Python, a layout,
and a preference for fewer moving parts.

## The approach I chose

Four decisions shaped everything downstream. Each was a way of removing a thing that could be silently
wrong.

**Let the chip describe itself.** A standard cell library normally comes with a LEF file telling you
where each cell's pins are and a set of Verilog primitives telling you what each cell does. Those files
are convenient and they are also a second source of truth that can disagree with the artwork. So I took
neither. Instead I read the layout's *own* standard-cell masters: the pin names are inside the layout as
text labels on the cells, and each pin's geometry is the conductor shape that label sits on. The layer
stack — which layer is a wire, which is a via — I derived the same way, from the geometry of the via
masters themselves. A wrong layer map becomes impossible, because there is no map to be wrong: there is
only the artwork.

**Use a real connectivity engine.** A GDS has no concept of "a net". You have to define connectivity
yourself and then trace it. Rather than hand-write polygon merging, I drove KLayout's built-in
extraction engine, configured entirely from the layer rules the chip itself gave me. Less code I could
get wrong, and a mature engine doing the geometry.

**Measure the hidden rule; don't assume it.** The 121 bits are not unconstrained — the chip's `success`
depends on more than the counts you can see. The published approach recovered that hidden structure by
assuming a form and probing for it. I measured instead: sweep a single bit through all 121 positions,
record which internal state elements react to it, and *find* the structure as an exact cover over those
measurements. What I found disagrees with the published account, and I'll come to that.

**Derive the answer with my own search.** The final step is a constraint problem with a small search
space. I wrote two independent enumerators and required them to agree. No SAT solver, no formal
`cover()` call — partly because the search is tractable, and partly because a solver that says
"unsatisfiable" teaches you nothing about *why*.

![The six moves, with the measured number that carries each](/blogs/assets/img/f1_pipeline.png)

### Tech stack

Python 3.11 with **gdstk** (reading GDSII in integer database units, no floating-point geometry),
**klayout** (the extraction engine and geometry queries), **matplotlib** (the figures in this post), and
**iverilog** for the simulation cross-checks. Deliberately absent: the SkyWater PDK, any LEF file,
`shapely`, and every formal/SMT tool. Every figure and number below comes out of a committed artifact
that a script regenerates from the layout — the post's numbers are checked against those artifacts, not
retyped.

The code in this project was written with an AI coding agent — DeepSeek's model working through the
Hermes Agent harness — under a written protocol I fixed before I started. That protocol is what makes
the result checkable rather than merely plausible: every step had to end in an executable gate, and
anything I had not measured had to be recorded as unproven.

## Step 1 — Pins, from the artwork

The layout carries 41 distinct `(layer, datatype)` pairs. Classifying them by structural evidence only
— which ones appear in via masters, which carry long wires, which carry text — gives 9 via masters,
which in turn give the connectivity rule set: which conductor layers each via type joins. That table is
the whole of my "technology file".

Then the cells. Each of the 69 master cells carries its pin names as text labels; each name sits on the
conductor geometry that is its pin. I read both, in integer database units, and closed each pin's layer
set through the via rules so that a pin reaching metal 1 can be matched against metal 1 routing.

The calibration that matters: the warm-up design ships with its real netlist, and my extraction of the
warm-up reproduces that netlist exactly — **230 placements, 84 nets, zero differing net signatures**.
That is the check that the rules I derived from the artwork are the real ones.

<video controls preload="metadata" style="width:100%">
  <source src="/blogs/assets/video/warmup_gds_3d.mp4" type="video/mp4">
</video>

*A 25-second render of the warm-up layout (1280×1302). Worth a look, because it makes the point that
this is routed silicon: cells on a grid, wires snaking across several metal layers, vias wherever a
wire changes layer.*

## Step 2 — Placements

The chip contains **1,618 placed cells**. Three properties of this layout made the recovery
unambiguous: every placement sits exactly on the 0.46 µm site grid, only every other row is populated
(so no two cells can overlap vertically), and there are no 90° rotations at all — every cell is at 0° or
180°, possibly mirrored.

That last point matters more than it sounds. A layout tool describes orientation in ways that are easy
to misread, and misreading it is how you end up with a phantom population of rotated cells. Rather than
trust a convention, I fixed it empirically: compute each instance's bounding box from its master and
its transform, and require it to equal the bounding box measured from the layout itself. Exactly one
transform convention satisfies that for **all 1,618** instances.

## Step 3 — Connectivity, and a netlist

Now the geometry becomes a circuit. The engine, driven by the derived rules, files **40,360 conductor
shapes** onto nets: every single shape lands in exactly one net, with **2,626 nets** and no orphans.
Power and ground are identified the strong way — not as "the two biggest nets" but by the pin names
they carry (`VPWR`, `VGND` from the layout's own labels).

Then the wiring: every functional pin of every instance is mapped onto exactly one net — **2,777 of
2,777**, with zero conflicts. What is left over is 972 unconnected supply pins, and all 972 are
explained by two predicted classes (well ties with no routeable geometry, and antenna-diode supply
squares). An unexplained gap would have been a failure here; a *classified* gap is a result.

What comes out is a gate-level netlist of the whole chip: 1,618 cells, 2,626 nets, and a list of which
pin of which cell connects to what.

## Step 4 — Models, validated twice

A netlist is only useful with cell behaviour. I wrote behavioural models for the cell families from
their pin names and structure, and then validated them against **two independent oracles**:

* the warm-up design, whose correct netlist I hold — the whole chain (layout → extraction → models)
  reproduces it exactly; and
* the reference VCD. I simulated the chip with the documented stimulus and compared outputs
  instant-by-instant, byte for byte: **312 cycles, 2,808 output bits, zero mismatches, and no unknown
  bits.**

The VCD check matters because it is the only evidence that my *models* — not just my wiring — are right.
A netlist with subtly wrong cell behaviour can still look plausible.

## Step 5 — The hidden rule, by measurement

This is where the project earned its keep.

The visible constraints on the 121 bits are easy to read off once the chip is simulated: 22 ones, two
per row, two per column, and no two set bits adjacent (horizontally, vertically or diagonally). Those
four rules alone admit thousands of inputs, so there must be more: the chip's message vocabulary
distinguishes "you broke the hidden rule" from "you broke a visible one".

The published account says the grid is divided into 11 regions, and that each region has its own
counter. So I went looking for those counters. I mapped every state element in the netlist, found the
counters, and the picture that emerged was different: the eleven counters are the eleven **column**
counters. One per column, each ticking when that column's bits arrive. There is no per-region decode
anywhere in this netlist and no per-region counter to find — I went after that object several different
ways, and the honest summary is that it is not in this design.

So I measured the rule instead. Set exactly one bit, run the chip, and record which internal state
elements end high: that gives every latch a *trigger set* — the cells it reacts to. Then solve for the
structure directly: find every sub-collection of those sets that partitions the 121 cells exactly. Two
capacity-2 covers come out — eleven classes, each holding exactly two of the accepted board's set bits.
One of them is just "the columns" (which adds nothing, since two-per-column is already a visible rule);
the other is a genuinely different partition, and it is the one that pins the accepted input.

![The recovered partition, as measured](/blogs/assets/img/f4_partition.png)

*The partition I recovered, as measured: 11 classes over the 121 cells, two of the answer's set bits in
each. Class sizes run from 4 to 28 cells — it is not the tidy 11-column picture, and I deliberately
draw it as measured rather than as anything prettier.*

Then I tested it against the chip *through its messages*. I built boards that satisfy the recovered
partition and have exactly one visible flaw — an adjacent pair — and asked the chip what it thought.
**All 23 of them print `TWO NOT TOUCH`** ("everything else is fine; your bits are touching"). And the
controls that break the partition while also having an adjacent pair — **8 of them** — do not. That
contrast is what turns a candidate partition into something the hardware itself corroborates.

## Step 6 — The answer

With four mechanical rules plus the recovered partition, the search is small, and it has exactly **one**
solution — an exhaustive 715,877-node search that is allowed to find a second one and does not. Two
independently written enumerators — a row-by-row search and a bitmask enumerator — agree on both the
solution and the total count, and an independent validator recomputes the constraints from the grid.

The accepted board:

```text
.......*.*.
*....*.....
.......*.*.
*.*........
....*.*....
..*.....*..
....*.....*
.*....*....
...*......*
.....*..*..
.*.*.......
```

Its 121-bit feed order, top-left cell first:

```text
0000000101010000100000000000010101010000000000001010000001000001000000100000101000010000000100000010000010010001010000000
```

Fed that vector, the chip asserts `success` at **cycle 126**, and prints **`(* TWO STARS *)`**.

![The accepted board](/blogs/assets/img/f2_answer.png)

![The five messages and their triggers](/blogs/assets/img/f3_messages.png)

The chip's vocabulary is small and precise: `EMPTY SKY` for all zeros, `BIG BANG` for all ones,
`TRY AGAIN` for everything else that is wrong, `TWO NOT TOUCH` when adjacency is the *only* fault, and
`(* TWO STARS *)` on success. The interesting one is `TWO NOT TOUCH`: it exists precisely because the
hidden rule is real, and it is the message that let me corroborate the partition.

## How I convinced myself the result is right

The answer matching a published value proves very little on its own — I knew the target. So the
verification is about the route:

* **33 gates**, one per executed step, each re-deriving what it asserts from the artifacts or the
  netlist rather than trusting a stored number. Several gates deliberately rebuild the extraction
  engine and re-measure, which is why the fast ones still take seconds.
* **Fault injection as a meta-gate.** For every artifact, a script mutates it — claims a second
  solution, flips one bit of the answer, upgrades a partial verdict to a full one — and requires that
  the *owning* gate fails and no other gate does. **129 injected faults, each caught by its owner.**
  A gate that cannot fail is not a gate.
* **Reproducibility.** One command deletes every derived artifact the repository tracks, rebuilds all
  of them from the layout, and compares bytes against what was committed: **32 of 32 identical, 30
  stages, about seven minutes.**
* **Honesty checks that can fail.** The acceptance matrix is allowed to contain a partial result, and a
  gate fails if the partial result is silently upgraded or its reasons are deleted.

That discipline paid for itself twice. It caught a defect in my *own* verification evidence — the
reproducibility report was being deleted by the run and could not rebuild itself, so the gate certifying
it had been passing on an older copy — and it caught a net-name collision where a key that was unique
within one part of the hierarchy was silently merging unrelated nets in another. The second one had
produced a confident, plausible, wrong answer. That is the failure mode worth engineering against,
because nothing crashes.

## Where my measurements disagree with the published writeup

Two specific claims, stated as measurements rather than opinions:

**The per-region counters.** The published method recovers the map by probing one cell at a time and
watching a per-region counter fire. In this netlist, the eleven counters are the eleven *column*
counters, and there is no per-region counter. Implemented faithfully — one star at a time, watching for
a region counter to tick — the method returns columns, because columns are the only eleven-way
structure present.

**"Whatever breaks on the full netlist also breaks on the warm-up."** This is a good heuristic and I
used it. It is not a rule. Two of my most expensive defects were *invisible* on the warm-up: a pin
assignment for cell types the warm-up does not contain at all (so nothing there could check it), and a
net key that was unique only within a single circuit of the hierarchy (the warm-up is small enough to
have exactly one). The warm-up is the best oracle available, and it has a coverage boundary you only
find by crossing it.

Neither point says the puzzle's answer is wrong. It isn't — it matched. They are claims about how this
particular netlist is described, and they changed what I could assume.

## What I did not prove

I would rather write this section than have someone find it themselves.

**The region map is recovered and corroborated, not confirmed.** The accepted input is *unique*, so the
chip's verdicts cannot distinguish my partition from a look-alike: of 200 partitions of the same shape,
188 behave identically under every rejection test. The message channel does corroborate mine (23 boards
for, 8 controls against), but that is a sample near the answer, not a proof over the space. So the claim
is "recovered by measurement, corroborated by the hardware, with the strength of that evidence
measured" — not "the map, proven".

**My recovery does not spell anything.** The published writeup reads the map as the letters "JS". I
recovered a partition, drew it as measured, and it does not read as those letters. I am not going to
draw letters I did not find.

**One character of one message is decided by a floating node.** On the `TWO NOT TOUCH` path, one printed
character depends on a net that the layout leaves **structurally undriven** — both of its terminals are
cell inputs, nothing drives it. I tested three explanations and refuted all three: no constant cell ties
it (the nearest is ~10 µm away), the pin assignment is right (a rebuilt engine recovers the same two
terminals), and no missed via merge hides a driver (the one via overlapping the wire sits on a layer
pair the wire does not occupy there, so it cannot merge). The character is genuinely indeterminate, which
means the chip is nondeterministic in exactly one place: one character of one of its five messages.

![Net 806: the layout leaves it undriven](/blogs/assets/img/f5_net806.png)

*The undriven net: 17 shapes across metal 1–3 and two via types, four of its own vias, and the one
foreign via (red, dashed) that overlaps it — on a layer pair the wire does not use there, so there is
nothing to merge.*

## What I took away

The answer is public, so the value here was never the string of 121 bits. What I got out of it:

* a **gate-level netlist recovered from polygons alone** — no PDK, no LEF, no schematic — with every
  stage verified against an oracle I did not author;
* a **measured** hidden rule, with the limits of that measurement stated numerically;
* and a verification habit I now think of as the real deliverable: every claim has an owner, every
  owner can fail, and every number can be regenerated from the source in one command.

The second half of the problem — the part nobody tells you — is that a pipeline which produces a
plausible wrong answer is worse than one that produces nothing, because the wrong answer is invisible
unless you build the checks that can contradict you. Two of my nastiest bugs were exactly that, and both
were caught by a check rather than by intuition.

Jane Street announced a follow-up for later in 2026: design your own chip, and the best entries get
fabricated. That is the *other* direction — going from a netlist to silicon rather than silicon to a
netlist — and after this exercise I am considerably more interested in it.
