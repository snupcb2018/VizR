"""
Built-in and provisioned gene set database loader for automatic GSEA.
"""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.pipeline.utils.gsea_preranked import GSEAValidationError, parse_gmt_text
from backend.utils.logger import setup_module_logger
from config.shared_config import SharedConfig


logger = setup_module_logger(__name__, "INFO")

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_RESOURCE_ROOT = REPO_ROOT / "backend" / "pipeline" / "resources" / "gsea"
CACHE_RESOURCE_ROOT = REPO_ROOT / "backend" / "pipeline" / "resources" / "gsea_cache"
PLANT_GSEA_DATABASE_BASE_URL = "https://bioinformatics.cau.edu.cn/PlantGSEA/database"
GO_BASIC_OBO_URL = "http://purl.obolibrary.org/obo/go/go-basic.obo"
GO_BP_NORMALIZATION_VERSION = "plantgsea_go_bp_v4"
GO_BP_FILTER_POLICY = "ara_go_goslim_primary_go_id_secondary"
GO_NAMESPACE_WARNING_RATIO = 0.05
GO_NAMESPACE_FAIL_RATIO = 0.20
ARABIDOPSIS_BASELINE_KEYS = {"go_bp", "kegg", "reactome"}
PLANT_GSEA_DIRECT_DATABASES = {
    "go_bp": {
        "label": "GO BP",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_GO",
    },
    "gene_family": {
        "label": "Gene Family",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_GeneFamily",
    },
    "kegg": {
        "label": "KEGG",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_KEGG",
    },
    "plantcyc": {
        "label": "PlantCyc",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_PlantCyc",
    },
    "po": {
        "label": "PO",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_PO",
    },
    "literature": {
        "label": "Literature",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_LIT",
    },
    "tf": {
        "label": "TF",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_TFT",
    },
    "mir": {
        "label": "MIR",
        "url": f"{PLANT_GSEA_DATABASE_BASE_URL}/Ara_MIR",
    },
}
USER_RESOURCE_GSEA_DATABASES = {
    "go_bp": {
        "label": "GO gene sets",
        "filename": "Ara_GO.txt",
    },
    "gene_family": {
        "label": "Gene Family based gene sets",
        "filename": "Ara_GFam.txt",
    },
    "kegg": {
        "label": "KEGG gene sets",
        "filename": "Ara_KEGG.txt",
    },
    "plantcyc": {
        "label": "PlantCyc gene sets",
        "filename": "Ara_Cyc.txt",
    },
    "po": {
        "label": "PO gene sets",
        "filename": "Ara_PO.txt",
    },
    "literature": {
        "label": "Literature collected gene sets",
        "filename": "Ara_LIT.txt",
    },
    "tf": {
        "label": "TFT gene sets",
        "filename": "Ara_TFT.txt",
    },
    "mir": {
        "label": "MIR gene sets",
        "filename": "Ara_MIR.txt",
    },
}


def _normalize_gene_id(gene_id: str) -> str:
    return gene_id.strip().upper()


def _split_embedded_gene_values(values: Any) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = list(values)

    expanded: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        for token in re.split(r"[,\n\r;]+", str(raw_value)):
            gene = _normalize_gene_id(token)
            if not gene or gene in seen:
                continue
            seen.add(gene)
            expanded.append(gene)
    return expanded


def _normalize_requested_keys(requested_keys: list[str] | None) -> set[str] | None:
    if not requested_keys:
        return None

    normalized = {
        str(key).strip().lower()
        for key in requested_keys
        if str(key).strip()
    }
    return normalized or None


def _species_directory(species: str) -> str:
    normalized = (species or "").strip().lower()
    species_map = {
        "arabidopsis": "arabidopsis",
        "arabidopsis thaliana": "arabidopsis",
    }
    return species_map.get(normalized, "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _seed_species_dir(species: str) -> Path:
    species_dir = _species_directory(species)
    if not species_dir:
        raise GSEAValidationError(f"No built-in GSEA databases are configured for species: {species}")
    return SEED_RESOURCE_ROOT / species_dir


def _cache_species_dir(species: str) -> Path:
    species_dir = _species_directory(species)
    if not species_dir:
        raise GSEAValidationError(f"No built-in GSEA databases are configured for species: {species}")
    return CACHE_RESOURCE_ROOT / species_dir


def _user_cache_species_dir(species: str, username: str | None) -> Path:
    species_dir = _species_directory(species)
    if not species_dir:
        raise GSEAValidationError(f"No built-in GSEA databases are configured for species: {species}")
    if not username or not str(username).strip():
        logger.warning(
            f"[GSEA-DB] Username was not provided for user-scoped cache resolution. Falling back to repo cache for species='{species}'"
        )
        return _cache_species_dir(species)
    return Path(SharedConfig.VIZR_PATH) / "users" / str(username).strip() / "resource" / species_dir / "gsea_cache"


def _user_resource_gsea_source_dir(species: str, username: str | None) -> Path:
    species_dir = _species_directory(species)
    if not species_dir:
        raise GSEAValidationError(f"No built-in GSEA databases are configured for species: {species}")
    if not username or not str(username).strip():
        raise GSEAValidationError("Username is required to resolve user resource GSEA source directory")
    return Path(SharedConfig.VIZR_PATH) / "users" / str(username).strip() / "resource" / species_dir / "gsea"


def _go_namespace_cache_path(username: str | None) -> Path:
    if not username or not str(username).strip():
        raise GSEAValidationError("Username is required to resolve GO namespace cache")
    return (
        Path(SharedConfig.VIZR_PATH)
        / "users"
        / str(username).strip()
        / "resource"
        / "go_namespace"
        / "go_basic_namespace.json"
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _load_gene_list(relative_path: str) -> list[str]:
    source_path = REPO_ROOT / relative_path
    if not source_path.exists():
        raise GSEAValidationError(f"Built-in GSEA gene source file was not found: {relative_path}")

    genes: list[str] = []
    seen: set[str] = set()
    with source_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            gene_id = _normalize_gene_id(raw_line)
            if not gene_id or gene_id in seen:
                continue
            seen.add(gene_id)
            genes.append(gene_id)
    return genes


def _normalize_manifest_gene_sets(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_gene_sets: list[dict[str, Any]] = []
    for gene_set in manifest.get("gene_sets", []):
        genes = gene_set.get("genes")
        if genes is None:
            merged_genes: list[str] = []
            seen: set[str] = set()
            for relative_path in gene_set.get("sources", []):
                for gene_id in _load_gene_list(relative_path):
                    if gene_id in seen:
                        continue
                    seen.add(gene_id)
                    merged_genes.append(gene_id)
            genes = merged_genes

        deduped_genes = _split_embedded_gene_values(genes or [])

        if not deduped_genes:
            continue

        normalized_gene_sets.append({
            "id": gene_set.get("id") or gene_set.get("name"),
            "name": gene_set.get("name"),
            "description": gene_set.get("description", ""),
            "go_namespace": gene_set.get("go_namespace", ""),
            "genes": deduped_genes,
        })

    return normalized_gene_sets


def _manifest_to_database_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": manifest["database_key"],
        "label": manifest["label"],
        "description": manifest["description"],
        "species": manifest["species"],
        "id_namespace": manifest["id_namespace"],
        "generation_date": manifest["generation_date"],
        "source": manifest.get("source", ""),
        "status": manifest.get("status", "ready"),
        "usage_note": manifest.get("usage_note", ""),
        "origin_url": manifest.get("origin_url", ""),
        "provisioned_at": manifest.get("provisioned_at"),
        "normalization_version": manifest.get("normalization_version"),
        "filter_policy": manifest.get("filter_policy"),
        "namespace_source_version": manifest.get("namespace_source_version"),
    }


def _manifest_to_gene_set_bundle(manifest: dict[str, Any]) -> dict[str, Any]:
    gene_sets: dict[str, dict[str, object]] = {}
    for gene_set in _normalize_manifest_gene_sets(manifest):
        gene_sets[gene_set["name"]] = {
            "id": gene_set.get("id") or gene_set.get("name"),
            "description": gene_set.get("description", ""),
            "genes": gene_set["genes"],
            "go_namespace": gene_set.get("go_namespace", ""),
        }

    if not gene_sets:
        raise GSEAValidationError(
            f"Built-in GSEA database '{manifest['database_key']}' does not contain any usable gene sets"
        )

    return {
        "database": _manifest_to_database_entry(manifest),
        "gene_sets": gene_sets,
    }


def _load_seed_manifests(species: str) -> dict[str, dict[str, Any]]:
    seed_dir = _seed_species_dir(species)
    if not seed_dir.exists():
        return {}

    manifests: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted(seed_dir.glob("*.json")):
        manifest = _load_manifest(manifest_path)
        manifest["gene_sets"] = _normalize_manifest_gene_sets(manifest)
        manifests[manifest["database_key"]] = manifest
    return manifests


def _load_cached_manifests(species: str, username: str | None = None) -> dict[str, dict[str, Any]]:
    try:
        cache_dir = _user_cache_species_dir(species, username)
    except GSEAValidationError:
        return {}

    if not cache_dir.exists():
        return {}

    manifests: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted(cache_dir.glob("*.json")):
        if manifest_path.name == "index.json":
            continue
        manifest = _load_manifest(manifest_path)
        manifest["gene_sets"] = _normalize_manifest_gene_sets(manifest)
        manifests[manifest["database_key"]] = manifest
    return manifests


def _write_cache_index(
    species: str,
    ready_manifests: dict[str, dict[str, Any]],
    failures: list[dict[str, Any]],
    username: str | None = None,
) -> None:
    cache_dir = _user_cache_species_dir(species, username)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(
        cache_dir / "index.json",
        {
            "species": species,
            "generated_at": _now_iso(),
            "databases": [_manifest_to_database_entry(manifest) for manifest in ready_manifests.values()],
            "failures": failures,
        },
    )


def _build_generic_download_headers(referer: str = "", use_range: bool = False) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Accept": "text/plain,text/tab-separated-values,text/csv,*/*;q=0.8",
        "Connection": "close",
    }
    if referer:
        headers["Referer"] = referer
    if use_range:
        headers["Range"] = "bytes=0-1048575"
    return headers


def _decode_remote_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _build_download_headers(url: str, use_range: bool = False) -> dict[str, str]:
    return _build_generic_download_headers(
        referer="https://bioinformatics.cau.edu.cn/PlantGSEA/download.php",
        use_range=use_range,
    )


def _format_response_headers(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    try:
        return {
            str(key): str(value)
            for key, value in headers.items()
            if str(key).lower() in {"content-type", "content-length", "server", "location", "accept-ranges"}
        }
    except Exception:
        return {}


def _parse_content_range_total(content_range: str) -> int | None:
    match = re.match(r"^bytes\s+\d+-\d+/(\d+)$", str(content_range).strip(), re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _probe_remote_content_length(url: str, timeout: int = 30) -> int | None:
    headers = _build_download_headers(url, use_range=True)
    headers["Range"] = "bytes=0-0"
    logger.info(
        f"[GSEA-DB][HTTP] Size probe request: url='{url}', timeout={timeout}, headers={headers}"
    )
    request = Request(url, headers=headers)

    try:
        with urlopen(request, timeout=timeout) as response:
            response_headers = _format_response_headers(getattr(response, "headers", None))
            content_range = ""
            content_length = ""
            try:
                content_range = response.headers.get("Content-Range", "")
                content_length = response.headers.get("Content-Length", "")
            except Exception:
                content_range = ""
                content_length = ""

            total_size = _parse_content_range_total(content_range)
            if total_size is None and str(getattr(response, "status", "")) == "200":
                try:
                    total_size = int(content_length) if content_length else None
                except (TypeError, ValueError):
                    total_size = None

            logger.info(
                f"[GSEA-DB][HTTP] Size probe response: url='{url}', status={getattr(response, 'status', 'unknown')}, total_size={total_size}, headers={response_headers}"
            )
            return total_size
    except HTTPError as exc:
        response_headers = _format_response_headers(getattr(exc, "headers", None))
        logger.warning(
            f"[GSEA-DB][HTTP] Size probe HTTP error: url='{url}', status={exc.code}, reason='{exc.reason}', headers={response_headers}"
        )
    except URLError as exc:
        logger.warning(
            f"[GSEA-DB][HTTP] Size probe URL error: url='{url}', reason='{exc.reason}'"
        )
    except Exception as exc:
        logger.warning(
            f"[GSEA-DB][HTTP] Size probe unexpected error: url='{url}', error='{exc}'"
        )

    return None


def _download_text(url: str, timeout: int = 30) -> str:
    retryable_http_statuses = {502, 503, 504}
    attempts = [
        ("full", False),
        ("range", True),
    ]

    last_error: Exception | None = None

    for attempt_name, use_range in attempts:
        headers = _build_download_headers(url, use_range=use_range)
        for retry_index in range(3):
            logger.info(
                f"[GSEA-DB][HTTP] Download request: url='{url}', timeout={timeout}, attempt='{attempt_name}', retry={retry_index + 1}/3, headers={headers}"
            )
            request = Request(url, headers=headers)

            try:
                with urlopen(request, timeout=timeout) as response:
                    content_type = ""
                    try:
                        content_type = response.headers.get("Content-Type", "")
                    except Exception:
                        content_type = ""
                    body = response.read()
                    response_headers = _format_response_headers(getattr(response, "headers", None))
                    logger.info(
                        f"[GSEA-DB][HTTP] Download response: url='{url}', attempt='{attempt_name}', retry={retry_index + 1}/3, status={getattr(response, 'status', 'unknown')}, bytes={len(body)}, content_type='{content_type}', headers={response_headers}"
                    )
                    return _decode_remote_bytes(body)
            except HTTPError as exc:
                error_body = ""
                try:
                    error_body = _decode_remote_bytes(exc.read())
                except Exception:
                    error_body = ""
                response_headers = _format_response_headers(getattr(exc, "headers", None))
                logger.warning(
                    f"[GSEA-DB][HTTP] Download HTTP error: url='{url}', attempt='{attempt_name}', retry={retry_index + 1}/3, status={exc.code}, reason='{exc.reason}', headers={response_headers}, body_preview={error_body[:200]!r}"
                )
                last_error = exc

                # Keep the existing 403 -> ranged retry behavior, and add transient gateway retries.
                if exc.code == 403 and not use_range:
                    break
                if exc.code in retryable_http_statuses and retry_index < 2:
                    time.sleep(1.0 * (retry_index + 1))
                    continue
                break
            except URLError as exc:
                logger.warning(
                    f"[GSEA-DB][HTTP] Download URL error: url='{url}', attempt='{attempt_name}', retry={retry_index + 1}/3, reason='{exc.reason}'"
                )
                last_error = exc
                if retry_index < 2:
                    time.sleep(1.0 * (retry_index + 1))
                    continue
                break
            except Exception as exc:
                logger.warning(
                    f"[GSEA-DB][HTTP] Download unexpected error: url='{url}', attempt='{attempt_name}', retry={retry_index + 1}/3, error='{exc}'"
                )
                last_error = exc
                if retry_index < 2:
                    time.sleep(1.0 * (retry_index + 1))
                    continue
                break

    curl_headers = _build_download_headers(url, use_range=False)
    curl_command = [
        "curl",
        "-L",
        "--max-time",
        str(timeout),
        "-H",
        f"User-Agent: {curl_headers['User-Agent']}",
        "-H",
        f"Accept: {curl_headers['Accept']}",
        "-H",
        f"Referer: {curl_headers['Referer']}",
        "-H",
        f"Connection: {curl_headers['Connection']}",
        url,
    ]
    logger.info(f"[GSEA-DB][HTTP] Falling back to curl download: url='{url}', command={curl_command}")
    try:
        completed = subprocess.run(
            curl_command,
            check=True,
            capture_output=True,
            timeout=timeout + 10,
        )
        logger.info(
            f"[GSEA-DB][HTTP] curl fallback response: url='{url}', returncode={completed.returncode}, bytes={len(completed.stdout)}, stderr_preview={completed.stderr.decode('utf-8', errors='replace')[:200]!r}"
        )
        return _decode_remote_bytes(completed.stdout)
    except subprocess.CalledProcessError as exc:
        stderr_text = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        logger.warning(
            f"[GSEA-DB][HTTP] curl fallback failed: url='{url}', returncode={exc.returncode}, stderr_preview={stderr_text[:200]!r}"
        )
        last_error = exc
    except subprocess.TimeoutExpired as exc:
        logger.warning(
            f"[GSEA-DB][HTTP] curl fallback timed out: url='{url}', timeout={timeout + 10}, stderr_preview={str(exc.stderr)[:200]!r}"
        )
        last_error = exc
    except Exception as exc:
        logger.warning(
            f"[GSEA-DB][HTTP] curl fallback unexpected error: url='{url}', error='{exc}'"
        )
        last_error = exc

    if last_error is not None:
        raise last_error
    raise GSEAValidationError(f"Failed to download remote gene set file: {url}")


def _looks_like_html(text: str) -> bool:
    stripped = text.lstrip().lower()
    return stripped.startswith("<!doctype html") or stripped.startswith("<html")


def _get_requested_plantgsea_targets(requested_keys: set[str] | None) -> list[dict[str, str]]:
    keys = sorted(requested_keys) if requested_keys else sorted(PLANT_GSEA_DIRECT_DATABASES.keys())
    targets: list[dict[str, str]] = []
    for key in keys:
        metadata = PLANT_GSEA_DIRECT_DATABASES.get(key)
        if not metadata:
            continue
        targets.append({
            "key": key,
            "label": metadata["label"],
            "url": metadata["url"],
        })
    return targets


def _get_requested_user_resource_targets(requested_keys: set[str] | None) -> list[dict[str, str]]:
    keys = sorted(requested_keys) if requested_keys else sorted(USER_RESOURCE_GSEA_DATABASES.keys())
    targets: list[dict[str, str]] = []
    for key in keys:
        metadata = USER_RESOURCE_GSEA_DATABASES.get(key)
        if not metadata:
            continue
        targets.append({
            "key": key,
            "label": metadata["label"],
            "filename": metadata["filename"],
        })
    return targets


def _split_gene_field(gene_field: str) -> list[str]:
    genes: list[str] = []
    seen: set[str] = set()
    for raw_gene in gene_field.split(","):
        gene = _normalize_gene_id(raw_gene)
        if not gene or gene in seen:
            continue
        seen.add(gene)
        genes.append(gene)
    return genes


def _extract_go_id(value: str) -> str:
    match = re.search(r"(GO:\d{7})", str(value or ""), re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).upper()


def _extract_goslim_namespace(value: str) -> str:
    match = re.search(
        r"GOslim:\s*(biological_process|cellular_component|molecular_function)",
        str(value or ""),
        re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip().lower()


def _extract_go_description(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"GO:\d{7}", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"GOslim:\s*(biological_process|cellular_component|molecular_function)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ,\t")


def _classify_go_namespace_from_description(description: str) -> str:
    normalized = str(description or "").strip().lower()
    if "biological_process" in normalized:
        return "biological_process"
    if "cellular_component" in normalized:
        return "cellular_component"
    if "molecular_function" in normalized:
        return "molecular_function"
    return "unknown"


def _parse_go_basic_namespace_map(raw_text: str) -> dict[str, str]:
    namespace_map: dict[str, str] = {}
    current_id: str | None = None
    current_namespace: str | None = None
    in_term = False

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if line == "[Term]":
            if current_id and current_namespace:
                namespace_map[current_id] = current_namespace
            current_id = None
            current_namespace = None
            in_term = True
            continue
        if line.startswith("[") and line != "[Term]":
            if current_id and current_namespace:
                namespace_map[current_id] = current_namespace
            current_id = None
            current_namespace = None
            in_term = False
            continue
        if not in_term or not line:
            continue
        if line.startswith("id: GO:"):
            current_id = line.split("id:", 1)[1].strip()
            continue
        if line.startswith("namespace:"):
            current_namespace = line.split("namespace:", 1)[1].strip()

    if current_id and current_namespace:
        namespace_map[current_id] = current_namespace

    if not namespace_map:
        raise GSEAValidationError("Failed to parse GO namespace map from go-basic.obo")
    return namespace_map


def _download_go_namespace_text(timeout: int = 60) -> str:
    headers = _build_generic_download_headers(referer="https://geneontology.org/docs/download-ontology/")
    request = Request(GO_BASIC_OBO_URL, headers=headers)
    logger.info(
        f"[GSEA-GO] Downloading GO namespace source: url='{GO_BASIC_OBO_URL}', timeout={timeout}"
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            logger.info(
                f"[GSEA-GO] GO namespace download response: status={getattr(response, 'status', 'unknown')}, bytes={len(body)}"
            )
            return _decode_remote_bytes(body)
    except Exception as exc:
        logger.warning(f"[GSEA-GO] Python GO namespace download failed: error='{exc}'")

    curl_command = [
        "curl",
        "-L",
        "--max-time",
        str(timeout),
        "-H",
        f"User-Agent: {headers['User-Agent']}",
        "-H",
        f"Accept: {headers['Accept']}",
        "-H",
        "Referer: https://geneontology.org/docs/download-ontology/",
        "-H",
        f"Connection: {headers['Connection']}",
        GO_BASIC_OBO_URL,
    ]
    logger.info(f"[GSEA-GO] Falling back to curl namespace download: command={curl_command}")
    completed = subprocess.run(
        curl_command,
        check=True,
        capture_output=True,
        timeout=timeout + 10,
    )
    logger.info(
        f"[GSEA-GO] curl namespace download response: returncode={completed.returncode}, bytes={len(completed.stdout)}"
    )
    return _decode_remote_bytes(completed.stdout)


def _ensure_go_namespace_cache(username: str | None) -> dict[str, Any]:
    cache_path = _go_namespace_cache_path(username)
    if cache_path.exists():
        payload = _load_manifest(cache_path)
        if isinstance(payload.get("namespaces"), dict) and payload["namespaces"]:
            logger.info(
                f"[GSEA-GO] Reusing GO namespace cache: path='{cache_path}', version='{payload.get('namespace_source_version', '')}', term_count={len(payload['namespaces'])}"
            )
            return payload

    raw_text = _download_go_namespace_text()
    namespace_map = _parse_go_basic_namespace_map(raw_text)
    namespace_source_version = hashlib.sha1(raw_text.encode("utf-8")).hexdigest()
    payload = {
        "source_url": GO_BASIC_OBO_URL,
        "generated_at": _now_iso(),
        "namespace_source_version": namespace_source_version,
        "term_count": len(namespace_map),
        "namespaces": namespace_map,
    }
    _write_manifest(cache_path, payload)
    logger.info(
        f"[GSEA-GO] Saved GO namespace cache: path='{cache_path}', version='{namespace_source_version}', term_count={len(namespace_map)}"
    )
    return payload


def _normalize_go_bp_gene_sets(
    gene_sets: dict[str, dict[str, object]],
    username: str | None,
) -> tuple[dict[str, dict[str, object]], dict[str, Any]]:
    namespace_payload = _ensure_go_namespace_cache(username)
    namespace_map = namespace_payload.get("namespaces", {}) or {}

    counts = {
        "biological_process": 0,
        "cellular_component": 0,
        "molecular_function": 0,
        "unknown": 0,
    }
    source_counts = {
        "goslim_field": 0,
        "go_id_map": 0,
        "description_fallback": 0,
    }
    filtered_gene_sets: dict[str, dict[str, object]] = {}
    namespace_source_used = "goslim_field"
    go_id_namespace_mismatch_count = 0
    sample_debug_rows: list[dict[str, str]] = []

    for gene_set_name, gene_set_info in gene_sets.items():
        raw_go_id = str(gene_set_info.get("id") or "")
        go_id = _extract_go_id(raw_go_id)
        goslim_namespace = str(gene_set_info.get("go_namespace") or "").strip().lower()
        go_id_namespace = str(namespace_map.get(go_id, "")).strip().lower()
        namespace = goslim_namespace
        source_key = "goslim_field"

        if not namespace:
            namespace = go_id_namespace
            source_key = "go_id_map"
        if not namespace:
            namespace = _classify_go_namespace_from_description(str(gene_set_info.get("description", "")))
            source_key = "description_fallback"

        if source_key != "goslim_field":
            namespace_source_used = source_key
        source_counts[source_key] += 1

        if goslim_namespace and go_id_namespace and goslim_namespace != go_id_namespace:
            go_id_namespace_mismatch_count += 1

        if len(sample_debug_rows) < 5:
            sample_debug_rows.append({
                "name": gene_set_name,
                "raw_go_id": raw_go_id,
                "normalized_go_id": go_id,
                "goslim_namespace": goslim_namespace,
                "go_id_namespace": go_id_namespace,
                "selected_namespace": namespace,
                "source_key": source_key,
            })

        if namespace not in counts:
            namespace = "unknown"
        counts[namespace] += 1

        if namespace == "biological_process":
            filtered_gene_sets[gene_set_name] = gene_set_info

    total_count = sum(counts.values())
    unknown_ratio = (counts["unknown"] / total_count) if total_count else 1.0
    example_names = list(filtered_gene_sets.keys())[:3]

    logger.info(
        f"[GSEA-GO] Namespace classification summary: total_count={total_count}, bp_count={counts['biological_process']}, cc_count={counts['cellular_component']}, mf_count={counts['molecular_function']}, unknown_count={counts['unknown']}, unknown_ratio={unknown_ratio:.4f}, namespace_source_used='{namespace_source_used}', goslim_count={source_counts['goslim_field']}, go_id_count={source_counts['go_id_map']}, description_count={source_counts['description_fallback']}, go_id_namespace_mismatch_count={go_id_namespace_mismatch_count}, example_bp_sets={example_names}, sample_debug_rows={sample_debug_rows}"
    )

    if counts["unknown"] and unknown_ratio > GO_NAMESPACE_WARNING_RATIO:
        logger.warning(
            f"[GSEA-GO] GO namespace classification produced elevated unknown ratio: unknown_count={counts['unknown']}, total_count={total_count}, unknown_ratio={unknown_ratio:.4f}"
        )

    if counts["biological_process"] <= 0:
        raise GSEAValidationError("PlantGSEA Ara_GO did not yield any biological_process terms")
    if unknown_ratio > GO_NAMESPACE_FAIL_RATIO:
        raise GSEAValidationError(
            f"PlantGSEA Ara_GO classification quality is too low (unknown_ratio={unknown_ratio:.4f})"
        )

    return filtered_gene_sets, {
        "normalization_version": GO_BP_NORMALIZATION_VERSION,
        "filter_policy": GO_BP_FILTER_POLICY,
        "namespace_source_version": namespace_payload.get("namespace_source_version"),
        "namespace_source_used": namespace_source_used,
        "go_namespace_counts": counts,
        "go_namespace_source_counts": source_counts,
        "go_id_namespace_mismatch_count": go_id_namespace_mismatch_count,
        "unknown_ratio": unknown_ratio,
    }


def _parse_plantgsea_table_text(text: str) -> dict[str, dict[str, object]]:
    gene_sets: dict[str, dict[str, object]] = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 4:
            raise GSEAValidationError(
                f"PlantGSEA table line {line_number} must contain at least 4 tab-delimited columns"
            )

        gene_set_name = parts[0]
        gene_set_id = parts[1]
        description = parts[2]
        gene_field = parts[-1]

        if not gene_set_name:
            raise GSEAValidationError(f"PlantGSEA table line {line_number} has an empty gene set name")

        genes = _split_gene_field(gene_field)
        if not genes:
            continue

        if gene_set_name in gene_sets:
            raise GSEAValidationError(f"Duplicate gene set name found in PlantGSEA table: {gene_set_name}")

        gene_sets[gene_set_name] = {
            "id": gene_set_id or gene_set_name,
            "description": description,
            "genes": genes,
        }

    if not gene_sets:
        raise GSEAValidationError("No valid gene sets were found in the PlantGSEA table")

    return gene_sets


def _parse_ara_go_text(text: str) -> dict[str, dict[str, object]]:
    gene_sets: dict[str, dict[str, object]] = {}
    sample_rows: list[dict[str, str]] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split("\t")]
        if len(parts) != 3:
            raise GSEAValidationError(
                f"Ara_GO line {line_number} must contain exactly 3 tab-delimited columns"
            )

        gene_set_name, go_info, gene_field = parts
        if not gene_set_name:
            raise GSEAValidationError(f"Ara_GO line {line_number} has an empty gene set name")

        go_id = _extract_go_id(go_info)
        if not go_id:
            raise GSEAValidationError(f"Ara_GO line {line_number} does not contain a GO ID")

        go_namespace = _extract_goslim_namespace(go_info)
        description = _extract_go_description(go_info)
        genes = _split_gene_field(gene_field)
        if not genes:
            continue

        if gene_set_name in gene_sets:
            raise GSEAValidationError(f"Duplicate gene set name found in Ara_GO: {gene_set_name}")

        gene_sets[gene_set_name] = {
            "id": go_id,
            "description": description,
            "genes": genes,
            "go_namespace": go_namespace,
            "go_namespace_source": "goslim_field" if go_namespace else "",
        }

        if len(sample_rows) < 5:
            sample_rows.append({
                "name": gene_set_name,
                "go_id": go_id,
                "go_namespace": go_namespace,
                "description": description,
                "gene_count": str(len(genes)),
            })

    if not gene_sets:
        raise GSEAValidationError("No valid gene sets were found in Ara_GO")

    logger.info(
        f"[GSEA-GO] Parsed Ara_GO rows: gene_set_count={len(gene_sets)}, sample_rows={sample_rows}"
    )
    return gene_sets


def _parse_remote_gene_sets(text: str, database_key: str | None = None) -> dict[str, dict[str, object]]:
    if _looks_like_html(text):
        raise GSEAValidationError("Remote PlantGSEA response returned HTML instead of a gene set file")

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise GSEAValidationError("Remote PlantGSEA response is empty")

    first_parts = [part.strip() for part in lines[0].split("\t")]
    if (
        database_key == "go_bp"
        and len(first_parts) == 3
        and "GO:" in first_parts[1]
        and "GOslim:" in first_parts[1]
    ):
        return _parse_ara_go_text(text)
    if len(first_parts) >= 4 and "," in first_parts[-1]:
        return _parse_plantgsea_table_text(text)

    return parse_gmt_text(text)


def _build_remote_manifest(
    species: str,
    key: str,
    label: str,
    source_url: str,
    gene_sets: dict[str, dict[str, object]],
    remote_content_length: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    description_map = {
        "go_bp": "Arabidopsis biological process gene sets automatically provisioned for VizR GSEA.",
        "kegg": "Arabidopsis KEGG-like pathway gene sets automatically provisioned for VizR GSEA.",
        "reactome": "Arabidopsis pathway gene sets automatically provisioned for VizR GSEA.",
        "gene_family": "Arabidopsis gene family sets automatically provisioned for VizR GSEA.",
        "plantcyc": "Arabidopsis PlantCyc pathway gene sets automatically provisioned for VizR GSEA.",
        "po": "Arabidopsis Plant Ontology gene sets automatically provisioned for VizR GSEA.",
        "literature": "Arabidopsis literature-collected gene sets automatically provisioned for VizR GSEA.",
        "tf": "Arabidopsis transcription factor gene sets automatically provisioned for VizR GSEA.",
        "mir": "Arabidopsis microRNA-related gene sets automatically provisioned for VizR GSEA.",
    }


def _build_user_resource_manifest(
    species: str,
    key: str,
    label: str,
    source_path: Path,
    gene_sets: dict[str, dict[str, object]],
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra_metadata = extra_metadata or {}
    description_map = {
        "go_bp": "Arabidopsis biological process gene sets loaded from the user resource snapshot for VizR GSEA.",
        "kegg": "Arabidopsis KEGG gene sets loaded from the user resource snapshot for VizR GSEA.",
        "gene_family": "Arabidopsis gene family gene sets loaded from the user resource snapshot for VizR GSEA.",
        "plantcyc": "Arabidopsis PlantCyc gene sets loaded from the user resource snapshot for VizR GSEA.",
        "po": "Arabidopsis Plant Ontology gene sets loaded from the user resource snapshot for VizR GSEA.",
        "literature": "Arabidopsis literature-collected gene sets loaded from the user resource snapshot for VizR GSEA.",
        "tf": "Arabidopsis transcription factor gene sets loaded from the user resource snapshot for VizR GSEA.",
        "mir": "Arabidopsis microRNA-related gene sets loaded from the user resource snapshot for VizR GSEA.",
    }

    stat = source_path.stat()
    return {
        "database_key": key,
        "label": label,
        "description": description_map.get(key, f"{label} loaded from the user resource snapshot for VizR GSEA."),
        "source": "User resource snapshot",
        "generation_date": datetime.fromtimestamp(stat.st_mtime, timezone.utc).date().isoformat(),
        "species": _species_directory(species),
        "id_namespace": "AGI locus IDs",
        "status": "ready",
        "usage_note": "Loaded from the user resource GSEA database directory.",
        "origin_url": str(source_path),
        "provisioned_at": _now_iso(),
        "source_filename": source_path.name,
        "source_size": stat.st_size,
        "source_mtime": stat.st_mtime,
        "normalization_version": extra_metadata.get("normalization_version"),
        "filter_policy": extra_metadata.get("filter_policy"),
        "namespace_source_version": extra_metadata.get("namespace_source_version"),
        "namespace_source_used": extra_metadata.get("namespace_source_used"),
        "go_namespace_counts": extra_metadata.get("go_namespace_counts"),
        "unknown_ratio": extra_metadata.get("unknown_ratio"),
        "gene_sets": [
            {
                "id": gene_set_info.get("id", gene_set_name),
                "name": gene_set_name,
                "description": str(gene_set_info.get("description", "") or ""),
                "go_namespace": str(gene_set_info.get("go_namespace", "") or ""),
                "genes": _split_embedded_gene_values(gene_set_info.get("genes", [])),
            }
            for gene_set_name, gene_set_info in gene_sets.items()
        ],
    }


def _build_seed_fallback_manifest(seed_manifest: dict[str, Any], error_message: str | None = None) -> dict[str, Any]:
    usage_note = "Local fallback snapshot retained for automatic GSEA."
    if error_message:
        usage_note = f"{usage_note} External refresh was unavailable: {error_message}"

    return {
        **seed_manifest,
        "status": "fallback_used",
        "usage_note": usage_note,
        "origin_url": seed_manifest.get("origin_url", ""),
        "provisioned_at": _now_iso(),
        "normalization_version": seed_manifest.get("normalization_version"),
        "filter_policy": seed_manifest.get("filter_policy"),
        "namespace_source_version": seed_manifest.get("namespace_source_version"),
        "gene_sets": _normalize_manifest_gene_sets(seed_manifest),
    }


def _build_cached_reuse_manifest(cached_manifest: dict[str, Any], error_message: str) -> dict[str, Any]:
    return {
        **cached_manifest,
        "status": "ready",
        "usage_note": f"Existing cached database reused because refresh was unavailable: {error_message}",
        "provisioned_at": cached_manifest.get("provisioned_at") or _now_iso(),
        "normalization_version": cached_manifest.get("normalization_version"),
        "filter_policy": cached_manifest.get("filter_policy"),
        "namespace_source_version": cached_manifest.get("namespace_source_version"),
        "gene_sets": _normalize_manifest_gene_sets(cached_manifest),
    }


def _is_cached_remote_manifest_compatible(
    key: str,
    cached_manifest: dict[str, Any],
    extra_metadata: dict[str, Any] | None,
) -> bool:
    if not cached_manifest:
        return False
    extra_metadata = extra_metadata or {}
    if key != "go_bp":
        return True
    return (
        cached_manifest.get("normalization_version") == extra_metadata.get("normalization_version")
        and cached_manifest.get("filter_policy") == extra_metadata.get("filter_policy")
        and cached_manifest.get("namespace_source_version") == extra_metadata.get("namespace_source_version")
    )


def _fetch_plantgsea_manifest(
    species: str,
    target: dict[str, str],
    cached_manifest: dict[str, Any] | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    key = target["key"]
    label = target["label"]
    remote_content_length = _probe_remote_content_length(target["url"])
    cached_remote_size = None
    if cached_manifest is not None:
        try:
            cached_remote_size = int(cached_manifest.get("remote_content_length"))
        except (TypeError, ValueError):
            cached_remote_size = None

    extra_metadata: dict[str, Any] | None = None

    if key == "go_bp":
        namespace_payload = _ensure_go_namespace_cache(username)
        extra_metadata = {
            "normalization_version": GO_BP_NORMALIZATION_VERSION,
            "filter_policy": GO_BP_FILTER_POLICY,
            "namespace_source_version": namespace_payload.get("namespace_source_version"),
        }

    if (
        cached_manifest is not None
        and remote_content_length is not None
        and cached_remote_size == remote_content_length
        and _is_cached_remote_manifest_compatible(key, cached_manifest, extra_metadata)
    ):
        logger.info(
            f"[GSEA-DB][FETCH] Reusing cached manifest without download: species='{species}', key='{key}', label='{label}', remote_size={remote_content_length}, cached_remote_size={cached_remote_size}"
        )
        return _build_cached_reuse_manifest(
            cached_manifest,
            f"remote size unchanged ({remote_content_length} bytes)",
        )

    logger.info(
        f"[GSEA-DB][FETCH] Fetching PlantGSEA manifest: species='{species}', key='{key}', label='{label}', url='{target['url']}', remote_size={remote_content_length}, cached_remote_size={cached_remote_size}"
    )
    raw_text = _download_text(target["url"])
    gene_sets = _parse_remote_gene_sets(raw_text, key)
    if key == "go_bp":
        gene_sets, normalized_metadata = _normalize_go_bp_gene_sets(gene_sets, username)
        extra_metadata = {
            **(extra_metadata or {}),
            **normalized_metadata,
        }
    logger.info(
        f"[GSEA-DB][FETCH] Parsed PlantGSEA manifest: key='{key}', label='{label}', gene_set_count={len(gene_sets)}"
    )
    return _build_remote_manifest(
        species,
        key,
        label,
        target["url"],
        gene_sets,
        remote_content_length,
        extra_metadata,
    )


def _is_cached_user_resource_manifest_current(
    cached_manifest: dict[str, Any] | None,
    source_path: Path,
    expected_metadata: dict[str, Any] | None = None,
) -> bool:
    if not cached_manifest:
        return False
    try:
        stat = source_path.stat()
    except OSError:
        return False
    is_current = (
        cached_manifest.get("source_filename") == source_path.name
        and int(cached_manifest.get("source_size") or -1) == int(stat.st_size)
        and float(cached_manifest.get("source_mtime") or -1) == float(stat.st_mtime)
    )
    if not is_current:
        return False
    expected_metadata = expected_metadata or {}
    for key in ("normalization_version", "filter_policy", "namespace_source_version"):
        expected_value = expected_metadata.get(key)
        if expected_value is None:
            continue
        if cached_manifest.get(key) != expected_value:
            return False
    return True


def _fetch_user_resource_manifest(
    species: str,
    target: dict[str, str],
    username: str | None,
    cached_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_dir = _user_resource_gsea_source_dir(species, username)
    source_path = source_dir / target["filename"]
    if not source_path.exists():
        raise GSEAValidationError(
            f"User resource GSEA source file was not found: {source_path}"
        )

    expected_metadata: dict[str, Any] | None = None
    if target["key"] == "go_bp":
        namespace_payload = _ensure_go_namespace_cache(username)
        expected_metadata = {
            "normalization_version": GO_BP_NORMALIZATION_VERSION,
            "filter_policy": GO_BP_FILTER_POLICY,
            "namespace_source_version": namespace_payload.get("namespace_source_version"),
        }

    if _is_cached_user_resource_manifest_current(cached_manifest, source_path, expected_metadata):
        logger.info(
            f"[GSEA-DB][RESOURCE] Reusing cached manifest without reparsing: species='{species}', key='{target['key']}', file='{source_path.name}'"
        )
        return _build_cached_reuse_manifest(
            cached_manifest,
            f"user resource source unchanged ({source_path.name})",
        )

    raw_text = source_path.read_text(encoding="utf-8")
    gene_sets = _parse_remote_gene_sets(raw_text, target["key"])
    if target["key"] == "go_bp":
        gene_sets, normalized_metadata = _normalize_go_bp_gene_sets(gene_sets, username)
        expected_metadata = {
            **(expected_metadata or {}),
            **normalized_metadata,
        }
    logger.info(
        f"[GSEA-DB][RESOURCE] Parsed user resource GSEA file: species='{species}', key='{target['key']}', file='{source_path.name}', gene_set_count={len(gene_sets)}"
    )
    return _build_user_resource_manifest(
        species,
        target["key"],
        target["label"],
        source_path,
        gene_sets,
        expected_metadata,
    )


def ensure_provisioned_gsea_databases(
    species: str,
    requested_keys: list[str] | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    species_dir = _species_directory(species)
    if not species_dir:
        return {"species": species, "databases": [], "failures": []}

    normalized_requested_keys = _normalize_requested_keys(requested_keys)
    logger.info(
        f"[GSEA-DB] Provisioning start: species='{species}', species_dir='{species_dir}', username='{username}', requested_keys={sorted(normalized_requested_keys) if normalized_requested_keys else 'all'}"
    )
    cached_manifests = _load_cached_manifests(species, username)
    logger.info(
        f"[GSEA-DB] Local manifest state: species='{species}', cached_keys={sorted(cached_manifests.keys())}"
    )
    ready_manifests: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []

    requested_targets = _get_requested_user_resource_targets(normalized_requested_keys)
    logger.info(
        f"[GSEA-DB] User resource targets resolved: species='{species}', targets={[target['key'] for target in requested_targets]}"
    )

    for target in requested_targets:
        key = target["key"]
        label = target["label"]
        try:
            manifest = _fetch_user_resource_manifest(species, target, username, cached_manifests.get(key))
            ready_manifests[key] = manifest
            logger.info(
                f"[GSEA-DB] Provisioned user resource database: key='{key}', label='{label}', source_filename='{manifest.get('source_filename')}', source_size={manifest.get('source_size')}"
            )
        except Exception as exc:
            logger.warning(
                f"[GSEA-DB] Failed to provision user resource database: species='{species}', key='{key}', label='{label}', filename='{target['filename']}', error='{exc}'"
            )
            failures.append({
                "key": key,
                "label": label,
                "state": "failed",
                "error_message": str(exc),
                "origin_url": target["filename"],
            })

    cache_dir = _user_cache_species_dir(species, username)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if normalized_requested_keys is None:
        current_files = {path.name for path in cache_dir.glob("*.json")}
        expected_files = {f"{key}.json" for key in ready_manifests.keys()} | {"index.json"}
        for stale_name in current_files - expected_files:
            try:
                (cache_dir / stale_name).unlink()
            except OSError:
                logger.warning(f"[GSEA-DB] Failed to remove stale cache manifest: {stale_name}")

    for key, manifest in ready_manifests.items():
        _write_manifest(cache_dir / f"{key}.json", manifest)

    _write_cache_index(species, ready_manifests, failures, username)
    logger.info(
        f"[GSEA-DB] Provisioning complete: species='{species}', username='{username}', cache_dir='{cache_dir}', ready_keys={sorted(ready_manifests.keys())}, failure_keys={[failure['key'] for failure in failures]}"
    )
    return {
        "species": species,
        "databases": [_manifest_to_database_entry(manifest) for manifest in ready_manifests.values()],
        "failures": failures,
    }


def get_available_builtin_gsea_databases(
    species: str,
    requested_keys: list[str] | None = None,
    username: str | None = None,
) -> list[dict[str, Any]]:
    normalized_requested_keys = _normalize_requested_keys(requested_keys)
    manifests = _load_cached_manifests(species, username)
    if not manifests and username:
        provisioning = ensure_provisioned_gsea_databases(species, requested_keys, username)
        return sorted(provisioning["databases"], key=lambda item: item["label"].lower())

    databases = [
        _manifest_to_database_entry(manifest)
        for key, manifest in manifests.items()
        if not normalized_requested_keys or key in normalized_requested_keys
    ]
    databases.sort(key=lambda item: item["label"].lower())
    return databases


def load_builtin_gene_sets(species: str, database_key: str, username: str | None = None) -> dict[str, Any]:
    manifests = _load_cached_manifests(species, username)
    manifest = manifests.get(database_key)
    if not manifest and username:
        provisioning = ensure_provisioned_gsea_databases(species, [database_key], username)
        manifests = _load_cached_manifests(species, username)
        manifest = manifests.get(database_key)
        if not manifest:
            failure = next((item for item in provisioning.get("failures", []) if item.get("key") == database_key), None)
            if failure:
                raise GSEAValidationError(failure.get("error_message") or f"GSEA database '{database_key}' is unavailable")

    if not manifest:
        raise GSEAValidationError(
            f"Built-in GSEA database '{database_key}' is not available for species: {species}"
        )

    return _manifest_to_gene_set_bundle(manifest)
