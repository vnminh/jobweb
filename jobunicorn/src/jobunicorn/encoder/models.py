"""Inductive encoders (DESIGN 6): heterogeneous R-GCN-style GNN and a two-tower baseline.

No ID embeddings for users/jobs (they never repeat across windows); attribute nodes get text + learned ID embedding.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

ATTR_TYPES_WITH_ID = ["occupation", "occ_group", "skill", "city", "state", "seniority", "job_type", "degree", "major"]


class InputProjector(nn.Module):
    """Per-node-type input layer: Linear(text) [+ MLP(numeric) for users] [+ ID embedding for attribute types]."""

    def __init__(self, in_dims: dict[str, int], n_nodes: dict[str, int], hidden: int, user_num_dim: int, dropout: float = 0.1,
                 job_num_dim: int = 0):
        super().__init__()
        self.proj = nn.ModuleDict({t: nn.Linear(d, hidden) for t, d in in_dims.items()})
        self.user_num = nn.Sequential(nn.Linear(user_num_dim, hidden), nn.ReLU(), nn.Linear(hidden, hidden)) if user_num_dim else None
        self.job_num = nn.Sequential(nn.Linear(job_num_dim, hidden), nn.ReLU(), nn.Linear(hidden, hidden)) if job_num_dim else None
        self.id_emb = nn.ModuleDict({t: nn.Embedding(n_nodes[t], hidden) for t in ATTR_TYPES_WITH_ID if t in n_nodes})
        for e in self.id_emb.values():
            nn.init.normal_(e.weight, std=0.02)
        self.drop = nn.Dropout(dropout)

    def forward(self, x_text: dict[str, torch.Tensor], user_num: torch.Tensor | None, node_ids: dict[str, torch.Tensor],
                job_num: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        h = {}
        for t, x in x_text.items():
            z = self.proj[t](x)
            if t == "user" and self.user_num is not None and user_num is not None:
                z = z + self.user_num(user_num)
            if t == "job" and self.job_num is not None and job_num is not None:
                z = z + self.job_num(job_num)
            if t in self.id_emb:
                z = z + self.id_emb[t](node_ids[t])
            h[t] = self.drop(F.relu(z))
        return h


class HeteroGNN(nn.Module):
    """2-layer relational GNN: per-relation GraphConv (separate weights per edge type = R-GCN), mean aggregation with
    edge weights, sum over relations, residual connection, final linear head to `out` dims."""

    def __init__(self, metadata, in_dims, n_nodes, hidden: int = 64, out: int = 64, layers: int = 2, user_num_dim: int = 0,
                 dropout: float = 0.1, job_num_dim: int = 0):
        super().__init__()
        from torch_geometric.nn import GraphConv, HeteroConv

        self.inp = InputProjector(in_dims, n_nodes, hidden, user_num_dim, dropout, job_num_dim)
        self.convs = nn.ModuleList()
        for _ in range(layers):
            self.convs.append(HeteroConv({et: GraphConv((hidden, hidden), hidden, aggr="mean") for et in metadata[1]}, aggr="sum"))
        self.norms = nn.ModuleList([nn.ModuleDict({t: nn.LayerNorm(hidden) for t in metadata[0]}) for _ in range(layers)])
        self.head = nn.ModuleDict({t: nn.Linear(hidden, out) for t in metadata[0]})
        self.drop = nn.Dropout(dropout)

    def forward(self, x_text, user_num, node_ids, edge_index_dict, edge_weight_dict, job_num=None) -> dict[str, torch.Tensor]:
        h = self.inp(x_text, user_num, node_ids, job_num)
        for conv, norm in zip(self.convs, self.norms):
            m = conv(h, edge_index_dict, edge_weight_dict=edge_weight_dict)
            h = {t: self.drop(F.relu(norm[t](h[t] + m[t]))) if t in m else h[t] for t in h}
        return {t: self.head[t](z) for t, z in h.items()}


class TwoTower(nn.Module):
    """No-GNN baseline: user tower on [profile title emb, mean emb of history-applied jobs, numeric, state emb];
    job tower on [text emb, popularity, state emb]. Same information as the GNN except graph propagation."""

    def __init__(self, text_dim: int, user_num_dim: int, hidden: int = 128, out: int = 64, dropout: float = 0.1,
                 n_states: int = 1, state_dim: int = 16, job_num_dim: int = 1):
        super().__init__()
        self.state = nn.Embedding(n_states + 1, state_dim)  # index 0 = unknown
        self.user = nn.Sequential(nn.Linear(2 * text_dim + user_num_dim + state_dim, hidden), nn.ReLU(), nn.Dropout(dropout), nn.Linear(hidden, out))
        self.job = nn.Sequential(nn.Linear(text_dim + job_num_dim + state_dim, hidden), nn.ReLU(), nn.Dropout(dropout), nn.Linear(hidden, out))

    def forward_user(self, prof, hist, num, state) -> torch.Tensor:
        return self.user(torch.cat([prof, hist, num, self.state(state + 1)], dim=-1))

    def forward_job(self, x, num, state) -> torch.Tensor:
        return self.job(torch.cat([x, num, self.state(state + 1)], dim=-1))


def bpr_loss(pos: torch.Tensor, neg: torch.Tensor) -> torch.Tensor:
    """-log sigmoid(pos - neg), averaged. neg may have an extra trailing dim of negatives per positive."""
    if neg.dim() == pos.dim() + 1:
        pos = pos.unsqueeze(-1)
    return -F.logsigmoid(pos - neg).mean()
