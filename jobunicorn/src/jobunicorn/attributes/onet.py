"""O*NET taxonomy loader (O*NET 30.1 text database, CC BY 4.0)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from jobunicorn.data.clean import normalize_title

SOC_MAJOR_GROUPS = {
    "11": "Management", "13": "Business and Financial Operations", "15": "Computer and Mathematical",
    "17": "Architecture and Engineering", "19": "Life, Physical, and Social Science", "21": "Community and Social Service",
    "23": "Legal", "25": "Educational Instruction and Library", "27": "Arts, Design, Entertainment, Sports, and Media",
    "29": "Healthcare Practitioners and Technical", "31": "Healthcare Support", "33": "Protective Service",
    "35": "Food Preparation and Serving Related", "37": "Building and Grounds Cleaning and Maintenance",
    "39": "Personal Care and Service", "41": "Sales and Related", "43": "Office and Administrative Support",
    "45": "Farming, Fishing, and Forestry", "47": "Construction and Extraction", "49": "Installation, Maintenance, and Repair",
    "51": "Production", "53": "Transportation and Material Moving", "55": "Military Specific",
}


def _read(d: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(d / name, sep="\t", dtype=str, keep_default_na=False, quoting=3)


@dataclass
class Onet:
    occupations: pd.DataFrame  # code, title, description, group, group_name, job_zone
    labels: pd.DataFrame  # code, label, label_norm, source
    tech: pd.DataFrame  # code, example, commodity_title, hot, in_demand
    related: pd.DataFrame  # code, related_code, tier


def load_onet(onet_dir: str | Path) -> Onet:
    """Load occupations (with SOC major group), title labels (title + alternate + reported), technology skills."""
    d = Path(onet_dir)
    occ = _read(d, "Occupation Data.txt").rename(columns={"O*NET-SOC Code": "code", "Title": "title", "Description": "description"})
    occ["group"] = occ["code"].str[:2]
    occ["group_name"] = occ["group"].map(SOC_MAJOR_GROUPS)
    jz = _read(d, "Job Zones.txt").rename(columns={"O*NET-SOC Code": "code", "Job Zone": "job_zone"})
    occ = occ.merge(jz[["code", "job_zone"]], on="code", how="left")
    occ["job_zone"] = pd.to_numeric(occ["job_zone"], errors="coerce")
    alt = _read(d, "Alternate Titles.txt").rename(columns={"O*NET-SOC Code": "code"})
    rep = _read(d, "Sample of Reported Titles.txt").rename(columns={"O*NET-SOC Code": "code"})
    labs = pd.concat([
        pd.DataFrame({"code": occ["code"], "label": occ["title"], "source": "title"}),
        pd.DataFrame({"code": alt["code"], "label": alt["Alternate Title"], "source": "alternate"}),
        pd.DataFrame({"code": alt.loc[alt["Short Title"] != "n/a", "code"], "label": alt.loc[alt["Short Title"] != "n/a", "Short Title"], "source": "short"}),
        pd.DataFrame({"code": rep["code"], "label": rep["Reported Job Title"], "source": "reported"}),
    ], ignore_index=True)
    labs["label_norm"] = labs["label"].map(normalize_title)
    labs = labs[labs["label_norm"] != ""].drop_duplicates(["code", "label_norm"])
    tech = _read(d, "Technology Skills.txt").rename(columns={
        "O*NET-SOC Code": "code", "Example": "example", "Commodity Title": "commodity_title",
        "Hot Technology": "hot", "In Demand": "in_demand"})[["code", "example", "commodity_title", "hot", "in_demand"]]
    rel = _read(d, "Related Occupations.txt").rename(columns={"O*NET-SOC Code": "code", "Related O*NET-SOC Code": "related_code", "Relatedness Tier": "tier"})
    return Onet(occupations=occ, labels=labs, tech=tech, related=rel[["code", "related_code", "tier"]])
