Supplementary files for "Controlled State Resynchronization for Kubernetes Edge Nodes After Network Partitions"
resync_sim.py  discrete-event simulator (API server queue, agents, Governor, baselines B1-B3, ablations A1-A4)
tune.py        three-stage tuning on seeds 1001-1005 (writes tuning.json)
main_run.py    main experiment matrix, seeds 1-30; extra_run.py adds the gamma = 0 (no aging) variant
analyze.py, extra_an.py  statistics (paired Wilcoxon, Holm, Cliff's delta, bootstrap CIs) -> analysis.json
figs.py        Figures 1-5
per_run.csv, per_node.csv  raw results
Run order: tune.py, main_run.py, extra_run.py, analyze.py, extra_an.py, figs.py. Requires numpy, scipy, matplotlib.
All numbers come from simulation with assumed request costs; they are not Kubernetes measurements.
