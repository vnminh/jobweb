"""Pack GraphTables into a PyTorch Geometric HeteroData and extract per-window subgraphs."""

from __future__ import annotations

import numpy as np
import torch

from jobunicorn.graph.build import RELATIONS, GraphTables


def to_heterodata(g: GraphTables, add_reverse: bool = True):
    """HeteroData with num_nodes per type, `window` tensors for user/job, edge_index + edge_weight per relation.
    Reverse relations are named 'rev_<rel>' (needed for message passing towards users/jobs)."""
    from torch_geometric.data import HeteroData

    data = HeteroData()
    for t, df in g.nodes.items():
        data[t].num_nodes = len(df)
        if "window" in df.columns:
            data[t].window = torch.as_tensor(df["window"].to_numpy(np.int64).copy())
    for rel, df in g.edges.items():
        s, d = RELATIONS[rel]
        ei = torch.as_tensor(np.vstack([df["src"].to_numpy(np.int64), df["dst"].to_numpy(np.int64)]))
        w = torch.as_tensor(df["weight"].to_numpy(np.float32))
        data[s, rel, d].edge_index = ei
        data[s, rel, d].edge_weight = w
        if add_reverse and s != d:
            data[d, f"rev_{rel}", s].edge_index = ei.flip(0)
            data[d, f"rev_{rel}", s].edge_weight = w
    return data


def window_subgraph(data, window: int):
    """Subgraph with the users/jobs of one window and all shared (attribute) nodes; node ids are re-indexed."""
    subset = {}
    for t in data.node_types:
        if "window" in data[t]:
            subset[t] = (data[t].window == window).nonzero().view(-1)
        else:
            subset[t] = torch.arange(data[t].num_nodes)
    return data.subgraph(subset)
