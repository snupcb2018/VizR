"""
KEGG Pathway Analysis using g:Profiler

Provides KEGG pathway enrichment analysis and URL generation for pathway visualization.
Uses the existing GProfilerAPI infrastructure for analysis.

KEGG URL Format: https://www.kegg.jp/kegg-bin/show_pathway?map={organism}{pathway_id}&multi_query={gene1}+red%0d{gene2}+red...
Example: https://www.kegg.jp/kegg-bin/show_pathway?map=ath00195&multi_query=AT1G01010+red%0dAT1G01020+red
"""

import pandas as pd
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from backend.pipeline.utils.go_enrichment import GProfilerAPI
from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')


# KEGG organism code mapping
KEGG_ORGANISM_MAP = {
    'arabidopsis': 'ath',
    'human': 'hsa',
    'mouse': 'mmu',
    'rat': 'rno',
}


def extract_pathway_id(term_id: str) -> str:
    """
    Extract KEGG pathway ID from term ID

    Args:
        term_id: KEGG term ID (e.g., "KEGG:00195" or "00195")

    Returns:
        Pathway ID without prefix (e.g., "00195")
    """
    if ':' in term_id:
        return term_id.split(':')[-1]
    return term_id


def generate_kegg_url(pathway_id: str, gene_ids: List[str], organism: str = 'ath') -> str:
    """
    Generate KEGG Pathway diagram URL with gene highlighting

    Args:
        pathway_id: KEGG Pathway ID (e.g., "00195" or "KEGG:00195")
        gene_ids: List of gene IDs to highlight (e.g., ["AT1G01010", "AT1G01020"])
        organism: KEGG organism code (default: 'ath' for Arabidopsis)

    Returns:
        KEGG website URL with highlighted genes

    Example:
        >>> generate_kegg_url("00195", ["AT1G01010", "AT1G01020"], "ath")
        'https://www.kegg.jp/kegg-bin/show_pathway?map=ath00195&multi_query=AT1G01010+red%0dAT1G01020+red'
    """
    # Extract clean pathway ID
    clean_pathway_id = extract_pathway_id(pathway_id)

    # Build pathway map parameter
    pathway_map = f"{organism}{clean_pathway_id}"

    # Build base URL with show_pathway CGI
    if gene_ids and len(gene_ids) > 0:
        # Create multi_query parameter: gene1+red%0dgene2+red%0d...
        # %0d is URL-encoded newline character
        gene_highlights = '%0d'.join([f"{gene_id}+red" for gene_id in gene_ids])
        return f"https://www.kegg.jp/kegg-bin/show_pathway?map={pathway_map}&multi_query={gene_highlights}"
    else:
        # No genes to highlight, just show the pathway
        return f"https://www.kegg.jp/pathway/{pathway_map}"


def analyze_kegg_pathways(
    genes: List[str],
    organism: str = 'arabidopsis',
    p_value_cutoff: float = 0.05,
    gene_symbol_map: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Run KEGG pathway enrichment analysis using gProfiler

    Args:
        genes: List of gene IDs (e.g., ["AT1G01010", "AT1G01020"])
        organism: Organism name (arabidopsis, human, mouse, rat)
        p_value_cutoff: Adjusted p-value cutoff for filtering
        gene_symbol_map: Optional mapping of gene IDs to symbols for display

    Returns:
        Dictionary with pathway results and KEGG URLs:
        {
            'success': True,
            'gene_count': 150,
            'pathways': [
                {
                    'Rank': 1,
                    'Term ID': 'KEGG:00195',
                    'Term Name': 'Photosynthesis',
                    'P-value': 0.00012,
                    'Adjusted P-value': 0.0024,
                    'Genes': 'AT1G01010;AT1G01020',
                    'Gene Count': 2,
                    'Term Size': 45,
                    'kegg_url': 'https://www.kegg.jp/pathway/ath00195+...',
                    'GeneSymbols': 'NAC001;ARV1'  # if gene_symbol_map provided
                },
                ...
            ]
        }
    """
    try:
        logger.info(f"🧬 [KEGG-PATHWAY] Starting KEGG pathway analysis for {len(genes)} genes")
        logger.info(f"📚 [KEGG-PATHWAY] Organism: {organism}")
        logger.info(f"🎯 [KEGG-PATHWAY] P-value cutoff: {p_value_cutoff}")

        # Get KEGG organism code
        kegg_org_code = KEGG_ORGANISM_MAP.get(organism.lower(), 'ath')
        logger.info(f"🔬 [KEGG-PATHWAY] KEGG organism code: {kegg_org_code}")

        # Run enrichment analysis with g:Profiler (KEGG only)
        api = GProfilerAPI(organism=organism, timeout=60)
        results = api.run_enrichment(
            genes=genes,
            databases=['KEGG'],
            description=f"KEGG Pathway Analysis",
            p_value_cutoff=p_value_cutoff
        )

        if not results or 'KEGG' not in results:
            logger.warning(f"⚠️ [KEGG-PATHWAY] No significant KEGG pathways found")
            return {
                'success': True,
                'gene_count': len(genes),
                'pathways': [],
                'message': 'No significant KEGG pathways found'
            }

        # Process KEGG results
        kegg_df = results['KEGG']
        pathway_results = []

        for idx, row in kegg_df.iterrows():
            # Extract gene list
            gene_list = row['Genes'].split(';') if row['Genes'] else []

            # Generate KEGG URL with highlighted genes
            pathway_id = row['Term ID']
            kegg_url = generate_kegg_url(pathway_id, gene_list, kegg_org_code)

            # Build pathway result
            pathway_data = {
                'Rank': row['Rank'],
                'Term ID': row['Term ID'],
                'Term Name': row['Term Name'],
                'P-value': row['P-value'],
                'Adjusted P-value': row['Adjusted P-value'],
                'Genes': row['Genes'],
                'Gene Count': row['Gene Count'],
                'Term Size': row['Term Size'],
                'kegg_url': kegg_url
            }

            # Add gene symbols if mapping provided
            if gene_symbol_map:
                gene_symbols = [
                    gene_symbol_map.get(gene_id.strip(), {}).get('symbol', gene_id.strip())
                    for gene_id in gene_list
                ]
                pathway_data['GeneSymbols'] = ';'.join(gene_symbols)

            pathway_results.append(pathway_data)

        logger.info(f"✅ [KEGG-PATHWAY] Analysis complete: {len(pathway_results)} enriched pathways")

        return {
            'success': True,
            'gene_count': len(genes),
            'pathways': pathway_results
        }

    except Exception as e:
        logger.error(f"❌ [KEGG-PATHWAY] Analysis failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e),
            'gene_count': len(genes),
            'pathways': []
        }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Test with Arabidopsis genes
    test_genes = [
        'AT1G01010', 'AT1G01020', 'AT1G01030', 'AT1G01040', 'AT1G01050',
        'AT1G01060', 'AT1G01070', 'AT1G01080', 'AT1G01090', 'AT1G01100'
    ]

    print("🧬 Testing KEGG Pathway Analysis with Arabidopsis genes...")
    print(f"📝 Genes: {', '.join(test_genes)}")

    result = analyze_kegg_pathways(
        genes=test_genes,
        organism='arabidopsis',
        p_value_cutoff=0.05
    )

    if result['success'] and result['pathways']:
        print(f"\n📊 KEGG Pathway Results ({len(result['pathways'])} pathways):")
        for pathway in result['pathways'][:10]:  # Show top 10
            print(f"\n  Rank {pathway['Rank']}: {pathway['Term Name']}")
            print(f"    Term ID: {pathway['Term ID']}")
            print(f"    P-value: {pathway['P-value']:.2e}")
            print(f"    Genes: {pathway['Gene Count']} genes")
            print(f"    KEGG URL: {pathway['kegg_url']}")
    else:
        print(f"❌ No pathways found or error occurred")
        if 'error' in result:
            print(f"   Error: {result['error']}")
