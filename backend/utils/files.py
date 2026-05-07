"""
File processing utilities for VizR pipeline.

This module contains utility functions for file operations including compression/decompression
and file management operations used across the VizR RNA-Seq analysis pipeline.
"""

import os
import time
import gzip
import shutil
import concurrent.futures
import logging


def is_gzip_file(file_path: str) -> bool:
    """
    파일의 magic bytes를 읽어서 실제로 gzip 파일인지 확인

    확장자에 의존하지 않고 파일 내용을 검사하여 진짜 gzip 파일인지 판단합니다.
    Gzip 파일은 항상 첫 2바이트가 0x1f 0x8b (gzip magic number)로 시작합니다.

    Args:
        file_path (str): 확인할 파일 경로

    Returns:
        bool: gzip 파일이면 True, 아니면 False

    Example:
        >>> is_gzip_file('/path/to/file.fastq.gz')  # 실제 gzip 파일
        True
        >>> is_gzip_file('/path/to/file.fastq')     # 비압축 파일
        False
        >>> is_gzip_file('/path/to/fake.gz')        # 확장자만 .gz (내용은 비압축)
        False
    """
    try:
        with open(file_path, 'rb') as f:
            # gzip 파일은 항상 0x1f 0x8b로 시작 (gzip magic number)
            magic_bytes = f.read(2)
            return magic_bytes == b'\x1f\x8b'
    except Exception:
        # 파일 읽기 실패 시 False 반환 (로그는 호출하는 쪽에서 처리)
        return False


def decompress_gzip_files(input_files, temp_dir, logger=None):
    """
    Decompress all input files in parallel using gzip module.
    
    Args:
        input_files (dict): Dictionary mapping file keys to compressed file paths
                          e.g., {'SE': '/path/to/file.fastq.gz'} or 
                                {'R1': '/path/to/R1.fastq.gz', 'R2': '/path/to/R2.fastq.gz'}
        temp_dir (str): Temporary directory path where decompressed files will be stored
        logger (logging.Logger, optional): Logger instance for detailed logging. 
                                         If None, uses default logger
    
    Returns:
        dict: Dictionary mapping file keys to decompressed file paths
              e.g., {'SE': '/temp/file.fastq'} or 
                    {'R1': '/temp/R1.fastq', 'R2': '/temp/R2.fastq'}
    
    Raises:
        Exception: If any file decompression fails
    
    Example:
        >>> input_files = {'R1': '/data/sample_R1.fastq.gz', 'R2': '/data/sample_R2.fastq.gz'}
        >>> temp_dir = '/tmp/prinseq_12345'
        >>> decompressed = decompress_input_files_parallel(input_files, temp_dir, logger)
        >>> print(decompressed)
        {'R1': '/tmp/prinseq_12345/sample_R1.fastq', 'R2': '/tmp/prinseq_12345/sample_R2.fastq'}
    """
    # Use provided logger or create a default one
    if logger is None:
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'INFO')
    
    # Create workers equal to file count (SE: 1, PE: 2)
    max_workers = len(input_files)
    logger.info(f"📦 [DECOMPRESS-{os.getpid()}] ═══════════════════════════════════════")
    logger.info(f"📦 [DECOMPRESS-{os.getpid()}] Starting parallel decompression")
    logger.info(f"📦 [DECOMPRESS-{os.getpid()}] ═══════════════════════════════════════")
    logger.info(f"🔄 [DECOMPRESS-{os.getpid()}] Worker configuration: {max_workers} workers (equal to file count)")
    
    # Log file information before decompression
    total_compressed_size = 0
    for key, gz_file in input_files.items():
        compressed_size = os.path.getsize(gz_file)
        total_compressed_size += compressed_size
        logger.info(f"📥 [DECOMPRESS-{os.getpid()}] {key}: {os.path.basename(gz_file)} ({compressed_size:,} bytes)")
    logger.info(f"📊 [DECOMPRESS-{os.getpid()}] Total compressed file size: {total_compressed_size:,} bytes")
    
    def decompress_single_file(key, gz_file):
        """Decompress single file (executed in thread)"""
        start_time = time.time()
        logger.info(f"🔧 [DECOMPRESS-{os.getpid()}] [{key}] Starting decompression: {os.path.basename(gz_file)}")
        
        try:
            # Decompressed filename (remove .gz extension)
            extracted_filename = os.path.basename(gz_file).replace('.gz', '')
            extracted_path = os.path.join(temp_dir, extracted_filename)
            
            logger.info(f"⚙️  [DECOMPRESS-{os.getpid()}] [{key}] Target path: {extracted_path}")
            
            # Decompress gz file
            with gzip.open(gz_file, 'rb') as gz_in:
                with open(extracted_path, 'wb') as file_out:
                    shutil.copyfileobj(gz_in, file_out)
            
            file_size = os.path.getsize(extracted_path)
            elapsed_time = time.time() - start_time
            compression_ratio = (os.path.getsize(gz_file) / file_size * 100) if file_size > 0 else 0
            
            logger.info(f"✅ [DECOMPRESS-{os.getpid()}] [{key}] Decompression completed!")
            logger.info(f"📤 [DECOMPRESS-{os.getpid()}] [{key}] Output: {extracted_filename} ({file_size:,} bytes)")
            logger.info(f"⏱️  [DECOMPRESS-{os.getpid()}] [{key}] Elapsed time: {elapsed_time:.2f}s")
            logger.info(f"📈 [DECOMPRESS-{os.getpid()}] [{key}] Compression ratio: {compression_ratio:.1f}%")
            
            return key, extracted_path
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"💥 [DECOMPRESS-{os.getpid()}] [{key}] Decompression failed!")
            logger.error(f"💥 [DECOMPRESS-{os.getpid()}] [{key}] Error: {e}")
            logger.error(f"💥 [DECOMPRESS-{os.getpid()}] [{key}] Elapsed time: {elapsed_time:.2f}s")
            raise Exception(f"Failed to extract {gz_file}: {e}")
    
    # Parallel execution
    logger.info(f"🚀 [DECOMPRESS-{os.getpid()}] Starting parallel decompression tasks...")
    decompressed_files = {}
    total_start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit decompression tasks for all files
        future_to_key = {
            executor.submit(decompress_single_file, key, gz_file): key 
            for key, gz_file in input_files.items()
        }
        
        logger.info(f"📋 [DECOMPRESS-{os.getpid()}] {len(future_to_key)} tasks submitted, waiting for completion...")
        
        # Collect results in completion order
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_key):
            key, file_path = future.result()
            decompressed_files[key] = file_path
            completed_count += 1
            logger.info(f"📌 [DECOMPRESS-{os.getpid()}] Progress: {completed_count}/{len(future_to_key)} completed")
    
    total_elapsed = time.time() - total_start_time
    total_decompressed_size = sum(os.path.getsize(path) for path in decompressed_files.values())
    
    logger.info(f"🎉 [DECOMPRESS-{os.getpid()}] All files decompressed successfully!")
    logger.info(f"📊 [DECOMPRESS-{os.getpid()}] Total decompressed size: {total_decompressed_size:,} bytes")
    logger.info(f"⏱️  [DECOMPRESS-{os.getpid()}] Total elapsed time: {total_elapsed:.2f}s")
    logger.info(f"🏎️  [DECOMPRESS-{os.getpid()}] Average processing speed: {total_decompressed_size / (1024*1024) / total_elapsed:.1f} MB/s")
    
    return decompressed_files


def cleanup_temp_files(file_paths, logger=None):
    """
    Clean up temporary files safely.
    
    Args:
        file_paths (dict or list): Dictionary or list of file paths to clean up
        logger (logging.Logger, optional): Logger instance for detailed logging
    
    Returns:
        tuple: (cleanup_count, cleanup_size) - Number of files cleaned and total size freed
    """
    if logger is None:
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'INFO')
    
    logger.info(f"🗑️  [CLEANUP-{os.getpid()}] Starting temporary file cleanup...")
    
    cleanup_count = 0
    cleanup_size = 0
    
    # Handle both dict and list inputs
    if isinstance(file_paths, dict):
        items = file_paths.items()
    else:
        items = enumerate(file_paths)
    
    for key, temp_file in items:
        try:
            if os.path.exists(temp_file):
                file_size = os.path.getsize(temp_file)
                os.remove(temp_file)
                cleanup_count += 1
                cleanup_size += file_size
                logger.info(f"   ✅ [{key}] Removed: {os.path.basename(temp_file)} ({file_size:,} bytes)")
            else:
                logger.warning(f"   ⚠️  [{key}] File not found: {os.path.basename(temp_file)}")
        except Exception as cleanup_error:
            logger.error(f"   ❌ [{key}] Failed to remove: {os.path.basename(temp_file)}")
            logger.error(f"       Error: {cleanup_error}")
    
    logger.info(f"📊 [CLEANUP-{os.getpid()}] Cleanup completed:")
    logger.info(f"   ├─ Files removed: {cleanup_count}")
    logger.info(f"   └─ Space freed: {cleanup_size:,} bytes")
    
    return cleanup_count, cleanup_size


def decompress_single_file(gz_file_path, logger=None, remove_original=True, stop_event=None):
    """
    Decompress a single gzip file.

    Args:
        gz_file_path (str): Path to the gzip file to decompress
        logger (logging.Logger, optional): Logger instance for detailed logging
        remove_original (bool): Whether to remove original .gz file after decompression
        stop_event (Event, optional): Event to check for stop signal during decompression

    Returns:
        str: Path to the decompressed file

    Raises:
        Exception: If decompression fails or stopped by user

    Example:
        >>> decompressed = decompress_single_file('/path/to/file.fastq.gz', logger)
        >>> print(decompressed)  # '/path/to/file.fastq'
    """
    if logger is None:
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'INFO')

    # Stop event 초기 상태 로깅
    if stop_event:
        logger.info(f"🔍 [DECOMPRESS-STOP-CHECK] Stop event provided - Initial state: {'SET' if stop_event.is_set() else 'NOT SET'} (id={id(stop_event)})")
    else:
        logger.warning(f"⚠️  [DECOMPRESS-STOP-CHECK] No stop event provided - User cancellation not available")

    if not gz_file_path.endswith('.gz'):
        logger.warning(f"⚠️  [DECOMPRESS] File is not gzipped: {os.path.basename(gz_file_path)}")
        return gz_file_path

    if not os.path.exists(gz_file_path):
        raise Exception(f"Source file does not exist: {gz_file_path}")

    # Decompressed filename (remove .gz extension)
    decompressed_path = gz_file_path[:-3]  # Remove '.gz'

    logger.info(f"📦 [DECOMPRESS] Decompressing: {os.path.basename(gz_file_path)}")

    start_time = time.time()
    chunk_count = 0
    decompressed_bytes = 0

    try:
        # Decompress gz file with stop event checking
        with gzip.open(gz_file_path, 'rb') as gz_in:
            with open(decompressed_path, 'wb') as file_out:
                # ✅ 청크 단위로 압축 해제하며 stop event 체크
                chunk_size = 1024 * 1024  # 1MB chunks
                while True:
                    chunk_count += 1

                    # Stop event 체크
                    if stop_event and stop_event.is_set():
                            logger.warning(f"🛑 [DECOMPRESS-STOP-DETECTED] Stop signal detected at chunk {chunk_count}")
                            logger.warning(f"🛑 [DECOMPRESS] Decompression stopped by user: {os.path.basename(gz_file_path)}")
                            logger.info(f"   📊 Processed {chunk_count} chunks ({decompressed_bytes:,} bytes) before stopping")
                            # 부분적으로 압축 해제된 파일 삭제
                            if os.path.exists(decompressed_path):
                                os.remove(decompressed_path)
                                logger.info(f"   🗑️  Removed partial file: {os.path.basename(decompressed_path)}")
                            raise Exception("Decompression stopped by user signal")

                    # 청크 읽기
                    chunk = gz_in.read(chunk_size)
                    if not chunk:
                        logger.debug(f"✅ [DECOMPRESS-COMPLETE] All chunks processed: {chunk_count} chunks, {decompressed_bytes:,} bytes")
                        break

                    # 청크 쓰기
                    file_out.write(chunk)
                    decompressed_bytes += len(chunk)

        # Verify decompression
        if os.path.exists(decompressed_path):
            compressed_size = os.path.getsize(gz_file_path)
            decompressed_size = os.path.getsize(decompressed_path)
            elapsed_time = time.time() - start_time

            # Remove original if requested
            if remove_original:
                os.remove(gz_file_path)
                logger.info(f"   ✅ Decompressed: {os.path.basename(decompressed_path)} ({decompressed_size:,} bytes)")
                logger.info(f"   🗑️  Removed: {os.path.basename(gz_file_path)}")
            else:
                logger.info(f"   ✅ Decompressed: {os.path.basename(decompressed_path)} (original kept)")

            logger.info(f"   ⏱️  Time: {elapsed_time:.2f}s")

            return decompressed_path
        else:
            raise Exception(f"Decompressed file was not created: {decompressed_path}")

    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"💥 [DECOMPRESS] Failed to decompress: {os.path.basename(gz_file_path)}")
        logger.error(f"       Error: {e}")
        logger.error(f"       Time: {elapsed_time:.2f}s")
        # Clean up partial decompression
        if os.path.exists(decompressed_path):
            os.remove(decompressed_path)
        raise


def compress_gzip_files(file_paths, logger=None, remove_original=True):
    """
    Compress files using gzip compression.

    Args:
        file_paths (list): List of file paths to compress
        logger (logging.Logger, optional): Logger instance for detailed logging
        remove_original (bool): Whether to remove original files after compression

    Returns:
        dict: Compression results with the following keys:
            - compressed_files: List of compressed file paths
            - total_original_size: Total size of original files
            - total_compressed_size: Total size after compression
            - total_space_saved: Total space saved (bytes)
            - compression_ratio: Overall compression ratio (percentage)
            - compression_time: Time taken for compression
            - files_processed: Number of files processed
            - files_skipped: Number of files skipped (already compressed)

    Example:
        >>> files = ['/path/to/file1.fastq', '/path/to/file2.fastq']
        >>> result = compress_files_gzip(files, logger, remove_original=True)
        >>> print(f"Space saved: {result['total_space_saved']:,} bytes")
    """
    if logger is None:
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'INFO')
    
    if not file_paths:
        logger.warning(f"🗜️  [COMPRESS-{os.getpid()}] No files provided for compression")
        return {
            'compressed_files': [],
            'total_original_size': 0,
            'total_compressed_size': 0,
            'total_space_saved': 0,
            'compression_ratio': 0,
            'compression_time': 0,
            'files_processed': 0,
            'files_skipped': 0
        }
    
    logger.info(f"🗜️  [COMPRESS-{os.getpid()}] ═══════════════════════════════════════")
    logger.info(f"🗜️  [COMPRESS-{os.getpid()}] Starting gzip compression")
    logger.info(f"🗜️  [COMPRESS-{os.getpid()}] ═══════════════════════════════════════")
    logger.info(f"📦 [COMPRESS-{os.getpid()}] Compressing {len(file_paths)} files...")
    
    compressed_files = []
    total_original_size = 0
    total_compressed_size = 0
    files_processed = 0
    files_skipped = 0
    compression_start_time = time.time()
    
    # Pre-process files to determine actual compression targets
    compression_targets = []
    for i, file_path in enumerate(file_paths, 1):
        if not os.path.exists(file_path):
            logger.warning(f"   ⚠️  [{i}/{len(file_paths)}] File not found: {os.path.basename(file_path)}")
            continue
        
        original_size = os.path.getsize(file_path)
        total_original_size += original_size
        
        # Skip if already compressed
        if file_path.endswith('.gz'):
            logger.info(f"   ⏭️  [{i}/{len(file_paths)}] Skipped: {os.path.basename(file_path)} (already compressed)")
            compressed_files.append(file_path)
            total_compressed_size += original_size
            files_skipped += 1
            continue
        
        compression_targets.append((i, file_path, original_size))
    
    if not compression_targets:
        logger.info(f"🗜️  [COMPRESS-{os.getpid()}] No files need compression")
    else:
        # Determine max workers for parallel compression
        max_workers = len(compression_targets)
        logger.info(f"🚀 [COMPRESS-{os.getpid()}] Using {max_workers} workers for parallel compression")
        
        def compress_single_file(target_info):
            """Compress single file (executed in thread)"""
            i, file_path, original_size = target_info
            
            try:
                # Define compressed file path
                compressed_path = file_path + '.gz'
                
                logger.info(f"   🔄 [{i}/{len(file_paths)}] Compressing: {os.path.basename(file_path)} ({original_size:,} bytes)")
                
                # Perform gzip compression
                with open(file_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Verify compressed file was created
                if os.path.exists(compressed_path):
                    compressed_size = os.path.getsize(compressed_path)
                    compression_ratio = (compressed_size / original_size * 100) if original_size > 0 else 0
                    space_saved = original_size - compressed_size
                    
                    # Remove original file if requested
                    if remove_original:
                        os.remove(file_path)
                        logger.info(f"   ✅ [{i}/{len(file_paths)}] Compressed: {os.path.basename(compressed_path)}")
                    else:
                        logger.info(f"   ✅ [{i}/{len(file_paths)}] Compressed: {os.path.basename(compressed_path)} (original kept)")
                    
                    logger.info(f"       📊 Original: {original_size:,} bytes → Compressed: {compressed_size:,} bytes")
                    logger.info(f"       📈 Compression: {compression_ratio:.1f}% | Space saved: {space_saved:,} bytes")
                    
                    return {'success': True, 'compressed_path': compressed_path, 'compressed_size': compressed_size}
                else:
                    logger.error(f"   ❌ [{i}/{len(file_paths)}] Compression failed: {os.path.basename(file_path)}")
                    return {'success': False, 'original_path': file_path, 'original_size': original_size}
                    
            except Exception as compress_error:
                logger.error(f"   💥 [{i}/{len(file_paths)}] Compression error: {os.path.basename(file_path)}")
                logger.error(f"       Error: {compress_error}")
                return {'success': False, 'original_path': file_path, 'original_size': original_size}
        
        # Parallel compression execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit compression tasks
            future_to_target = {
                executor.submit(compress_single_file, target): target 
                for target in compression_targets
            }
            
            logger.info(f"📋 [COMPRESS-{os.getpid()}] {len(future_to_target)} compression tasks submitted")
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_target):
                result = future.result()
                if result['success']:
                    compressed_files.append(result['compressed_path'])
                    total_compressed_size += result['compressed_size']
                    files_processed += 1
                else:
                    compressed_files.append(result['original_path'])
                    total_compressed_size += result['original_size']
    
    # Calculate final statistics
    compression_time = time.time() - compression_start_time
    total_space_saved = total_original_size - total_compressed_size
    overall_compression_ratio = (total_compressed_size / total_original_size * 100) if total_original_size > 0 else 0
    
    # Log summary
    logger.info(f"")
    logger.info(f"📊 [COMPRESS-{os.getpid()}] Compression summary:")
    logger.info(f"   ├─ Files provided: {len(file_paths)}")
    logger.info(f"   ├─ Files processed: {files_processed}")
    logger.info(f"   ├─ Files skipped: {files_skipped}")
    logger.info(f"   ├─ Original size: {total_original_size:,} bytes")
    logger.info(f"   ├─ Compressed size: {total_compressed_size:,} bytes")
    logger.info(f"   ├─ Space saved: {total_space_saved:,} bytes ({total_space_saved/1024/1024:.1f} MB)")
    logger.info(f"   ├─ Overall compression: {overall_compression_ratio:.1f}%")
    logger.info(f"   └─ Compression time: {compression_time:.2f}s")
    
    return {
        'compressed_files': compressed_files,
        'total_original_size': total_original_size,
        'total_compressed_size': total_compressed_size,
        'total_space_saved': total_space_saved,
        'compression_ratio': overall_compression_ratio,
        'compression_time': compression_time,
        'files_processed': files_processed,
        'files_skipped': files_skipped
    }


def ensure_decompressed_files(file_paths, logger=None):
    """
    Ensure input files are decompressed and ready for processing.

    Automatically detects and decompresses .gz files when needed:
    1. If .fastq exists → use it directly
    2. If only .fastq.gz exists → decompress automatically
    3. If neither exists → raise FileNotFoundError

    This function is called by each pipeline step (qc, clean, alignment) to ensure
    input files are available in uncompressed format, regardless of whether the user
    manually deleted .fastq files after a previous pipeline run.

    Args:
        file_paths: Can be:
                   - str: Single file path
                   - dict: {'R1': path, 'R2': path} or {'SE': path}
                   - list: [path1, path2, ...]
        logger (logging.Logger, optional): Logger instance for detailed logging

    Returns:
        Decompressed file paths in the same format as input:
        - str → str
        - dict → dict
        - list → list

    Raises:
        FileNotFoundError: If neither .fastq nor .fastq.gz exists

    Example:
        >>> # Single file
        >>> path = ensure_decompressed_files('/data/sample.fastq')

        >>> # Paired-end files
        >>> files = ensure_decompressed_files({'R1': '/data/R1.fastq', 'R2': '/data/R2.fastq'})

        >>> # Automatically decompresses if only .gz exists
        >>> path = ensure_decompressed_files('/data/sample.fastq')  # finds sample.fastq.gz and decompresses
    """
    if logger is None:
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'INFO')

    def ensure_single_file(file_path):
        """Ensure a single file is decompressed"""
        # If file ends with .gz, it's already compressed - just return it
        if file_path.endswith('.gz'):
            logger.debug(f"📦 [ENSURE-DECOMPRESS] File is compressed: {os.path.basename(file_path)}")
            return file_path

        # Check if uncompressed file exists
        if os.path.exists(file_path):
            logger.debug(f"✅ [ENSURE-DECOMPRESS] Uncompressed file exists: {os.path.basename(file_path)}")
            return file_path

        # Check if compressed version exists
        gz_file_path = file_path + '.gz'
        if os.path.exists(gz_file_path):
            logger.info(f"📦 [ENSURE-DECOMPRESS] Found compressed file, decompressing: {os.path.basename(gz_file_path)}")

            # Decompress (remove_original=False to keep .gz file)
            decompressed_path = decompress_single_file(gz_file_path, logger, remove_original=False)
            logger.info(f"   ✅ Decompressed: {os.path.basename(decompressed_path)}")
            return decompressed_path

        # Neither file exists
        raise FileNotFoundError(
            f"Input file not found: {file_path}\n"
            f"Also checked: {gz_file_path}\n"
            f"Please ensure the file exists in either compressed or uncompressed format."
        )

    # Handle different input types
    if isinstance(file_paths, str):
        # Single file path
        return ensure_single_file(file_paths)

    elif isinstance(file_paths, dict):
        # Dictionary of file paths (e.g., {'R1': path1, 'R2': path2})
        logger.info(f"📂 [ENSURE-DECOMPRESS] Checking {len(file_paths)} input files...")
        result = {}
        for key, path in file_paths.items():
            result[key] = ensure_single_file(path)
        return result

    elif isinstance(file_paths, list):
        # List of file paths
        logger.info(f"📂 [ENSURE-DECOMPRESS] Checking {len(file_paths)} input files...")
        return [ensure_single_file(path) for path in file_paths]

    else:
        raise TypeError(f"Unsupported file_paths type: {type(file_paths)}")


def cleanup_uncompressed_raw_data(raw_data_dir, logger=None):
    """
    Clean up uncompressed .fastq files in the raw data directory after pipeline completion.

    For each .fastq file found:
    - If .fastq.gz exists: Original was compressed, delete .fastq only
    - If .fastq.gz does NOT exist: Original was uncompressed, compress to .gz then delete .fastq

    This prevents data loss when users upload uncompressed FASTQ files directly.

    Args:
        raw_data_dir (str): Path to the raw data directory containing FASTQ files
        logger (logging.Logger, optional): Logger instance for detailed logging

    Returns:
        dict: Cleanup results with files_deleted, files_compressed, space_freed, and cleanup_time

    Example:
        >>> result = cleanup_uncompressed_raw_data('/data2/vizr/users/hjung/workbench/test5/quanti/raw')
        >>> if result:
        >>>     print(f"Deleted {result['files_deleted']} files")
        >>>     print(f"Compressed {result['files_compressed']} files")
        >>>     print(f"Space freed: {result['space_freed']:,} bytes")
    """
    import time

    if logger is None:
        from backend.utils.logger import setup_module_logger
        logger = setup_module_logger(__name__, 'INFO')

    if not os.path.exists(raw_data_dir):
        logger.warning(f"⚠️  [RAW-CLEANUP] Raw data directory not found: {raw_data_dir}")
        return {}

    logger.info(f"🧹 [RAW-CLEANUP] ═══════════════════════════════════════")
    logger.info(f"🧹 [RAW-CLEANUP] Cleaning up uncompressed raw data files")
    logger.info(f"🧹 [RAW-CLEANUP] ═══════════════════════════════════════")
    logger.info(f"📂 [RAW-CLEANUP] Scanning directory: {raw_data_dir}")

    start_time = time.time()

    # Find all .fastq files (not .fastq.gz)
    fastq_files = []
    for root, dirs, files in os.walk(raw_data_dir):
        for filename in files:
            if filename.endswith('.fastq') and not filename.endswith('.fastq.gz'):
                file_path = os.path.join(root, filename)
                fastq_files.append(file_path)
                logger.info(f"   ✓ Found: {filename}")

    if not fastq_files:
        logger.info(f"📭 [RAW-CLEANUP] No uncompressed .fastq files found")
        return {}

    logger.info(f"📊 [RAW-CLEANUP] Found {len(fastq_files)} uncompressed FASTQ files to delete")

    # Process uncompressed files: delete if .gz exists, compress if not
    files_deleted = 0
    files_compressed = 0
    space_freed = 0

    for file_path in fastq_files:
        try:
            file_size = os.path.getsize(file_path)
            gz_file_path = file_path + '.gz'

            if os.path.exists(gz_file_path):
                # Case 1: Original was compressed (.gz exists)
                # Just delete the uncompressed file
                os.remove(file_path)
                files_deleted += 1
                space_freed += file_size
                logger.debug(f"   🗑️  Deleted: {os.path.basename(file_path)} (compressed version exists)")
            else:
                # Case 2: Original was uncompressed (.gz doesn't exist)
                # Compress first, then delete uncompressed
                logger.info(f"   🗜️  Compressing: {os.path.basename(file_path)} (no compressed version found)")

                # Compress the file
                with open(file_path, 'rb') as f_in:
                    with gzip.open(gz_file_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)

                compressed_size = os.path.getsize(gz_file_path)
                logger.info(f"       Compressed: {file_size:,} → {compressed_size:,} bytes")

                # Delete the uncompressed file
                os.remove(file_path)
                files_deleted += 1
                files_compressed += 1
                space_freed += file_size - compressed_size  # Net space freed
                logger.debug(f"   ✅ Compressed and deleted: {os.path.basename(file_path)}")

        except Exception as e:
            logger.error(f"   ❌ Failed to process {file_path}: {e}")

    cleanup_time = time.time() - start_time

    logger.info(f"🎉 [RAW-CLEANUP] Raw data cleanup completed!")
    logger.info(f"   ├─ Files deleted: {files_deleted}")
    logger.info(f"   ├─ Files compressed: {files_compressed}")
    logger.info(f"   ├─ Space freed: {space_freed:,} bytes ({space_freed/1024/1024:.1f} MB)")
    logger.info(f"   └─ Cleanup time: {cleanup_time:.2f}s")
    logger.info(f"🧹 [RAW-CLEANUP] ═══════════════════════════════════════")

    return {
        'files_deleted': files_deleted,
        'files_compressed': files_compressed,
        'space_freed': space_freed,
        'cleanup_time': cleanup_time
    }