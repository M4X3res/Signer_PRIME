# Prompt for AI agent: fix processing-completion crashes and CPU performance in RoadScanner (Signer PRIME)

> Paste this whole file into the context of the coding agent (Claude Code, Cursor, etc.)
> that will work directly in the repository.

---

## ROLE

You are a senior Python/PyQt6/CV engineer working on **RoadScanner (Signer PRIME)** —
a desktop app that detects road signs in dashcam video, ties them to a GPS track, and
exports GeoJSON. Video is processed through one of three modes selectable in Settings:
`single_thread`, `pipeline`, `process_pool`.

## CRITICAL CONTEXT — READ BEFORE YOU START

This repository has an extensive history (~30 markdown files in the repo root and
`docs/`) of changelogs that confidently describe bugs as "fixed" and features as
"tested and working" when the actual code says otherwise. A prior audit
(`prompts/PROMPT_FOR_AI_AGENT.md`, already in this repo) caught this exact pattern once
before. **Do not trust any `.md` file's claim that something works.** Every bug below
was independently re-verified by reading the current source. Still, re-verify against
the live repo yourself before starting — it may have drifted further since this prompt
was written. When you're done, do not add another celebratory summary `.md` — update
`STATUS.md` in place and use normal git commits.

## WHAT'S BROKEN, IN ONE SENTENCE

Clicking "Завершить" (Finish) crashes the app in every mode because of a missing
`import logging`; Process Pool mode is additionally unusable because it never feeds a
`SignHandler` and is missing methods the controller calls on it; and single-thread mode
— the mode the app itself recommends for CPU — silently skips the OCR throttling
optimization that pipeline mode gets, making it the slowest possible configuration for
the use case it's supposed to be best at.

---

## PART 1 — Confirmed crash bugs (fix these first, in this order)

### 1.1 `processing/processing_controller.py::finish_and_save()` — `NameError: name 'logging' is not defined`

**Evidence:** the file's imports are only `queue`, `typing.Optional`, PyQt6's
`QObject`/`pyqtSignal`/`QThread`, `configs.config`, `VideoReaderThread`,
`DetectorThread`. There is no `import logging` anywhere. Yet `finish_and_save()`
opens with:

```python
logger = logging.getLogger(__name__)
```

and calls `logger.info(...)` / `logger.warning(...)` five more times in the same
method. The very first line executed raises `NameError`.

This method is called from `MainWindow._on_finish_requested()` — i.e. every time the
user clicks "■ Завершить", **regardless of processing_mode** (single_thread, pipeline,
and process_pool all go through this same controller method). PyQt6 has no custom
`sys.excepthook` installed anywhere in `main.py`, so an unhandled exception raised
inside a connected slot terminates the whole application, not just the click handler.

**Fix:** add `import logging` with the other imports at the top of the file. Do not
wrap the method body in `try/except` instead — that would silently swallow the
`wait()`/`stop()` calls this method exists to perform, and you'd ship a
"finish" button that appears to work but doesn't actually stop threads cleanly.

**Verify:** click "Завершить" partway through processing a short test clip in
single_thread mode (today's effective default — see 1.3) and confirm: no crash,
`roadscan.log` shows the expected `[ProcessingController]` log lines, and the app
proceeds to save results.

### 1.2 Process Pool mode is non-functional and crashes at the end of processing

**Evidence, `processing/detector_process_pool.py`:** the class `DetectorProcessPool`
defines `start()`, `stop()`, `wait()`, `_detect_optimal_workers()`,
`_start_submitter()`, `_submit_loop()` — and **no** `get_result_signs()` or
`get_turn_data()`.

But `ProcessingController` calls exactly these two methods unconditionally on whatever
object is in `self._detector_pool`:

```python
def get_result_signs(self) -> list:
    if self._detector_pool:
        return self._detector_pool.get_result_signs()   # AttributeError
    ...
def get_turn_data(self) -> list:
    if self._detector_pool:
        return self._detector_pool.get_turn_data()       # AttributeError
    ...
```

`_start_process_pool()` (the path taken when `config.PROCESSING_MODE == "process_pool"`)
assigns exactly a `DetectorProcessPool` instance to `self._detector_pool`. Both natural
completion and a manual "Завершить" click end up in `MainWindow._save_results()`, which
calls `get_result_signs()` immediately — guaranteed `AttributeError` at the end of every
process_pool run.

**There is a second, deeper problem underneath the missing methods.** Even with the
methods added, there is nothing correct for them to return:

```python
def _on_process_pool_frame(self, processed_frame):
    # ProcessPool возвращает ProcessedFrame с detections
    # Нужно обработать через SignHandler и отправить в UI
    # TODO: Интегрировать SignHandler здесь
    # Пока просто пробрасываем как есть
    self.frame_ready.emit(processed_frame)
```

This is a literal TODO stub. No `SignHandler` is ever created or driven in the
process_pool path — every detection from every worker process is thrown away after
being drawn once in the UI preview. Compare this to the (unused-but-correct!)
`processing/detector_pool.py::DetectorPool`, whose `_aggregator_loop()` correctly:
builds `DetectedSign` objects from raw detections, updates `configs.config.INDEX_OF_*`
**before** each call (see `sign_handler.py`'s dependence on these globals), and drives
one shared `SignHandler.check_the_data_to_add()` in strict frame order (guaranteed by
the reorder logic upstream). `DetectorPool.get_result_signs()`/`get_turn_data()` already
do exactly what `DetectorProcessPool` needs.

Note also: `ProcessingController._start_detector_pool()` (which wires up `DetectorPool`)
and the class attribute `USE_DETECTOR_POOL` both exist in `processing_controller.py`
but are **dead code** — `start()` never calls `_start_detector_pool()` and never checks
`USE_DETECTOR_POOL`. It only ever branches between `_start_detector()` (single_thread /
pipeline) and `_start_process_pool()` (the broken one).

**Fix, in this order:**
1. Port the aggregation pattern from `DetectorPool._aggregator_loop()` /
   `_build_detected_signs()` into `DetectorProcessPool`'s
   `ResultAggregatorThread._process_result()` (or a new method called from it) — after
   pulling a `ProcessedFrame` off the `ReorderBuffer` (already frame-ordered), rebuild
   `DetectedSign` objects from `frame_data['detections']` + `frame_data['gps_data']`,
   update `config.INDEX_OF_FRAME` / `INDEX_OF_All_FRAME` / `INDEX_OF_VIDEO` /
   `INDEX_OF_GPS` for that frame, then call one shared `SignHandler.check_the_data_to_add()`.
   The `SignHandler` instance should live on `DetectorProcessPool` (or its aggregator
   thread), created once, never in the worker processes.
2. Add `get_result_signs()` / `get_turn_data()` to `DetectorProcessPool`, delegating to
   that `SignHandler`'s `.result_signs` / `.turns`, exactly like `DetectorPool` already
   does.
3. Once this works, you can either delete the now-fully-dead `DetectorPool` /
   `_start_detector_pool()` / `USE_DETECTOR_POOL`, or leave `DetectorPool` as a
   documented reference — your call, but don't leave three different "pool" classes
   silently rotting if you can consolidate.

**Verify:** run a short test clip through process_pool mode end-to-end (after fixing
1.3/1.4 below so you can actually reach this mode) and confirm the output GeoJSON has a
non-empty `features` array with a sign count in the same ballpark as single_thread mode
on the same clip. Exact counts may differ slightly from worker-timing jitter, but not by
an order of magnitude, and never zero.

### 1.3 The Settings "Режим обработки" dropdown has zero effect on real runs

**Evidence:** `ProcessingController.start()` branches on the module-level global
`config.PROCESSING_MODE` (`configs/config.py`, hardcoded default `"single_thread"`,
never reassigned anywhere in the running app). Nothing in `MainWindow`,
`ProcessingController`, or any UI code ever copies the user's actual choice
(`AppSettings.processing_mode`, set via the Settings page combo box) into
`config.PROCESSING_MODE`. The **only** place in the whole codebase that ever writes
`config.PROCESSING_MODE` is `scripts/benchmark_end_to_end_cpu.py`.

Net effect: picking "Process Pool" in Settings does nothing when you run a normal job
from the Dashboard — the controller always takes the `single_thread` branch. ("Pipeline"
mode is a partial exception: `DetectorThread.run()` separately reads
`settings.processing_mode == "pipeline"` directly to decide whether to enable async OCR,
so pipeline behavior *does* actually activate through the single_thread controller path
— only `process_pool` is fully unreachable from the UI.)

**Fix:** at the top of `ProcessingController.start()` (or in `_reset_config()`), do:
```python
from configs.settings import get_app_settings
config.PROCESSING_MODE = get_app_settings().processing_mode
```
so the dropdown actually controls behavior. Do this only after 1.2 is fixed and
verified — don't make a broken mode reachable from the UI before it's safe.

### 1.4 The benchmark script doesn't match the current `ProcessingController` API

**Evidence, `scripts/benchmark_end_to_end_cpu.py::run_benchmark()`:**
```python
controller.processing_finished.connect(on_finished)
controller.processing_error.connect(on_error)
```
`ProcessingController` defines the signals `finished` and `error` — not
`processing_finished` / `processing_error`. These attributes don't exist, so this
raises `AttributeError` before any processing starts. This is the one tool in the repo
built specifically to measure the CPU performance question in Part 2 — fix it first so
you have working measurement before making performance claims.

Also: `config.COUNT_PROCESSED_FRAMES`, which this script reads to compute
`avg_fps = processed_frames / total_time`, is declared in `configs/config.py`, reset to
`0` by `ProcessingController._reset_config()`, and **never incremented anywhere** —
confirm this yourself with a repo-wide grep. The FPS this script prints will always be
`0` even after fixing the signal names. `DetectorThread._frames_processed` is the real
live counter (already used for `[SmartSkip]` logging and the `stats` signal) — either
increment `config.COUNT_PROCESSED_FRAMES` alongside it, or change the benchmark script
to listen to the `stats` signal instead of reading the global at the end.

**Fix:** correct the signal names, and fix the FPS metric via one of the two options
above.

---

## PART 2 — CPU performance

Several optimizations described in the historical changelogs genuinely are present in
the current code — verify this yourself, but on this snapshot: `grab()`/`retrieve()`
frame skipping in `video_reader.py`, UI-preview throttling
(`_should_emit_preview` in `detector_thread.py`), a real DCT/pHash-based CNN cache
(`core/detector.py::compute_image_hash`, not naive MD5), and CNN-skip-via-tracking
(`TrackedSign.should_skip_cnn` / `get_stable_cnn_class`, wired through
`Detector.detect_with_tracking`). Don't re-implement these — confirm they're intact and
build on top of them.

### 2.1 (Highest value — do this first) OCR throttling only helps `pipeline` mode; `single_thread` gets none of it

**Evidence:** `TrackedSign.should_run_ocr()` / `mark_ocr_requested()` (`core/sign.py`)
exist and are wired into `DetectorThread._process_loop()` — but only inside the
`if self._use_pipeline and self._sign_handler.signs:` block. In single_thread mode
(`self._use_pipeline == False`), that block never runs; instead OCR happens
unconditionally inside `Detector.detect_with_tracking(raw.image, tracked_map,
skip_ocr=False)`:
```python
text = ""
if not skip_ocr:
    with profiler.measure("ocr_read_text"):
        text = self._read_text(crop, cnn_class, yolo_class)
```
called once per detected text-bearing sign on **every processed frame**, with zero
throttling. EasyOCR is the single heaviest per-frame operation on CPU by every measure
in this repo's own profiling notes. Meanwhile `ui/widgets/settings_page.py`'s own
tooltip tells CPU users to always pick "Один поток" (single thread). So the mode the app
recommends for CPU pays full, unthrottled OCR cost on every frame a text sign is
visible in — realistically 30-40+ calls per sign given typical dwell time, versus the
~6-8 the pipeline path already achieves.

**Fix:** apply the same `tracked_sign.should_run_ocr(abs_frame_number)` /
`mark_ocr_requested(abs_frame_number)` gate to the synchronous path too. There's a
chicken-and-egg ordering issue to solve: tracking (`SignHandler.check_the_data_to_add`)
currently runs *after* detection using this frame's fresh detections. Two options:

- **Option A (simpler):** keep detection itself unthrottled (YOLO/CNN classification is
  already cheap relative to OCR and already benefits from the tracking cache and pHash
  cache), but have `_read_text()` / its caller consult the *previous* frame's
  `TrackedSign` for the matching detection (via `get_tracked_signs_map()`, the same
  lookup already used for CNN-skip) and skip the OCR call if
  `TrackedSign.should_run_ocr()` says no. New signs (no matching `TrackedSign` yet)
  still get OCR as before.
- **Option B (cleaner long-term):** restructure `_process_loop()` so single_thread mode
  also does tracking-before-OCR, exactly like the pipeline branch already does — call
  `detect_with_tracking(..., skip_ocr=True)`, run `check_the_data_to_add`, then loop
  `sign_handler.signs` and call `_read_text()` **synchronously** (instead of submitting
  to `_ocr_worker`) for any sign whose `should_run_ocr()` is true. Factor the
  "loop tracked signs → check throttle → run OCR" logic into one shared method
  parameterized by sync-vs-submit, used by both modes.

Either way, add OCR call/skip counters to the single_thread path too — right now
`_update_stats()`'s `ocr_info` string is only populated
`if self._use_pipeline and self._ocr_worker:`, so single_thread mode currently prints no
OCR statistics at all and you have no way to see whether the fix is working.

**Verify:** process the same clip with a text-bearing sign visible 30+ frames, before
and after, in single_thread mode. Confirm: (a) OCR call count for that sign drops to
roughly `OCR_MAX_CALLS_PER_SIGN` (6), (b) the final `SEM250`/`MVALUE` text in the output
GeoJSON is unchanged (same `most_common()` winner as before), (c) FPS increases.

### 2.2 CPU thread limits — real lever, real risk, do this last and carefully

`main.py` sets `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `KMP_DUPLICATE_LIB_OK=TRUE`,
`TBB_NUM_THREADS=1`, `OPENCV_NUM_THREADS=1`; `DetectorThread.run()` additionally calls
`torch.set_num_threads(1)`. These force all PyTorch inference (YOLO + CNN) onto a
single CPU thread regardless of how many cores exist. The repo's own crash-history docs
(`docs/CRASH_FIX_0xC0000409.md`) link this to a real `STATUS_STACK_BUFFER_OVERRUN`
crash from a conflict between torch's bundled OpenMP runtime and Qt/WebEngine sharing a
process — treat this part of the history as a genuine constraint, unlike most of the
rest of the changelog narrative.

1. Change only `torch.set_num_threads(N)` first, e.g.
   `N = max(1, os.cpu_count() - 1)`. Leave the environment variables untouched.
2. Run a real, ≥20-minute continuous full-video-processing stress test on an actual
   Windows CPU-only machine — not a quick smoke test. If it crashes even once with
   `0xC0000409` or anything similar, revert immediately and stop; do not "work around"
   it with try/except, that masks real memory corruption.
3. Only if step 2 is fully stable, consider `OMP_NUM_THREADS` / `MKL_NUM_THREADS`, and
   only ever inside worker **processes** once process_pool mode is fixed (1.2) — never
   raise these in the main Qt process. Processes sidestep the DLL-conflict problem in a
   way that raising thread counts in-process does not.
4. Add a settings fallback so a user who hits a crash can revert to `N=1` without a code
   change.

### 2.3 Verify whether CNN "rube" batching is actively hurting performance right now

`docs/BATCHING_FAILURE_ANALYSIS.md` documents a measured ~30% FPS *regression* from
batching CNN classification on CPU-only hardware and claims it was reverted (commit
`1c84127`, reverting `29acf57`). But the current `core/detector.py` still contains
`_classify_rube_batch()` / `_classify_fine_batch()` / `_run_cnn_batch()`, and both
`Detector.detect()` and `Detector.detect_with_tracking()` (the latter is what's
actually called from `detector_thread.py` today) call `_classify_rube_batch()`
unconditionally. Either the revert was itself later reverted without re-measuring, or
rube-only batching behaves differently from the two-stage batching that was measured —
neither the doc nor the current code should be trusted by default here. Measure it:

1. Using the fixed `scripts/benchmark_end_to_end_cpu.py` (1.4), benchmark a
   representative CPU-only clip with `_classify_rube_batch` as-is.
2. Add a temporary flag to instead call `_classify_rube` per-crop in a loop, and
   benchmark the same clip.
3. Keep whichever is measurably faster with identical detections/output, and record the
   actual numbers you got — don't just restate the old doc's conclusion or assume the
   current code is fine because it's already there.

### 2.4 Cheap, low-risk cleanups worth doing alongside the above

- `processing/video_reader.py` opens, writes, and closes `video_debug.log` with
  `open(path, "a")` **inside** the per-frame hot loop (for the first 50 frames, and
  again every 100 processed frames). Replace with one file handle (or a proper
  `logging.FileHandler`) held open for the duration of `_read_all_videos()`.
- Several hot-path `print()` calls bypass the app's actual `logging` configuration
  entirely and always flush to both stdout and `roadscan.log`
  (`core/osm_snap.py`, `core/detector.py::_print_cache_stats()`,
  `processing/detector_pool.py`, `processing/processing_controller.py`). Convert these
  to `logger.debug()`/`logger.info()`. This exact cleanup was flagged as incomplete in
  this repo's own prior audit (`WORK_SUMMARY.md` Part 5) and never finished — finish it,
  at minimum for anything inside a per-frame or per-detection loop.

### 2.5 Be honest about Process Pool's actual value on CPU-only hardware

The app's own Settings tooltip already says Process Pool is "⚠️ Медленнее на CPU из-за
overhead! Полезно только с GPU и большими батчами." After fixing correctness (1.2) and
applying 2.1's OCR fix to both paths, benchmark process_pool against single_thread on
real CPU-only hardware before promoting it. Full-resolution frame serialization across
process boundaries (`raw.image.tobytes()` per frame in
`detector_process_pool.py::_submit_loop()`) is a real IPC cost that may well make it
slower on CPU regardless of core count. If that's what you measure, say so plainly in
`STATUS.md` and the Settings tooltip rather than leaving it half-fixed and
under-documented. Fixing the crash (1.2) is required either way — a mediocre feature
should fail safely, not crash.

---

## PART 3 — Required verification methodology (don't skip this)

For every change above:
1. Fix it.
2. `python -m py_compile <file>` at minimum; better, import and instantiate the touched
   classes in a throwaway script to catch import/attribute errors before they surface in
   the GUI (this is exactly the class of bug — `NameError`, `AttributeError` — you're
   fixing; don't reintroduce a sibling of it).
3. Process the same short (2-5 min) fixed test video + GPX through the affected mode,
   end to end, from the Dashboard — once letting it run to natural completion, and once
   clicking "Завершить" partway through. Confirm no crash, expected log lines in
   `roadscan.log`, and a plausible non-empty output GeoJSON.
4. Where feasible, use `scripts/test_detector_regression.py --compare` against a
   pre-change baseline to confirm detections didn't silently change from an unrelated
   edit.
5. Only move to the next item once 3-4 pass.

---

## PART 4 — Acceptance criteria

- [ ] Clicking "■ Завершить" in single_thread mode does not crash the app.
- [ ] Clicking "■ Завершить" in pipeline mode does not crash the app.
- [ ] Running process_pool mode to natural completion, and separately clicking
      "Завершить" mid-way, does not crash, and produces a non-empty GeoJSON with a
      plausible sign count.
- [ ] Selecting "Pipeline" or "Process Pool" in Settings actually changes the behavior
      of a run started from the Dashboard.
- [ ] `scripts/benchmark_end_to_end_cpu.py` runs to completion without `AttributeError`
      and reports a non-zero, sane FPS for all three modes.
- [ ] Single_thread mode shows a measurable OCR-throttling effect (call-count drop, FPS
      increase) on a text-heavy clip, with unchanged final OCR text vs. baseline.
- [ ] Any `torch.set_num_threads()` change is backed by a documented ≥20-minute stress
      test with zero crashes, and has a revert path.
- [ ] The rube-batching keep/revert decision is backed by actual before/after numbers
      from the fixed benchmark script.
- [ ] No new `print()` calls added in per-frame/per-detection hot paths; the ones
      flagged in 2.4 are converted to `logging`.
- [ ] `STATUS.md` reflects the true, verified state of each processing_mode, including
      an honest verdict on whether process_pool is worth using on CPU-only hardware.

---

## PART 5 — Anti-patterns to avoid (this repo's own documented history of exactly these mistakes)

1. Do not write a `.md` changelog claiming something is fixed/tested without an actual
   passing test or a manual repro you personally ran.
2. Do not wrap a crash in `try/except: print(...)` and call it fixed — fix the root
   cause. `finish_and_save()`'s `NameError` must be fixed by adding the missing import,
   not by catching it and skipping the `wait()`/`stop()` calls it exists to perform.
3. Do not add a new global env var or thread-count change "just to be safe" without a
   measured, documented reason and a real stress test (2.2).
4. Do not assume a `.md` file's benchmark numbers are current, or that current code
   matches what a doc says was reverted — 2.3 is a direct example of code and
   documentation disagreeing with each other.
5. When done, update `STATUS.md` in place rather than adding another summary file.
