"""
Utilities for storing and loading precomputed GSEA results.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from backend.pipeline.utils.gsea_preranked import GSEAValidationError, summarize_gsea_rows
from backend.utils.logger import setup_module_logger


logger = setup_module_logger(__name__, "INFO")


def normalize_deg_tool_name(tool_name: str | None) -> str:
    normalized = (tool_name or "edgeR").strip()
    lowered = normalized.lower()
    if lowered == "edger":
        return "edgeR"
    if lowered == "deseq2":
        return "DESeq2"
    return normalized


def resolve_deg_result_file_from_schema(
    workbench_schema: dict[str, Any],
    comparison_name: str,
    deg_tool: str,
) -> tuple[str, str]:
    canonical_tool = normalize_deg_tool_name(deg_tool)
    candidate_tools: list[str] = []
    for candidate in (canonical_tool, deg_tool, "edgeR", "DESeq2"):
        if candidate and candidate not in candidate_tools:
            candidate_tools.append(candidate)

    for candidate_tool in candidate_tools:
        result_filename = f"genes.counts.matrix.{comparison_name}.{candidate_tool}.DE_results"
        result_path = os.path.join(workbench_schema["deg"], candidate_tool, result_filename)
        if os.path.exists(result_path):
            return result_path, candidate_tool

    raise FileNotFoundError(f"DEG result file not found for {comparison_name} ({canonical_tool})")


def discover_deg_result_files(
    workbench_schema: dict[str, Any],
    preferred_tool: str | None = None,
) -> list[dict[str, str]]:
    tool_candidates = [normalize_deg_tool_name(preferred_tool)] if preferred_tool else []
    for fallback_tool in ("edgeR", "DESeq2"):
        if fallback_tool not in tool_candidates:
            tool_candidates.append(fallback_tool)

    discovered: dict[tuple[str, str], dict[str, str]] = {}
    for tool_name in tool_candidates:
        tool_dir = Path(workbench_schema["deg"]) / tool_name
        if not tool_dir.exists():
            continue
        for result_path in sorted(tool_dir.glob("genes.counts.matrix.*.*.DE_results")):
            parts = result_path.name.split(".")
            if len(parts) < 6:
                continue
            comparison_name = ".".join(parts[3:-2])
            discovered[(comparison_name, tool_name)] = {
                "comparison_name": comparison_name,
                "deg_tool": tool_name,
                "result_path": str(result_path),
            }

    return list(discovered.values())


def build_preranked_text_from_deg_result(result_path: str) -> tuple[str, int, str]:
    df = pd.read_csv(result_path, sep="\t", index_col=0)
    if df.empty:
        raise GSEAValidationError("DEG result file is empty")

    rank_key = None
    for candidate in ("logFC", "log2FoldChange", "stat"):
        if candidate in df.columns:
            rank_key = candidate
            break

    if not rank_key:
        raise GSEAValidationError("DEG result file does not contain a supported ranking column")

    lines: list[str] = []
    epsilon = 1e-9
    for index, (gene_id, row) in enumerate(df.iterrows()):
        gene_text = str(gene_id).strip()
        if not gene_text or gene_text.lower() == "nan":
            continue

        rank_value_raw = row.get(rank_key)
        if pd.isna(rank_value_raw):
            continue

        try:
            rank_value = float(rank_value_raw)
        except (TypeError, ValueError):
            continue

        adjusted_rank = rank_value - (index * epsilon)
        lines.append(f"{gene_text}\t{adjusted_rank:.12f}")

    if not lines:
        raise GSEAValidationError("No ranked genes could be extracted from the DEG result file")

    return "\n".join(lines), len(lines), rank_key


def extract_ranking_profile_from_deg_result(result_path: str) -> tuple[list[dict[str, float]], int | None, str]:
    df = pd.read_csv(result_path, sep="\t", index_col=0)
    if df.empty:
        raise GSEAValidationError("DEG result file is empty")

    rank_key = None
    for candidate in ("logFC", "log2FoldChange", "stat"):
        if candidate in df.columns:
            rank_key = candidate
            break

    if not rank_key:
        raise GSEAValidationError("DEG result file does not contain a supported ranking column")

    cleaned = df[[rank_key]].rename(columns={rank_key: "value"}).dropna(subset=["value"]).copy()
    cleaned["value"] = pd.to_numeric(cleaned["value"], errors="coerce")
    cleaned = cleaned.dropna(subset=["value"])

    if cleaned.empty:
        raise GSEAValidationError("DEG result file does not contain usable ranking values")

    ranking_profile = [
        {"index": int(idx + 1), "value": float(value)}
        for idx, value in enumerate(cleaned["value"].tolist())
    ]
    zero_cross_index = next(
        (int(idx + 1) for idx, value in enumerate(cleaned["value"].tolist()) if value <= 0),
        None,
    )
    return ranking_profile, zero_cross_index, rank_key


def get_gsea_output_dir(
    workbench_schema: dict[str, Any],
    deg_tool: str,
    comparison_name: str,
    gene_set_db: str,
) -> str:
    normalized_tool = normalize_deg_tool_name(deg_tool)
    return os.path.join(workbench_schema["deg"], normalized_tool, "gsea", comparison_name, gene_set_db)


def get_gsea_result_paths(
    workbench_schema: dict[str, Any],
    deg_tool: str,
    comparison_name: str,
    gene_set_db: str,
) -> dict[str, str]:
    output_dir = get_gsea_output_dir(workbench_schema, deg_tool, comparison_name, gene_set_db)
    return {
        "dir": output_dir,
        "result_json": os.path.join(output_dir, "result.json"),
        "comparison_detail_json": os.path.join(output_dir, "comparison_detail.json"),
        "results_csv": os.path.join(output_dir, "results.csv"),
        "leading_edge_csv": os.path.join(output_dir, "leading_edge.csv"),
        "status_json": os.path.join(output_dir, "status.json"),
        "detail_dir": os.path.join(output_dir, "detail"),
    }


def save_precomputed_gsea_result(paths: dict[str, str], payload: dict[str, Any]) -> None:
    os.makedirs(paths["dir"], exist_ok=True)

    ready_payload = dict(payload)
    ready_payload.pop("ranking_profile", None)
    ready_payload["rows"] = summarize_gsea_rows(payload.get("rows", []))
    ready_payload["state"] = "ready"
    with open(paths["result_json"], "w", encoding="utf-8") as handle:
        json.dump(ready_payload, handle, ensure_ascii=False, indent=2)

    with open(paths["comparison_detail_json"], "w", encoding="utf-8") as handle:
        json.dump(
            {
                "comparison_name": payload.get("comparison_name"),
                "deg_tool": payload.get("deg_tool"),
                "gene_set_db": payload.get("gene_set_db"),
                "ranking_metric": payload.get("ranking_metric"),
                "ranked_gene_count": payload.get("validation", {}).get("ranked_gene_count"),
                "zero_cross_index": payload.get("zero_cross_index"),
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    with open(paths["status_json"], "w", encoding="utf-8") as handle:
        json.dump(
            {
                "state": "ready",
                "comparison_name": payload.get("comparison_name"),
                "deg_tool": payload.get("deg_tool"),
                "gene_set_db": payload.get("gene_set_db"),
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    with open(paths["results_csv"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "gene_set",
                "gene_set_id",
                "description",
                "gene_set_size",
                "overlap_size",
                "es",
                "nes",
                "p_value",
                "fdr",
                "leading_edge_size",
                "direction",
            ]
        )
        for row in payload.get("rows", []):
            writer.writerow(
                [
                    row.get("gene_set", ""),
                    row.get("gene_set_id", ""),
                    row.get("description", ""),
                    row.get("gene_set_size", ""),
                    row.get("overlap_size", ""),
                    row.get("es", ""),
                    row.get("nes", ""),
                    row.get("p_value", ""),
                    row.get("fdr", ""),
                    row.get("leading_edge_size", ""),
                    "up" if float(row.get("nes", 0)) >= 0 else "down",
                ]
            )

    with open(paths["leading_edge_csv"], "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["gene_set", "leading_edge_genes"])
        for row in payload.get("rows", []):
            writer.writerow(
                [
                    row.get("gene_set", ""),
                    ";".join(row.get("leading_edge_genes", [])),
                ]
            )

    try:
        result_json_size = os.path.getsize(paths["result_json"]) if os.path.exists(paths["result_json"]) else 0
        comparison_detail_size = os.path.getsize(paths["comparison_detail_json"]) if os.path.exists(paths["comparison_detail_json"]) else 0
        results_csv_size = os.path.getsize(paths["results_csv"]) if os.path.exists(paths["results_csv"]) else 0
        leading_edge_csv_size = os.path.getsize(paths["leading_edge_csv"]) if os.path.exists(paths["leading_edge_csv"]) else 0
    except OSError:
        result_json_size = comparison_detail_size = results_csv_size = leading_edge_csv_size = 0

    logger.info(
        f"[GSEA-STORE] Saved precomputed result: dir='{paths['dir']}', comparison='{payload.get('comparison_name')}', gene_set_db='{payload.get('gene_set_db')}', row_count={len(payload.get('rows', []))}, tested_gene_sets={payload.get('validation', {}).get('tested_gene_sets')}, result_json_size={result_json_size}, comparison_detail_size={comparison_detail_size}, results_csv_size={results_csv_size}, leading_edge_csv_size={leading_edge_csv_size}"
    )


def save_precomputed_gsea_failure(
    paths: dict[str, str],
    comparison_name: str,
    deg_tool: str,
    gene_set_db: str,
    error_message: str,
) -> None:
    os.makedirs(paths["dir"], exist_ok=True)
    logger.warning(
        f"[GSEA-STORE] Saving failed precomputed state: dir='{paths['dir']}', comparison='{comparison_name}', deg_tool='{deg_tool}', gene_set_db='{gene_set_db}', error_message='{error_message}'"
    )
    with open(paths["status_json"], "w", encoding="utf-8") as handle:
        json.dump(
            {
                "state": "failed",
                "comparison_name": comparison_name,
                "deg_tool": deg_tool,
                "gene_set_db": gene_set_db,
                "error_message": error_message,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )


def load_precomputed_gsea_state(paths: dict[str, str]) -> dict[str, Any] | None:
    logger.info(
        f"[GSEA-STORE] Loading precomputed state: dir='{paths['dir']}', result_json_exists={os.path.exists(paths['result_json'])}, status_json_exists={os.path.exists(paths['status_json'])}"
    )
    if os.path.exists(paths["result_json"]):
        with open(paths["result_json"], "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload["state"] = payload.get("state", "ready")
        logger.info(
            f"[GSEA-STORE] Loaded result payload: dir='{paths['dir']}', state='{payload.get('state')}', rows={len(payload.get('rows', []))}, tested_gene_sets={payload.get('validation', {}).get('tested_gene_sets')}"
        )
        return payload

    if os.path.exists(paths["status_json"]):
        with open(paths["status_json"], "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        logger.info(
            f"[GSEA-STORE] Loaded status payload: dir='{paths['dir']}', state='{payload.get('state')}', error_message='{payload.get('error_message', '')}'"
        )
        return payload

    logger.info(f"[GSEA-STORE] No stored payload found: dir='{paths['dir']}'")
    return None


def load_gsea_comparison_detail(paths: dict[str, str]) -> dict[str, Any] | None:
    if not os.path.exists(paths["comparison_detail_json"]):
        return None

    with open(paths["comparison_detail_json"], "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    logger.info(
        f"[GSEA-STORE] Loaded comparison detail: dir='{paths['dir']}', ranking_metric='{payload.get('ranking_metric')}', ranked_gene_count={payload.get('ranked_gene_count')}, zero_cross_index={payload.get('zero_cross_index')}"
    )
    return payload


def can_reuse_precomputed_gsea_result(
    paths: dict[str, str],
    comparison_name: str,
    deg_tool: str,
    gene_set_db: str,
    ranking_metric: str,
    species: str,
    permutations: int,
    database_metadata: dict[str, Any] | None,
) -> bool:
    payload = load_precomputed_gsea_state(paths)
    if not payload or payload.get("state") != "ready":
        return False

    stored_validation = payload.get("validation") or {}
    stored_database_metadata = payload.get("database_metadata") or {}
    current_database_metadata = database_metadata or {}

    same_identity = (
        payload.get("comparison_name") == comparison_name
        and normalize_deg_tool_name(payload.get("deg_tool")) == normalize_deg_tool_name(deg_tool)
        and str(payload.get("gene_set_db", "")).strip().lower() == gene_set_db
        and payload.get("ranking_metric") == ranking_metric
        and str(stored_database_metadata.get("species", "")).strip().lower()
        == str(species or "").strip().lower()
        and int(stored_validation.get("permutations", -1)) == int(permutations)
    )
    same_database_version = (
        stored_database_metadata.get("source") == current_database_metadata.get("source")
        and stored_database_metadata.get("generation_date") == current_database_metadata.get("generation_date")
        and stored_database_metadata.get("normalization_version") == current_database_metadata.get("normalization_version")
        and stored_database_metadata.get("filter_policy") == current_database_metadata.get("filter_policy")
        and stored_database_metadata.get("namespace_source_version") == current_database_metadata.get("namespace_source_version")
    )

    if same_identity and same_database_version:
        logger.info(
            f"[GSEA-STORE] Reusing matching precomputed result: dir='{paths['dir']}', comparison='{comparison_name}', gene_set_db='{gene_set_db}', permutations={permutations}"
        )
        return True

    logger.info(
        f"[GSEA-STORE] Precomputed result mismatch; recalculation required: dir='{paths['dir']}', comparison='{comparison_name}', gene_set_db='{gene_set_db}', stored_permutations={stored_validation.get('permutations')}, current_permutations={permutations}, stored_generation_date='{stored_database_metadata.get('generation_date')}', current_generation_date='{current_database_metadata.get('generation_date')}', stored_source='{stored_database_metadata.get('source')}', current_source='{current_database_metadata.get('source')}', stored_species='{stored_database_metadata.get('species')}', current_species='{current_database_metadata.get('species')}', stored_normalization_version='{stored_database_metadata.get('normalization_version')}', current_normalization_version='{current_database_metadata.get('normalization_version')}', stored_filter_policy='{stored_database_metadata.get('filter_policy')}', current_filter_policy='{current_database_metadata.get('filter_policy')}', stored_namespace_source_version='{stored_database_metadata.get('namespace_source_version')}', current_namespace_source_version='{current_database_metadata.get('namespace_source_version')}', stored_provisioned_at='{stored_database_metadata.get('provisioned_at')}', current_provisioned_at='{current_database_metadata.get('provisioned_at')}'"
    )
    return False


def get_gsea_detail_cache_path(paths: dict[str, str], gene_set_name: str) -> str:
    os.makedirs(paths["detail_dir"], exist_ok=True)
    gene_set_hash = hashlib.sha1(gene_set_name.encode("utf-8")).hexdigest()
    return os.path.join(paths["detail_dir"], f"{gene_set_hash}.json")


def load_gsea_plot_detail_cache(
    paths: dict[str, str],
    gene_set_name: str,
    comparison_name: str,
    deg_tool: str,
    gene_set_db: str,
    ranking_metric: str,
    species: str,
    permutations: int,
    database_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    detail_path = get_gsea_detail_cache_path(paths, gene_set_name)
    if not os.path.exists(detail_path):
        return None

    with open(detail_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    stored_database_metadata = payload.get("database_metadata") or {}
    current_database_metadata = database_metadata or {}
    same_identity = (
        payload.get("comparison_name") == comparison_name
        and normalize_deg_tool_name(payload.get("deg_tool")) == normalize_deg_tool_name(deg_tool)
        and str(payload.get("gene_set_db", "")).strip().lower() == gene_set_db
        and payload.get("gene_set") == gene_set_name
        and payload.get("ranking_metric") == ranking_metric
        and str(payload.get("species", "")).strip().lower() == str(species or "").strip().lower()
        and int(payload.get("permutations", -1)) == int(permutations)
        and stored_database_metadata.get("source") == current_database_metadata.get("source")
        and stored_database_metadata.get("generation_date") == current_database_metadata.get("generation_date")
        and stored_database_metadata.get("normalization_version") == current_database_metadata.get("normalization_version")
        and stored_database_metadata.get("filter_policy") == current_database_metadata.get("filter_policy")
        and stored_database_metadata.get("namespace_source_version") == current_database_metadata.get("namespace_source_version")
    )

    if not same_identity:
        logger.info(
            f"[GSEA-STORE] Plot detail cache mismatch; recalculation required: path='{detail_path}', gene_set='{gene_set_name}'"
        )
        return None

    logger.info(f"[GSEA-STORE] Reusing cached plot detail: path='{detail_path}', gene_set='{gene_set_name}'")
    return payload


def save_gsea_plot_detail_cache(
    paths: dict[str, str],
    payload: dict[str, Any],
) -> None:
    detail_path = get_gsea_detail_cache_path(paths, str(payload.get("gene_set", "")))
    with open(detail_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    try:
        cache_size = os.path.getsize(detail_path)
    except OSError:
        cache_size = 0
    logger.info(
        f"[GSEA-STORE] Saved plot detail cache: dir='{paths['dir']}', gene_set='{payload.get('gene_set', '')}', cache_path='{detail_path}', cache_size={cache_size}, leading_edge_size={payload.get('leading_edge_size')}, hit_count={len(payload.get('hit_indices', []))}, running_score_count={len(payload.get('running_scores', []))}"
    )
