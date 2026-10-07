# The night clock

How long a release takes to land once the song is done. This is the baseline:
the last six releases, before any work to make release night faster or to
log it as it runs.

**Measured, rough.** Every number below comes from file modification times in
each release's own folder on the Mac it shipped from. A modification time is
when a file there was last written, which makes this a partial clock:

- The creative work on these releases (the piece, the drafts, the renders) ran
  in cloud sessions first. A folder only shows what landed on the Mac, so this
  is the **landing** part of the night: films, cuts, covers, transfer parts,
  the mux.
- A file copied with its original time, or touched again later, shifts a row.
- A **session** is the densest burst of writes, split wherever the folder sat
  untouched for more than six hours. Writes outside it are listed, not counted.

| Release | Landing session (local time, 2026) | Length | Files written in it | Transfer parts in the folder | Outside the session |
|---|---|---|---|---|---|
| HAMECHI MANZOR DARE | 21 Sep 23:27 → 22 Sep 00:20 | 0.9 h | 15 | — | the song pack measured for this repository's port, a week later |
| ( - ) | 24 Sep 01:00 → 01:33 | 0.5 h | 39 | 15 · 143 MiB | an audio file the next night; the port's song pack |
| SAME AS YOU | 27 Sep 00:59 → 03:09 | 2.2 h | 81 | 15 · 249 MiB | the port's song pack |
| SHOULD I ? | 29 Sep 01:26 → 03:55 | 2.5 h | 86 | 14 · 192 MiB | the port's song pack |
| Setareh | 2 Oct 22:51 → 3 Oct 01:33 | 2.7 h | 48 | — | — |
| ⛈️ STORM | 5 Oct 12:30 → 14:32 | 2.0 h | 57 | 10 · 178 MiB | the master, a day and a half earlier |

Transfer parts are the hand-split files a release moved through on its way from
a cloud session to the Mac, most of them 18 MiB (18,874,368 B, measured); ( - )
also used 8 MiB ones.

## What it shows

- **Landing takes about two hours.** The median session is 2.1 h (measured,
  from the six rows); the four most recent run 2.0–2.7 h. The two short ones are
  the earliest canvas releases, which landed fewer files.
- **It is a night clock.** Five of the six sessions start between 22:51 and
  01:26 local time.
- **Four of six moved through split transfer parts**: 54 parts, 762 MiB in all
  (measured). Rendering the finals on the Mac removes that step (inferred).
- **What it can't show** is the whole night, from the master arriving to the
  last file delivered, with the time each stage took. Nothing logged that; the
  baseline exists so the first release night that does log it has something to
  be compared with.

## Re-running it

On any release folder (the output names no files):

```bash
python3 - /path/to/release-folder <<'EOF'
import os, re, sys, time
files = [os.path.join(r, f) for r, _, fs in os.walk(sys.argv[1]) for f in fs if f != ".DS_Store"]
ts = sorted(os.lstat(f).st_mtime for f in files)
sessions, start, prev = [], ts[0], ts[0]
for t in ts[1:] + [float("inf")]:
    if t - prev > 6 * 3600:
        sessions.append((start, prev, sum(start <= x <= prev for x in ts)))
        start = t
    prev = t
at = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
for a, b, n in sessions:
    print(f"{at(a)} -> {at(b)}  {(b - a) / 3600:.1f} h  {n} files")
# transfer parts: the hand-split pieces of one file (x.part03, x.bin, x_part_03, ...)
parts = [f for f in files if re.search(r"\.(bin|part\d*)$|part[^/]*\d\d[^/]*$", f, re.I)]
sizes = sorted({os.lstat(f).st_size for f in parts}, reverse=True)[:2]
print(f"{len(parts)} transfer parts, {sum(os.lstat(f).st_size for f in parts) / 2**20:.0f} MiB"
      + (f", largest {', '.join(f'{s:,} B' for s in sizes)}" if parts else ""))
EOF
```

The session with the most files is the row's landing session; the last line
is its transfer parts.
