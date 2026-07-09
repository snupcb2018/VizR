"""
VizR NCBI Blueprint
"""
from flask import Blueprint, request, jsonify, session
import logging

from backend.utils.logger import setup_module_logger
logger = setup_module_logger(__name__, 'INFO')

# Create blueprint
ncbi_bp = Blueprint('ncbi', __name__, url_prefix='/api/ncbi')


def require_auth(f):
    """Decorator to require authentication for routes."""
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@ncbi_bp.route('/search/<bioproject_id>', methods=['GET'])
@require_auth
def search_ncbi_bioproject(bioproject_id):
    """NCBI bioproject 메타데이터 검색"""
    try:
        import csv
        import io
        import requests
        
        logger.info(f"Searching NCBI for bioproject: {bioproject_id}")
        
        # Validate bioproject ID format (should start with PRJNA)
        if not bioproject_id.startswith('PRJNA'):
            return jsonify({'error': 'BioProject ID must start with PRJNA (e.g., PRJNA252931)'}), 400
        
        # Use Python requests to call NCBI E-utilities API
        try:
            import requests
            
            # Step 1: Search for bioproject using esearch API
            search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            search_params = {
                'db': 'sra',
                'term': bioproject_id,
                'retmode': 'json',
                'retmax': 1000  # Maximum number of results
            }
            
            logger.info(f"Searching NCBI for bioproject: {bioproject_id}")
            search_response = requests.get(search_url, params=search_params, timeout=30)
            search_response.raise_for_status()
            
            search_data = search_response.json()
            id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
            if not id_list:
                return jsonify({
                    'error': 'No data found for this BioProject ID',
                    'bioproject_id': bioproject_id
                }), 404
            
            logger.info(f"Found {len(id_list)} SRA entries for {bioproject_id}")
            
            # Step 2: Fetch runinfo data using efetch API
            fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            fetch_params = {
                'db': 'sra',
                'id': ','.join(id_list),
                'retmode': 'text',
                'rettype': 'runinfo'
            }
            
            logger.info(f"Fetching runinfo data for {len(id_list)} entries")
            fetch_response = requests.get(fetch_url, params=fetch_params, timeout=60)
            fetch_response.raise_for_status()
            
            csv_data = fetch_response.text.strip()
            
            if not csv_data:
                return jsonify({
                    'error': 'No runinfo data available for this BioProject',
                    'bioproject_id': bioproject_id
                }), 404
                
        except requests.RequestException as e:
            logger.error(f"NCBI API request failed: {e}")
            return jsonify({
                'error': f'Failed to connect to NCBI API: {str(e)}',
                'bioproject_id': bioproject_id
            }), 500
        except requests.Timeout:
            logger.error(f"NCBI API request timed out for {bioproject_id}")
            return jsonify({
                'error': 'NCBI API request timed out. Please try again.',
                'bioproject_id': bioproject_id
            }), 408
        
        # Parse CSV data and classify read types
        try:
            reader = csv.DictReader(io.StringIO(csv_data))
            files = []

            # Long-read platform detection
            LONG_READ_PLATFORMS = ['OXFORD_NANOPORE', 'PACBIO_SMRT', 'PACBIO']

            for row in reader:
                # Filter: Only RNA-Seq data
                library_strategy = row.get('LibraryStrategy', '')
                if library_strategy != 'RNA-Seq':
                    logger.debug(f"Skipping non-RNA-Seq file: {row.get('Run', '')} (LibraryStrategy: {library_strategy})")
                    continue

                platform = row.get('Platform', '')
                avg_length_str = row.get('avgLength', '0')

                # Calculate average length from bases/spots if avgLength not available
                try:
                    avg_length = float(avg_length_str) if avg_length_str else 0

                    # If avgLength is 0, try to calculate from bases/spots
                    if avg_length == 0:
                        bases = float(row.get('bases', '0'))
                        spots = float(row.get('spots', '0'))
                        if spots > 0:
                            avg_length = bases / spots
                except (ValueError, ZeroDivisionError):
                    avg_length = 0

                # Classify read type based on platform and avgLength
                # SHORT: <600bp or standard Illumina
                # BORDERLINE: 600-1000bp (warning zone)
                # LONG: >1000bp or known long-read platforms
                read_class = 'SHORT'
                if platform in LONG_READ_PLATFORMS or avg_length >= 1000:
                    read_class = 'LONG'
                elif 600 <= avg_length < 1000:
                    read_class = 'BORDERLINE'

                files.append({
                    'run': row.get('Run', ''),
                    'library_layout': row.get('LibraryLayout', ''),
                    'library_strategy': library_strategy,
                    'sample_name': row.get('SampleName', ''),
                    'size_mb': row.get('size_MB', '0'),
                    'bases': row.get('bases', '0'),
                    'spots': row.get('spots', '0'),
                    'scientific_name': row.get('ScientificName', ''),
                    'platform': platform,
                    'model': row.get('Model', ''),
                    'avg_length': round(avg_length, 2) if avg_length > 0 else 0,
                    'read_class': read_class
                })
            
            if not files:
                return jsonify({
                    'error': 'No RNA-Seq files found in this BioProject',
                    'bioproject_id': bioproject_id
                }), 404

            # Generate validation summary
            long_read_files = [f for f in files if f['read_class'] == 'LONG']
            borderline_files = [f for f in files if f['read_class'] == 'BORDERLINE']
            short_read_files = [f for f in files if f['read_class'] == 'SHORT']

            validation_summary = {
                'total_files': len(files),
                'short_read_count': len(short_read_files),
                'borderline_count': len(borderline_files),
                'long_read_count': len(long_read_files),
                'has_long_reads': len(long_read_files) > 0,
                'has_borderline': len(borderline_files) > 0,
                'all_compatible': len(long_read_files) == 0
            }

            logger.info(f"Found {len(files)} files for bioproject {bioproject_id}: "
                       f"{len(short_read_files)} short-read, "
                       f"{len(borderline_files)} borderline, "
                       f"{len(long_read_files)} long-read")

            return jsonify({
                'success': True,
                'bioproject_id': bioproject_id,
                'files': files,
                'total_files': len(files),
                'validation': validation_summary,
                'message': f'Found {len(files)} files'
            })
            
        except Exception as csv_error:
            logger.error(f"CSV parsing error: {csv_error}")
            return jsonify({
                'error': 'Failed to parse NCBI response data',
                'bioproject_id': bioproject_id
            }), 500
            
    except Exception as e:
        logger.error(f"NCBI search error for {bioproject_id}: {e}")
        return jsonify({
            'error': 'Internal server error during NCBI search',
            'bioproject_id': bioproject_id
        }), 500