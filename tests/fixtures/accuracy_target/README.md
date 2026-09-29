# Accuracy target

A deliberately small repository, used two ways: as the target the accuracy
harness traces in its own test, and as the hand-labeled sample for the region
a trace cannot reach. The files are plain Python with no dependencies, so the
harness can run its suite with nothing installed.

The expected trace, checked by hand against `calculator/report.py`:

| Caller | Callee | Inferred? |
| :--- | :--- | :--- |
| `calculator.report:total` | `calculator.ops:add` | yes |
| `calculator.report:label` | `calculator.report:total` | yes |
| `calculator.report:indirect` | `calculator.ops:add` | no, reached through a variable |
| `tests.test_report:ReportTest.test_total` | `calculator.report:total` | yes |
| `tests.test_report:ReportTest.test_label` | `calculator.report:label` | yes |
| `tests.test_report:ReportTest.test_indirect` | `calculator.report:indirect` | yes |

Five of the six match, and the sixth is the limit of static inference rather
than a defect in the measurement. `calculator.report:unused` calls `add` but is
never called, so it is an inferred edge the trace never sees, and
`calculator.ops:multiply` has no call edges at all.
