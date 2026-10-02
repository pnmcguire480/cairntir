# Proposed resource method amendment, awaiting pre-run agreement

This supersedes the measurement proposal in the earlier resource-budget draft;
the original frozen file remains unchanged. No benchmark was run. No thresholds
are accepted merely because this proposal is written.

Use matched stable 1.12.3 and candidate artifacts on each same machine, isolated
synthetic stores and identical dependency/model/cache/backup/update conditions.
Freeze artifact hashes, database and WAL sizes, history/task shape, repetitions,
sampling and thermal stop conditions before measurements. Record **every sample,
median and maximum**. Do not claim p95 confidence from five cold starts.

Suggested repetitions remain five paired cold starts and twenty paired warm
operations, alternating stable/candidate order. Proposed regression limits apply
separately to median and maximum (not an inferred percentile): startup baseline
+max(10%,50ms); save/get/resume +max(10%,20ms); semantic recall +max(10%,100ms).
Absolute usability ceilings still require pre-run agreement; an unacceptable
baseline does not become acceptable through a relative comparison.

Include `status` and `doctor` explicitly: elapsed wall time from command launch
through process/helper exit; snapshot/copy duration when present; maximum aggregate
working-set memory of parent plus every owned child at each sample; temporary
disk peak; and cleanup after both success and ordinary failure. Initial proposed
diagnostic elapsed allowance is baseline +max(10%,100ms), aggregate peak memory
baseline +max(10%,32MiB). These are review candidates, not measured tolerances.
Do not exclude the snapshot helper from CPU, memory or time accounting.

Record temporary disk as bytes alongside source database/WAL bytes. A proposed
scratch-space ceiling is twice database-plus-WAL bytes plus 8MiB, with zero owned
snapshot files remaining after normal exit or a handled failure. If OS cleanup
fails, report failure and retained paths rather than silently passing. Forced
termination cleanup is a separate unqualified scenario, not promised by normal
exception cleanup or a reason to add a service.

For idle behavior record cumulative CPU **seconds**, summed over parent and all
owned children (including short-lived processes), alongside elapsed seconds and
sampled working set. The proposed CPU allowance is baseline cumulative seconds
+0.001 times elapsed seconds (0.12 CPU-seconds over a two-minute interval).
This corresponds to 0.1 percentage point of one logical CPU; do not normalize by
total machine cores or ignore child work. Proposed idle memory allowance remains
baseline +max(5%,10MiB), and also report the aggregate maximum. Two-host cases
compare against the matched two-host baseline.

Fresh thermal conditions and a numeric stop rule must be agreed before repeated
measurements. Current restrictions still prohibit these benchmarks. The reported
93C peak does not establish its cause. No fan, power or persistent settings change
is authorized by this proposed method.
