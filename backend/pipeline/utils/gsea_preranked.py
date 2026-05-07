"""
Preranked GSEA utilities for VizR.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable

from backend.utils.logger import setup_module_logger


MIN_OVERLAP = 5
MAX_GENE_SET_SIZE = 500
DEFAULT_PERMUTATIONS = 25
DEFAULT_WEIGHT = 1.0

logger = setup_module_logger(__name__, 'INFO')


class GSEAValidationError(ValueError):
    """Raised when preranked GSEA inputs are invalid."""


@dataclass
class RankedEntry:
    gene_id: str
    score: float


def parse_ranked_gene_list(ranked_list_text: str) -> list[RankedEntry]:
    lines = [line.strip() for line in ranked_list_text.splitlines() if line.strip()]
    if not lines:
        raise GSEAValidationError("Ranked gene list is empty")

    entries: list[RankedEntry] = []
    seen_genes: set[str] = set()
    seen_scores: set[float] = set()

    for index, line in enumerate(lines, start=1):
        parts = line.split("\t")
        if len(parts) != 2:
            raise GSEAValidationError(
                f"Ranked gene list line {index} must contain exactly 2 tab-delimited columns"
            )

        gene_id = parts[0].strip()
        score_text = parts[1].strip()

        if not gene_id:
            raise GSEAValidationError(f"Ranked gene list line {index} has an empty gene ID")
        if gene_id in seen_genes:
            raise GSEAValidationError(f"Duplicate gene ID found in ranked list: {gene_id}")

        try:
            score = float(score_text)
        except ValueError as exc:
            raise GSEAValidationError(
                f"Ranked gene list line {index} contains a non-numeric ranking value"
            ) from exc

        if not math.isfinite(score):
            raise GSEAValidationError(
                f"Ranked gene list line {index} contains a non-finite ranking value"
            )
        if score in seen_scores:
            raise GSEAValidationError(
                "Duplicate ranking values are not allowed for preranked GSEA"
            )

        seen_genes.add(gene_id)
        seen_scores.add(score)
        entries.append(RankedEntry(gene_id=gene_id, score=score))

    entries.sort(key=lambda item: item.score, reverse=True)
    return entries


def parse_gmt_text(gmt_text: str) -> dict[str, dict[str, object]]:
    gene_sets: dict[str, dict[str, object]] = {}

    for line_number, raw_line in enumerate(gmt_text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 3:
            raise GSEAValidationError(
                f"GMT line {line_number} must contain at least 3 tab-delimited columns"
            )

        gene_set_name = parts[0].strip()
        description = parts[1].strip()
        genes = [gene.strip() for gene in parts[2:] if gene.strip()]

        if not gene_set_name:
            raise GSEAValidationError(f"GMT line {line_number} has an empty gene set name")
        if gene_set_name in gene_sets:
            raise GSEAValidationError(f"Duplicate gene set name found in GMT: {gene_set_name}")
        if not genes:
            continue

        deduped_genes = list(dict.fromkeys(genes))
        gene_sets[gene_set_name] = {
            "description": description,
            "genes": deduped_genes,
        }

    if not gene_sets:
        raise GSEAValidationError("No valid gene sets were found in the GMT file")

    return gene_sets


def parse_gmt_file(gmt_path: str) -> dict[str, dict[str, object]]:
    with open(gmt_path, "r", encoding="utf-8") as handle:
        return parse_gmt_text(handle.read())


def _compute_enrichment_core(
    ranked_entries: list[RankedEntry],
    gene_set: set[str],
    gene_ids: list[str] | None = None,
    scores: list[float] | None = None,
    weighted_scores: list[float] | None = None,
    weight: float = 1.0,
) -> dict[str, object]:
    genes = gene_ids or [entry.gene_id for entry in ranked_entries]
    scores = scores or [entry.score for entry in ranked_entries]
    hits = [gene in gene_set for gene in genes]
    hit_count = sum(hits)
    total_gene_count = len(ranked_entries)
    miss_count = total_gene_count - hit_count

    if hit_count == 0 or miss_count == 0:
        raise GSEAValidationError("Gene set overlap is not suitable for enrichment calculation")

    if weighted_scores is None:
        weighted_scores = [abs(score) ** weight for score in scores]
    hit_weights = [score if is_hit else 0.0 for score, is_hit in zip(weighted_scores, hits)]
    norm_hit = sum(hit_weights)
    miss_penalty = 1.0 / miss_count

    running_score = 0.0
    running_scores: list[float] = []
    max_es = -float("inf")
    min_es = float("inf")
    max_index = 0
    min_index = 0

    for idx, is_hit in enumerate(hits):
        if is_hit:
            running_score += hit_weights[idx] / norm_hit
        else:
            running_score -= miss_penalty

        running_scores.append(running_score)
        if running_score > max_es:
            max_es = running_score
            max_index = idx
        if running_score < min_es:
            min_es = running_score
            min_index = idx

    if abs(max_es) >= abs(min_es):
        es = max_es
        peak_index = max_index
        leading_edge_genes = [
            ranked_entries[idx].gene_id
            for idx in range(peak_index + 1)
            if hits[idx]
        ]
    else:
        es = min_es
        peak_index = min_index
        leading_edge_genes = [
            ranked_entries[idx].gene_id
            for idx in range(peak_index, total_gene_count)
            if hits[idx]
        ]

    hit_genes = [entry.gene_id for entry, is_hit in zip(ranked_entries, hits) if is_hit]
    hit_indices = [idx for idx, is_hit in enumerate(hits) if is_hit]
    hit_scores = [entry.score for entry, is_hit in zip(ranked_entries, hits) if is_hit]

    return {
        "es": es,
        "peak_index": peak_index,
        "running_scores": running_scores,
        "hit_genes": hit_genes,
        "hit_indices": hit_indices,
        "hit_scores": hit_scores,
        "leading_edge_genes": leading_edge_genes,
    }


def _compute_enrichment_score_only(
    total_gene_count: int,
    hit_indices: set[int],
    weighted_scores: list[float],
) -> float:
    hit_count = len(hit_indices)
    miss_count = total_gene_count - hit_count

    if hit_count == 0 or miss_count == 0:
        raise GSEAValidationError("Gene set overlap is not suitable for enrichment calculation")

    norm_hit = sum(weighted_scores[idx] for idx in hit_indices)
    miss_penalty = 1.0 / miss_count

    running_score = 0.0
    max_es = -float("inf")
    min_es = float("inf")

    for idx in range(total_gene_count):
        if idx in hit_indices:
            running_score += weighted_scores[idx] / norm_hit
        else:
            running_score -= miss_penalty

        if running_score > max_es:
            max_es = running_score
        if running_score < min_es:
            min_es = running_score

    return max_es if abs(max_es) >= abs(min_es) else min_es


def _sample_random_hit_indices(total_gene_count: int, gene_set_size: int, rng: random.Random) -> set[int]:
    return set(rng.sample(range(total_gene_count), gene_set_size))


def _bh_fdr(pvalues: list[float]) -> list[float]:
    if not pvalues:
        return []

    indexed = sorted(enumerate(pvalues), key=lambda item: item[1])
    adjusted = [1.0] * len(pvalues)
    prev = 1.0
    total = len(pvalues)

    for rank, (original_index, pvalue) in enumerate(reversed(indexed), start=1):
        adjusted_value = min(prev, (pvalue * total) / (total - rank + 1))
        adjusted[original_index] = min(adjusted_value, 1.0)
        prev = adjusted_value

    return adjusted


def summarize_gsea_rows(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "gene_set": row["gene_set"],
            "gene_set_id": row.get("gene_set_id", ""),
            "description": row["description"],
            "gene_set_size": row["gene_set_size"],
            "overlap_size": row["overlap_size"],
            "es": row["es"],
            "nes": row["nes"],
            "p_value": row["p_value"],
            "fdr": row["fdr"],
            "leading_edge_size": row["leading_edge_size"],
        }
        for row in rows
    ]


def compute_single_gene_set_detail(
    ranked_entries: list[RankedEntry],
    gene_set_name: str,
    gene_set_info: dict[str, object],
    min_overlap: int = MIN_OVERLAP,
    max_gene_set_size: int = MAX_GENE_SET_SIZE,
) -> dict[str, object]:
    ranked_gene_ids = {entry.gene_id for entry in ranked_entries}
    gene_ids = [entry.gene_id for entry in ranked_entries]
    scores = [entry.score for entry in ranked_entries]
    weighted_scores = [abs(score) for score in scores]

    genes = set(gene_set_info["genes"])
    overlap_genes = genes & ranked_gene_ids
    overlap_size = len(overlap_genes)
    logger.info(
        "[GSEA-ALGO] Single gene set detail parameters: "
        f"gene_set='{gene_set_name}', gene_set_id='{gene_set_info.get('id', '')}', "
        f"ranked_gene_count={len(ranked_entries)}, gene_set_size={len(genes)}, "
        f"overlap_size={overlap_size}, min_overlap={min_overlap}, "
        f"max_gene_set_size={max_gene_set_size}, weight={DEFAULT_WEIGHT}"
    )
    if overlap_size < min_overlap or overlap_size > max_gene_set_size:
        raise GSEAValidationError(
            f"Gene set '{gene_set_name}' does not pass overlap filters for detail rendering"
        )

    enrichment = _compute_enrichment_core(
        ranked_entries,
        overlap_genes,
        gene_ids=gene_ids,
        scores=scores,
        weighted_scores=weighted_scores,
    )

    return {
        "gene_set": gene_set_name,
        "gene_set_id": gene_set_info.get("id", ""),
        "description": gene_set_info["description"],
        "gene_set_size": len(genes),
        "overlap_size": overlap_size,
        "es": float(enrichment["es"]),
        "leading_edge_genes": enrichment["leading_edge_genes"],
        "leading_edge_size": len(enrichment["leading_edge_genes"]),
        "hit_genes": enrichment["hit_genes"],
        "hit_indices": enrichment["hit_indices"],
        "hit_scores": enrichment["hit_scores"],
        "running_scores": enrichment["running_scores"],
        "peak_index": enrichment["peak_index"],
    }


def run_preranked_gsea(
    ranked_entries: list[RankedEntry],
    gene_sets: dict[str, dict[str, object]],
    min_overlap: int = MIN_OVERLAP,
    max_gene_set_size: int = MAX_GENE_SET_SIZE,
    permutations: int = DEFAULT_PERMUTATIONS,
) -> dict[str, object]:
    ranked_gene_ids = {entry.gene_id for entry in ranked_entries}
    gene_ids = [entry.gene_id for entry in ranked_entries]
    scores = [entry.score for entry in ranked_entries]
    weighted_scores = [abs(score) for score in scores]
    total_gene_count = len(ranked_entries)
    rng = random.Random(42)
    rows: list[dict[str, object]] = []
    total_gene_set_count = len(gene_sets)
    skipped_below_min_overlap = 0
    skipped_above_max_gene_set_size = 0
    tested_overlap_sizes: list[int] = []

    logger.info(
        "[GSEA-ALGO] Starting preranked GSEA: "
        f"ranked_gene_count={total_gene_count}, total_gene_sets={total_gene_set_count}, "
        f"min_overlap={min_overlap}, max_gene_set_size={max_gene_set_size}, "
        f"permutations={permutations}, weight={DEFAULT_WEIGHT}, rng_seed=42"
    )

    for gene_set_name, gene_set_info in gene_sets.items():
        genes = set(gene_set_info["genes"])
        overlap_genes = genes & ranked_gene_ids
        overlap_size = len(overlap_genes)
        if overlap_size < min_overlap:
            skipped_below_min_overlap += 1
            continue
        if overlap_size > max_gene_set_size:
            skipped_above_max_gene_set_size += 1
            continue
        tested_overlap_sizes.append(overlap_size)

        enrichment = _compute_enrichment_core(
            ranked_entries,
            overlap_genes,
            gene_ids=gene_ids,
            scores=scores,
            weighted_scores=weighted_scores,
        )
        observed_es = float(enrichment["es"])
        observed_hit_indices = set(int(index) for index in enrichment["hit_indices"])

        null_scores: list[float] = []
        for _ in range(permutations):
            random_hit_indices = _sample_random_hit_indices(total_gene_count, overlap_size, rng)
            if random_hit_indices == observed_hit_indices:
                null_scores.append(observed_es)
                continue
            null_scores.append(
                _compute_enrichment_score_only(
                    total_gene_count,
                    random_hit_indices,
                    weighted_scores,
                )
            )

        if observed_es >= 0:
            positive_null = [score for score in null_scores if score >= 0]
            denom = sum(positive_null) / len(positive_null) if positive_null else 1.0
            p_value = (
                sum(1 for score in positive_null if score >= observed_es) / len(positive_null)
                if positive_null else 1.0
            )
        else:
            negative_null = [score for score in null_scores if score < 0]
            denom = (sum(abs(score) for score in negative_null) / len(negative_null)) if negative_null else 1.0
            p_value = (
                sum(1 for score in negative_null if score <= observed_es) / len(negative_null)
                if negative_null else 1.0
            )

        denom = denom if denom else 1.0
        nes = observed_es / denom

        rows.append({
            "gene_set": gene_set_name,
            "gene_set_id": gene_set_info.get("id", ""),
            "description": gene_set_info["description"],
            "gene_set_size": len(genes),
            "overlap_size": overlap_size,
            "es": observed_es,
            "nes": nes,
            "p_value": p_value,
            "leading_edge_genes": enrichment["leading_edge_genes"],
            "leading_edge_size": len(enrichment["leading_edge_genes"]),
            "hit_genes": enrichment["hit_genes"],
            "hit_indices": enrichment["hit_indices"],
            "hit_scores": enrichment["hit_scores"],
            "running_scores": enrichment["running_scores"],
            "peak_index": enrichment["peak_index"],
        })

    if not rows:
        logger.warning(
            "[GSEA-ALGO] No gene sets passed filters: "
            f"ranked_gene_count={total_gene_count}, total_gene_sets={total_gene_set_count}, "
            f"min_overlap={min_overlap}, max_gene_set_size={max_gene_set_size}, "
            f"skipped_below_min_overlap={skipped_below_min_overlap}, "
            f"skipped_above_max_gene_set_size={skipped_above_max_gene_set_size}, "
            f"permutations={permutations}, weight={DEFAULT_WEIGHT}"
        )
        raise GSEAValidationError(
            f"No gene sets passed the minimum overlap threshold ({min_overlap})"
        )

    fdr_values = _bh_fdr([float(row["p_value"]) for row in rows])
    for row, fdr in zip(rows, fdr_values):
        row["fdr"] = fdr

    rows.sort(key=lambda row: (row["fdr"], -abs(float(row["nes"])), row["gene_set"]))

    min_tested_overlap = min(tested_overlap_sizes) if tested_overlap_sizes else 0
    max_tested_overlap = max(tested_overlap_sizes) if tested_overlap_sizes else 0
    avg_tested_overlap = (
        sum(tested_overlap_sizes) / len(tested_overlap_sizes)
        if tested_overlap_sizes else 0.0
    )
    logger.info(
        "[GSEA-ALGO] Completed preranked GSEA: "
        f"ranked_gene_count={total_gene_count}, total_gene_sets={total_gene_set_count}, "
        f"tested_gene_sets={len(rows)}, skipped_below_min_overlap={skipped_below_min_overlap}, "
        f"skipped_above_max_gene_set_size={skipped_above_max_gene_set_size}, "
        f"min_overlap={min_overlap}, max_gene_set_size={max_gene_set_size}, "
        f"permutations={permutations}, weight={DEFAULT_WEIGHT}, "
        f"min_tested_overlap={min_tested_overlap}, max_tested_overlap={max_tested_overlap}, "
        f"avg_tested_overlap={avg_tested_overlap:.2f}"
    )

    return {
        "tested_gene_sets": len(rows),
        "ranked_gene_count": len(ranked_entries),
        "rows": rows,
        "min_overlap": min_overlap,
        "max_gene_set_size": max_gene_set_size,
        "permutations": permutations,
    }
