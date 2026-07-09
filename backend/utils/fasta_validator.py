"""
FASTA File Validator
Validates FASTA format files
"""
import gzip
import logging
from pathlib import Path
from typing import Tuple

from backend.utils.files import is_gzip_file

logger = logging.getLogger(__name__)


def validate_fasta_file(fasta_path: str, sample_size: int = 1000) -> Tuple[bool, str]:
    """
    Validate FASTA file format

    Args:
        fasta_path: Path to FASTA file (.fasta, .fa, or .gz versions)
        sample_size: Number of sequences to sample (default: 1000)

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if file is valid FASTA format
        - error_message: Error message if validation fails, empty string if valid
    """
    fasta_path = Path(fasta_path)

    if not fasta_path.exists():
        return False, f"FASTA file not found: {fasta_path}"

    # Determine if file is gzipped using magic bytes
    is_gzipped = is_gzip_file(str(fasta_path))
    logger.info(f"Validating FASTA file: {fasta_path.name}, Gzipped: {is_gzipped}")

    valid_nucleotides = set('ACGTNacgtn')
    sequences_sampled = 0
    current_sequence = []
    has_header = False
    line_num = 0

    try:
        # Open file (gzipped or plain text)
        if is_gzipped:
            file_handle = gzip.open(fasta_path, 'rt', encoding='utf-8')
        else:
            file_handle = open(fasta_path, 'r', encoding='utf-8')

        with file_handle as f:
            for line in f:
                line = line.rstrip('\n\r')
                line_num += 1

                # Skip empty lines
                if not line:
                    continue

                if line.startswith('>'):
                    # Header line
                    if current_sequence:
                        # Validate previous sequence
                        seq_str = ''.join(current_sequence)
                        if not seq_str:
                            logger.error(f"Empty sequence after header at line {line_num}")
                            return False, f"Invalid FASTA format: Empty sequence after header at line {line_num}"
                        if not all(c in valid_nucleotides for c in seq_str):
                            invalid_chars = set(seq_str) - valid_nucleotides
                            logger.error(f"Invalid sequence characters at line {line_num}: {invalid_chars}")
                            return False, f"Invalid sequence characters at line {line_num}: {invalid_chars}"

                        sequences_sampled += 1
                        current_sequence = []

                        if sequences_sampled >= sample_size:
                            logger.info(f"Sample size reached: {sequences_sampled} sequences validated")
                            break

                    has_header = True

                elif line.startswith(';'):
                    # Comment line, skip
                    continue

                else:
                    # Sequence line
                    if not has_header:
                        logger.error(f"Sequence found before header at line {line_num}")
                        return False, f"Invalid FASTA format: Sequence found before header at line {line_num}"

                    # Check for valid characters
                    if not all(c in valid_nucleotides or c.isspace() for c in line):
                        invalid_chars = set(line) - valid_nucleotides - {' ', '\t'}
                        logger.error(f"Invalid sequence characters at line {line_num}: {invalid_chars}")
                        return False, f"Invalid sequence characters at line {line_num}: {invalid_chars}"

                    # Remove whitespace and add to current sequence
                    current_sequence.append(line.replace(' ', '').replace('\t', ''))

        # Validate last sequence
        if current_sequence:
            seq_str = ''.join(current_sequence)
            if not seq_str:
                return False, f"Invalid FASTA format: Empty sequence at end of file"
            if not all(c in valid_nucleotides for c in seq_str):
                invalid_chars = set(seq_str) - valid_nucleotides
                return False, f"Invalid sequence characters in last sequence: {invalid_chars}"
            sequences_sampled += 1

        if sequences_sampled == 0:
            logger.error("No valid sequences found in FASTA file")
            return False, "Invalid FASTA format: No valid sequences found in file"

        logger.info(f"FASTA validation completed: {fasta_path.name}")
        logger.info(f"  Validated {sequences_sampled} sequences successfully")
        return True, ""

    except (gzip.BadGzipFile, EOFError) as e:
        logger.error(f"Corrupted gzip file: {e}")
        return False, "Corrupted gzip file. The file may be incomplete or damaged during upload."

    except UnicodeDecodeError as e:
        logger.error(f"File encoding error: {e}")
        return False, "Invalid file encoding. The file may not be a valid FASTA file or is corrupted."

    except Exception as e:
        logger.error(f"FASTA validation error: {e}")
        return False, f"Failed to validate FASTA file: {str(e)}"
