"""
GO Enrichment Analysis using g:Profiler Python Library

Uses the official gprofiler-official Python package for reliable gene functional enrichment analysis.

Reference: https://pypi.org/project/gprofiler-official/
API Docs: https://biit.cs.ut.ee/gprofiler/page/apis
"""

import pandas as pd
import logging
from typing import List, Dict, Optional, Tuple

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')


def extract_genes(row: pd.Series, log_first_only: bool = False) -> List[str]:
    """
    Extract gene list from intersections field.
    Handles multiple formats returned by g:Profiler library.

    Args:
        row: DataFrame row containing intersections field
        log_first_only: If True, only log for the first term (to reduce log spam)

    Returns:
        List of gene IDs
    """
    inter = row.get("intersections", [])

    if log_first_only and not hasattr(extract_genes, '_first_logged'):
        logger.info(f"🔍 [EXTRACT-GENES] Row columns: {list(row.index)}")
        logger.info(f"🔍 [EXTRACT-GENES] Intersections type: {type(inter)}")
        logger.info(f"🔍 [EXTRACT-GENES] Intersections sample (first 100 chars): {str(inter)[:100]}")
        extract_genes._first_logged = True

    if isinstance(inter, dict):  # 다중 query일 때
        gset = set()
        for v in inter.values():
            gset.update(v)
        return sorted(gset)
    elif isinstance(inter, (list, tuple, set)):
        return sorted(list(inter))
    else:  # 혹시 문자열인 경우 대비
        return [g.strip() for g in str(inter).split(",") if g.strip()]


def get_first_available(row: pd.Series, cols: List[str]):
    """
    Get first available value from multiple possible column names.

    Args:
        row: DataFrame row
        cols: List of column names to check

    Returns:
        First non-null value found, or None
    """
    for c in cols:
        if c in row and pd.notna(row[c]):
            return row[c]
    return None


class GProfilerAPI:
    """g:Profiler API client using official Python library"""

    # Available data sources
    DATABASES = {
        'GO_BP': 'GO:BP',  # Gene Ontology Biological Process
        'GO_MF': 'GO:MF',  # Gene Ontology Molecular Function
        'GO_CC': 'GO:CC',  # Gene Ontology Cellular Component
        'KEGG': 'KEGG',    # KEGG pathways
        'REAC': 'REAC',    # Reactome pathways
    }

    # Organism mapping
    ORGANISMS = {
        'arabidopsis': 'athaliana',
        'human': 'hsapiens',
        'mouse': 'mmusculus',
        'rat': 'rnorvegicus',
    }

    def __init__(self, organism: str = 'arabidopsis', timeout: int = 60):
        """
        Initialize g:Profiler API client

        Args:
            organism: Organism name (arabidopsis, human, mouse, rat)
            timeout: Request timeout in seconds
        """
        self.organism = self.ORGANISMS.get(organism.lower(), 'athaliana')
        self.timeout = timeout
        logger.info(f"🔬 [GPROFILER] Initialized g:Profiler client for {self.organism}")

    def run_enrichment(
        self,
        genes: List[str],
        databases: List[str] = ['GO_BP', 'GO_MF', 'GO_CC'],
        description: str = "VizR Gene List",
        p_value_cutoff: float = 0.05
    ) -> Dict[str, pd.DataFrame]:
        """
        Run complete enrichment analysis workflow using Python library

        Args:
            genes: List of gene IDs (e.g., ['AT1G01010', 'AT2G01020'])
            databases: List of databases to query (GO_BP, GO_MF, GO_CC, KEGG, REAC)
            description: Description of gene list
            p_value_cutoff: Adjusted p-value cutoff for filtering results

        Returns:
            Dictionary mapping database name to results DataFrame
        """
        try:
            from gprofiler import GProfiler

            logger.info(f"🧬 [GPROFILER] Starting enrichment analysis for {len(genes)} genes")
            logger.info(f"📚 [GPROFILER] Organism: {self.organism}")
            logger.info(f"📚 [GPROFILER] Databases: {', '.join(databases)}")
            logger.info(f"🎯 [GPROFILER] P-value cutoff: {p_value_cutoff}")

            # Convert database names to g:Profiler format
            sources = [self.DATABASES.get(db, db) for db in databases if db in self.DATABASES]
            if not sources:
                logger.error(f"❌ [GPROFILER] No valid databases specified")
                return {}

            logger.info(f"📊 [GPROFILER] Converted sources: {', '.join(sources)}")
            logger.info(f"📋 [GPROFILER] Query genes (first 10): {genes[:10]}")

            # Run g:Profiler analysis using Python library
            gp = GProfiler(return_dataframe=True)
            res = gp.profile(
                organism=self.organism,
                query=genes,
                sources=sources,
                no_evidences=False  # Enable intersections field (gene lists)
            )

            if res.empty:
                logger.warning(f"⚠️ [GPROFILER] No enrichment results found")
                return {}

            logger.info(f"📊 [GPROFILER] Retrieved {len(res)} total enriched terms")

            # Extract gene list from intersections field (log only first term to reduce spam)
            # Note: Use 'genes' not '_genes' because itertuples() cannot access underscore-prefixed columns
            res = res.assign(genes=res.apply(lambda r: extract_genes(r, log_first_only=True), axis=1))

            # Log gene extraction statistics
            gene_counts = res['genes'].apply(len)
            logger.info(f"📊 [GPROFILER] Gene extraction stats: min={gene_counts.min()}, max={gene_counts.max()}, avg={gene_counts.mean():.1f}")

            # Standardize column names
            res = res.assign(
                term_id=res.apply(lambda r: get_first_available(r, ["term_id", "native"]), axis=1),
                term_name=res.apply(lambda r: get_first_available(r, ["term_name", "name"]), axis=1),
                p_adj=res.apply(lambda r: get_first_available(r, ["adjusted_p_value", "p_value", "padj"]), axis=1)
            )

            # Group results by source (database)
            grouped_results = {}
            for db in databases:
                source = self.DATABASES.get(db, db)
                db_results = res[res['source'] == source].copy()

                if len(db_results) > 0:
                    # Filter by p-value cutoff
                    db_results = db_results[db_results['p_adj'] <= p_value_cutoff].copy()

                    if len(db_results) > 0:
                        # Convert to standard format
                        df_data = []
                        for idx, row in enumerate(db_results.itertuples(), 1):
                            gene_list = getattr(row, 'genes', [])

                            df_data.append({
                                'Rank': idx,
                                'Term': f"{row.term_id}: {row.term_name}",
                                'Term ID': row.term_id,
                                'Term Name': row.term_name,
                                'P-value': row.p_adj,
                                'Adjusted P-value': row.p_adj,
                                'Genes': ';'.join(gene_list),
                                'Gene Count': len(gene_list),
                                'Term Size': getattr(row, 'term_size', 0),
                                'Query Size': getattr(row, 'query_size', 0),
                                'Intersection Size': getattr(row, 'intersection_size', len(gene_list)),
                            })

                        df = pd.DataFrame(df_data)
                        df = df.sort_values('Adjusted P-value')
                        grouped_results[db] = df
                        logger.info(f"   └─ {db}: Found {len(df)} significant terms (p < {p_value_cutoff})")
                    else:
                        logger.warning(f"   └─ {db}: No significant terms found (p < {p_value_cutoff})")
                else:
                    logger.warning(f"   └─ {db}: No results from API")

            logger.info(f"✅ [GPROFILER] Enrichment analysis complete: {len(grouped_results)} databases with results")
            return grouped_results

        except ImportError:
            logger.error(f"❌ [GPROFILER] gprofiler-official library not installed")
            logger.error(f"   └─ Install with: pip install gprofiler-official")
            return {}
        except Exception as e:
            logger.error(f"❌ [GPROFILER] Unexpected error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {}

    def export_results(
        self,
        results: Dict[str, pd.DataFrame],
        output_dir: str,
        prefix: str = "enrichment"
    ) -> List[str]:
        """
        Export enrichment results to CSV files

        Args:
            results: Dictionary from run_enrichment()
            output_dir: Output directory path
            prefix: File prefix for output files

        Returns:
            List of created file paths
        """
        import os

        logger.info(f"💾 [GPROFILER] Exporting results to {output_dir}")

        os.makedirs(output_dir, exist_ok=True)
        output_files = []

        for db_name, df in results.items():
            filename = f"{prefix}_{db_name}.csv"
            filepath = os.path.join(output_dir, filename)

            df.to_csv(filepath, index=False, encoding='utf-8')
            output_files.append(filepath)
            logger.info(f"   └─ Saved {db_name}: {filepath} ({len(df)} terms)")

        logger.info(f"✅ [GPROFILER] Exported {len(output_files)} result files")
        return output_files


# Convenience function for quick analysis
def analyze_gene_list(
    genes: List[str],
    output_dir: Optional[str] = None,
    databases: List[str] = ['GO_BP', 'GO_MF', 'GO_CC'],
    p_value_cutoff: float = 0.05,
    description: str = "VizR Gene List",
    organism: str = 'arabidopsis'
) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """
    Convenience function to run complete GO enrichment analysis

    Args:
        genes: List of gene IDs
        output_dir: Optional output directory for CSV export
        databases: Databases to query (GO_BP, GO_MF, GO_CC, KEGG, REAC)
        p_value_cutoff: Adjusted p-value cutoff
        description: Gene list description
        organism: Organism name (arabidopsis, human, mouse, rat)

    Returns:
        Tuple of (results dict, list of output files)
    """
    api = GProfilerAPI(organism=organism)
    results = api.run_enrichment(genes, databases, description, p_value_cutoff)

    output_files = []
    if output_dir and results:
        output_files = api.export_results(results, output_dir)

    return results, output_files


if __name__ == "__main__":
    # Example usage with Arabidopsis genes
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Test with Arabidopsis genes
    test_genes = [
        'AT1G01010', 'AT1G01020', 'AT1G01030', 'AT1G01040', 'AT1G01050',
        'AT1G01060', 'AT1G01070', 'AT1G01080', 'AT1G01090', 'AT1G01100'
    ]

    print("🧬 Testing g:Profiler with Arabidopsis genes...")
    print(f"📝 Genes: {', '.join(test_genes)}")

    api = GProfilerAPI(organism='arabidopsis')
    results = api.run_enrichment(
        genes=test_genes,
        databases=['GO_BP', 'GO_MF', 'GO_CC'],
        p_value_cutoff=0.05
    )

    if results:
        for db_name, df in results.items():
            print(f"\n📊 {db_name} Results (top 10):")
            print(df.head(10)[['Rank', 'Term Name', 'P-value', 'Adjusted P-value', 'Gene Count']])
    else:
        print("❌ No results obtained")
