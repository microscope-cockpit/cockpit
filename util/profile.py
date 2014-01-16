
import pstats
import sys

stats = pstats.Stats(sys.argv[1])
stats.strip_dirs()
stats.sort_stats('time').print_stats(20)
stats.print_callees(20)
stats.sort_stats('cumulative').print_stats(20)
stats.print_callees(20)
