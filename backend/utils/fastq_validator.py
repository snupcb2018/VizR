"""
FASTQ File Validator
Validates FASTQ files and detects read types (short-read vs long-read)
"""
import gzip
import logging
from pathlib import Path
from typing import Dict, Tuple

from backend.utils.files import is_gzip_file

logger = logging.getLogger(__name__)


def detect_read_type(fastq_path: str, sample_size: int = 10000) -> Dict[str, any]:
    """
    Detect read type (short-read vs long-read) by sampling FASTQ file
    Also validates FASTQ format integrity

    Args:
        fastq_path: Path to FASTQ file (.fastq or .fastq.gz)
        sample_size: Number of reads to sample (default: 10000)

    Returns:
        Dict with:
            - is_long_read: bool
            - avg_length: float
            - min_length: int
            - max_length: int
            - sampled_reads: int
            - std_dev: float
            - format_valid: bool
    """
    fastq_path = Path(fastq_path)

    if not fastq_path.exists():
        raise FileNotFoundError(f"FASTQ file not found: {fastq_path}")

    # Determine if file is gzipped using magic bytes (not extension)
    is_gzipped = is_gzip_file(str(fastq_path))
    logger.info(f"Starting FASTQ validation: {fastq_path.name}, Gzipped: {is_gzipped}, Sample size: {sample_size}")

    lengths = []
    reads_sampled = 0
    valid_nucleotides = set('ACGTNacgtn')

    try:
        # Open file (gzipped or plain text)
        if is_gzipped:
            file_handle = gzip.open(fastq_path, 'rt', encoding='utf-8')
        else:
            file_handle = open(fastq_path, 'r', encoding='utf-8')

        with file_handle as f:
            line_num = 0
            current_read = {'header': None, 'sequence': None, 'plus': None, 'quality': None}

            for line in f:
                line = line.rstrip('\n\r')
                line_num += 1
                position = (line_num - 1) % 4

                # FASTQ format: every 4 lines = 1 read
                # Line 1: @ header
                # Line 2: sequence
                # Line 3: + separator
                # Line 4: quality scores

                if position == 0:  # Header line
                    if not line.startswith('@'):
                        logger.error(f"Invalid header at line {line_num}: {line[:50]}")
                        raise ValueError(f"Invalid FASTQ format: Line {line_num} should start with '@' but got: {line[:50]}")
                    current_read['header'] = line

                elif position == 1:  # Sequence line
                    if not line:
                        logger.error(f"Empty sequence at line {line_num}")
                        raise ValueError(f"Invalid FASTQ format: Empty sequence at line {line_num}")
                    # Check if sequence contains only valid nucleotides
                    if not all(c in valid_nucleotides for c in line):
                        invalid_chars = set(line) - valid_nucleotides
                        logger.error(f"Invalid characters at line {line_num}: {invalid_chars}")
                        raise ValueError(f"Invalid sequence characters at line {line_num}: {invalid_chars}")
                    current_read['sequence'] = line
                    seq_length = len(line)
                    lengths.append(seq_length)

                elif position == 2:  # Plus line
                    if not line.startswith('+'):
                        logger.error(f"Invalid separator at line {line_num}: {line[:50]}")
                        raise ValueError(f"Invalid FASTQ format: Line {line_num} should start with '+' but got: {line[:50]}")
                    current_read['plus'] = line

                elif position == 3:  # Quality line
                    if not line:
                        logger.error(f"Empty quality line at line {line_num}")
                        raise ValueError(f"Invalid FASTQ format: Empty quality line at line {line_num}")
                    # Verify quality length matches sequence length
                    seq_len = len(current_read['sequence'])
                    qual_len = len(line)
                    if seq_len != qual_len:
                        logger.error(f"Quality length mismatch at line {line_num}: seq={seq_len}, qual={qual_len}")
                        raise ValueError(f"Invalid FASTQ format: Quality length ({qual_len}) doesn't match sequence length ({seq_len}) at line {line_num}")
                    current_read['quality'] = line
                    reads_sampled += 1

                    if reads_sampled >= sample_size:
                        logger.info(f"Sample size reached: {reads_sampled} reads validated")
                        break

        if not lengths:
            raise ValueError("No valid reads found in FASTQ file")

        # Calculate statistics
        avg_length = sum(lengths) / len(lengths)
        min_length = min(lengths)
        max_length = max(lengths)

        # Calculate standard deviation
        variance = sum((x - avg_length) ** 2 for x in lengths) / len(lengths)
        std_dev = variance ** 0.5

        # Determine if long-read based on average length
        # Short-read (Illumina): typically 75-300bp with low variance
        # Long-read (PacBio/Nanopore): typically >500bp with high variance
        SHORT_READ_MAX_LENGTH = 500  # bp

        is_long_read = avg_length > SHORT_READ_MAX_LENGTH

        result = {
            'is_long_read': is_long_read,
            'avg_length': round(avg_length, 2),
            'min_length': min_length,
            'max_length': max_length,
            'sampled_reads': reads_sampled,
            'std_dev': round(std_dev, 2),
            'read_type': 'long-read' if is_long_read else 'short-read'
        }

        logger.info(f"FASTQ validation completed: {fastq_path.name}")
        logger.info(f"  Result: {result['read_type']}, Avg: {result['avg_length']}bp, Range: {result['min_length']}-{result['max_length']}bp")
        logger.info(f"  Sampled: {result['sampled_reads']} reads, Std Dev: {result['std_dev']}bp")

        return result

    except Exception as e:
        logger.error(f"FASTQ validation failed for {fastq_path.name}: {type(e).__name__} - {e}")
        raise


def validate_fastq_file(fastq_path: str, sample_size: int = 10000) -> Tuple[bool, str]:
    """
    Validate FASTQ file format and check if it's short-read data

    Args:
        fastq_path: Path to FASTQ file
        sample_size: Number of reads to sample

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if file is valid short-read data
        - error_message: Error message if validation fails, empty string if valid
    """
    try:
        result = detect_read_type(fastq_path, sample_size)

        if result['is_long_read']:
            error_msg = (
                f"Long-read sequencing data detected! "
                f"Average read length: {result['avg_length']}bp (range: {result['min_length']}-{result['max_length']}bp). "
                f"VizR currently supports only short-read data (Illumina, typically <500bp)."
            )
            return False, error_msg

        return True, ""

    except ValueError as e:
        # Format validation errors (corrupted file, invalid format)
        logger.error(f"FASTQ format validation error: {e}")
        error_msg = str(e)
        if "Invalid FASTQ format" in error_msg:
            return False, f"Corrupted or invalid FASTQ file: {error_msg}"
        elif "Invalid sequence characters" in error_msg:
            return False, f"Invalid FASTQ file: {error_msg}"
        else:
            return False, f"Invalid FASTQ file: {error_msg}"

    except (gzip.BadGzipFile, EOFError) as e:
        # Corrupted gzip file
        logger.error(f"Corrupted gzip file: {e}")
        return False, "Corrupted gzip file. The file may be incomplete or damaged during upload."

    except UnicodeDecodeError as e:
        # Binary file or wrong encoding
        logger.error(f"File encoding error: {e}")
        return False, "Invalid file encoding. The file may not be a valid FASTQ file or is corrupted."

    except Exception as e:
        # Other unexpected errors
        logger.error(f"FASTQ validation error: {e}")
        return False, f"Failed to validate FASTQ file: {str(e)}"
