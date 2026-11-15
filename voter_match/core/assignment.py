"""Sparse Optimal 1-to-1 Assignment.

The candidate graph produced by blocking is extremely sparse: each List-B voter
has only a few dozen plausible List-A candidates. Building a dense (n_b x n_a)
cost matrix and running the Hungarian algorithm on it costs O(n^3) time and
O(n^2) memory (~100 MB at 5,000 x 5,000).

Instead we split the bipartite candidate graph into connected components
(union-find) and solve a small dense assignment per component. Because no
edge crosses component boundaries, the union of the per-component optima is
exactly the global optimum, so results are identical to the dense solve.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment

# Cost for a non-edge inside a component's dense sub-matrix. Must exceed any
# real edge cost (max 1.0 - min_score) so the solver only picks real edges
# whenever possible, mirroring the original dense solver's 2.0 filler.
_NON_EDGE_COST = 2.0


class _UnionFind:
    __slots__ = ("parent",)

    def __init__(self) -> None:
        self.parent: dict[object, object] = {}

    def find(self, x: object) -> object:
        parent = self.parent
        if x not in parent:
            parent[x] = x
            return x
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    def union(self, a: object, b: object) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def solve_sparse_assignment(
    edges: Iterable[tuple[int, int, float]],
    min_score: float = 0.55,
) -> dict[int, int]:
    """Globally optimal 1-to-1 assignment over a sparse scored edge list.

    Args:
        edges: iterable of (b_idx, a_idx, score).
        min_score: edges scoring below this are ignored entirely.

    Returns:
        dict mapping b_idx -> a_idx for every assigned pair.
    """
    uf = _UnionFind()
    edge_list: list[tuple[int, int, float]] = []
    for b, a, s in edges:
        if s < min_score:
            continue
        edge_list.append((b, a, s))
        uf.union(("b", b), ("a", a))

    if not edge_list:
        return {}

    components: dict[object, list[tuple[int, int, float]]] = defaultdict(list)
    for b, a, s in edge_list:
        components[uf.find(("b", b))].append((b, a, s))

    max_cost = 1.0 - min_score
    assigned: dict[int, int] = {}

    for comp_edges in components.values():
        if len(comp_edges) == 1:
            b, a, _ = comp_edges[0]
            assigned[b] = a
            continue

        b_ids = sorted({e[0] for e in comp_edges})
        a_ids = sorted({e[1] for e in comp_edges})
        b_pos = {b: i for i, b in enumerate(b_ids)}
        a_pos = {a: j for j, a in enumerate(a_ids)}

        cost = np.full((len(b_ids), len(a_ids)), _NON_EDGE_COST, dtype=np.float64)
        for b, a, s in comp_edges:
            cost[b_pos[b], a_pos[a]] = 1.0 - s

        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols):
            if cost[r, c] <= max_cost + 1e-9:
                assigned[b_ids[r]] = a_ids[c]

    return assigned
