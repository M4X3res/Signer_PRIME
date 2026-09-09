# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')

from processing.detector_process_pool import ReorderBuffer

print("=== Test: gap safety valve ===")
buf = ReorderBuffer(max_gap=5)
released_total = []

for seq in range(1, 10):
    print(f"\nAdding seq={seq}")
    result = buf.add({"seq": seq, "frame_idx": seq * 5})
    released_total.extend(result)
    print(f"  Returned: {len(result)} frames")
    print(f"  Total released so far: {len(released_total)}")
    print(f"  Buffer size: {len(buf)}")
    print(f"  Buffer._next_expected: {buf._next_expected}")

print(f"\n=== Final: released={len(released_total)}, buffered={len(buf)} ===")
print(f"Released seqs: {[f['seq'] for f in released_total]}")
