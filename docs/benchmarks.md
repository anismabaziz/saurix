# Benchmark Results

Cold run = first run after cache clear. Warm run = immediate second run on same repo.

| Repo | Lang | Full Index (s) | Incremental Re-index (s) | Speedup | Cache Hits | Reindexed Files |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `pallets/flask` | python | 0.20 | 0.09 | 2.27x | 83 | 0 |
| `axios/axios` | typescript | 0.09 | 0.05 | 1.87x | 280 | 0 |
| `google/gson` | java | 0.75 | 0.31 | 2.45x | 259 | 0 |