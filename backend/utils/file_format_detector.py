"""
File Format Detector
Automatically detect FASTQ or FASTA format from file content
"""
import gzip
import logging
from pathlib import Path
from typing import Tuple, Optional

from backend.utils.files import is_gzip_file

logger = logging.getLogger(__name__)


def detect_file_format(file_path: str, max_lines: int = 100) -> Tuple[Optional[str], str]:
    """
    Detect if a file is FASTQ or FASTA format by examining content

    Args:
        file_path: Path to file
        max_lines: Maximum lines to read for detection

    Returns:
        Tuple of (format, error_message)
        - format: 'fastq', 'fasta', or None if cannot determine
        - error_message: Error message if detection fails
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return None, f"File not found: {file_path}"

    # Check if file is gzipped
    is_gzipped = is_gzip_file(str(file_path))
    logger.info(f"Detecting format for {file_path.name}, Gzipped: {is_gzipped}")

    try:
        # Open file (gzipped or plain text)
        if is_gzipped:
            file_handle = gzip.open(file_path, 'rt', encoding='utf-8')
        else:
            file_handle = open(file_path, 'r', encoding='utf-8')

        with file_handle as f:
            lines_read = 0
            first_char = None
            fastq_pattern_count = 0
            fasta_pattern_count = 0

            for line in f:
                line = line.strip()
                if not line:
                    continue

                lines_read += 1

                # Check first non-empty line
                if first_char is None:
                    first_char = line[0]
                    logger.info(f"First character: '{first_char}'")

                # Count FASTQ patterns (@ header, + separator)
                if line.startswith('@'):
                    fastq_pattern_count += 1
                elif line.startswith('+'):
                    fastq_pattern_count += 1

                # Count FASTA patterns (> header)
                if line.startswith('>'):
                    fasta_pattern_count += 1

                if lines_read >= max_lines:
                    break

        # Determine format based on patterns
        logger.info(f"Pattern counts - FASTQ: {fastq_pattern_count}, FASTA: {fasta_pattern_count}")

        if first_char == '@' and fastq_pattern_count >= 2:
            logger.info(f"Detected format: FASTQ")
            return 'fastq', ''
        elif first_char == '>' and fasta_pattern_count >= 1:
            logger.info(f"Detected format: FASTA")
            return 'fasta', ''
        else:
            logger.warning(f"Could not determine format for {file_path.name}")
            return None, f"Could not determine file format (not FASTQ or FASTA)"

    except (gzip.BadGzipFile, EOFError) as e:
        logger.error(f"Corrupted gzip file: {e}")
        return None, "Corrupted gzip file"

    except UnicodeDecodeError as e:
        logger.error(f"File encoding error: {e}")
        return None, "Invalid file encoding"

    except Exception as e:
        logger.error(f"Error detecting format: {e}")
        return None, f"Error reading file: {str(e)}"
