#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QC Analysis Prompts Module
AI prompts for FastQC result analysis and interpretation
"""

QC_ANALYSIS_PROMPT = """
You are a bioinformatics specialist focusing on sequencing data quality evaluation.
Please analyze the following quality control results and provide a detailed evaluation.

## Sample Information
Sample: {sample_name}
Group: {group_name}
Experiment Type: {experiment_type}
Total Sequences: {total_sequences}
Sequence Length: {sequence_length}
GC Content: {gc_content}%

## Quality Module Statistics
- Passed modules: {pass_count}/{total_modules}
- Attention needed: {warn_count}/{total_modules}
- Review required: {fail_count}/{total_modules}

Modules requiring review: {failed_modules}
Modules needing attention: {warned_modules}

## Quality Module Details
{module_details}

## Analysis Requirements
1. **Module-by-Module Analysis**: For each FastQC module, provide:
   - Status (pass/warn/fail) with quantitative details when available
   - Biological interpretation in experiment context
   - Specific implications for preprocessing decisions

2. **Preprocessing Decision Framework**: Based on module results, determine:
   - Is Trimmomatic/PRINSEQ quality trimming necessary? (provide Q-score thresholds)
   - Is adapter trimming required? (specify adapter contamination levels)
   - Should duplicates be removed? (consider experiment type)

3. **Quantitative Evidence**: Include specific metrics:
   - Quality scores (e.g., "Q≈34-35 across all positions")
   - Contamination levels (e.g., "adapter content <0.1%")
   - Sequence counts and GC percentages
   - Exact failure/warning reasons

4. **Expert Interpretation**: Explain biological context:
   - Why certain warnings are normal for RNA-seq (random hexamer bias, duplication)
   - Which thresholds indicate real quality issues vs. expected patterns
   - Impact on downstream alignment and quantification

5. **Specific Tool Recommendations**: Provide concrete next steps:
   - If trimming needed: exact Trimmomatic parameters (LEADING:X TRAILING:Y)
   - If no trimming: "바로 HISAT2/STAR 정렬 진행" with expected alignment rates
   - Pipeline-specific considerations (read length, library type)

## Important Context
- For RNA-seq: High duplication and sequence content bias are often acceptable
- For WGS: Low duplication and uniform content are important
- For ChIP-seq/ATAC-seq: Fragment size distribution is important
- Consider library preparation method impacts

## Response Format
You MUST respond with ONLY a valid JSON object. No explanations, no markdown, no additional text.

Required JSON structure:
{{
  "overall_assessment": "Brief quality summary (1-2 sentences maximum)",
  "confidence_score": 0.85,
  "experiment_type": "RNA-seq",
  "quality_evaluation": {{
    "usability": "excellent",
    "notes": ["note1", "note2"],
    "strengths": ["strength1"]
  }},
  "recommendations": {{
    "immediate_actions": ["action1"],
    "preprocessing": ["step1"],
    "downstream_considerations": ["consideration1"]
  }},
  "expected_outcomes": {{
    "alignment_rate": "85-95%",
    "sequence_quality": "Good",
    "coverage_uniformity": "Good"
  }},
  "evidence": {{
    "per_base_quality": "e.g., Average Q34.5 across all positions",
    "adapter_content": "e.g., Maximum 0.08% contamination",
    "duplication_level": "e.g., 54.8% would be removed by deduplication",
    "n_content": "e.g., Average 0.002%",
    "sequence_bias": "e.g., 5' bias in first 10bp"
  }},
  "decision_rationale": [
    "Quality Q34.5 > Q30 threshold → quality trimming not needed",
    "Adapter 0.08% < 0.1% threshold → adapter trimming not needed",
    "Duplication 54.8% expected for RNA-seq → keep duplicates"
  ],
  "uncertainties": [
    "Library preparation method not specified",
    "Species reference genome quality unknown"
  ]
}}

CRITICAL RULES:
1. Start response with {{ and end with }}
2. Use double quotes for all strings
3. confidence_score must be a number between 0.0 and 1.0
4. usability must be one of: "excellent", "good", "fair", "poor"
5. Maximum 5 items per array (provide comprehensive analysis)
6. Each string should be informative but concise (under 100 characters)
7. No trailing commas
8. No comments or explanations outside the JSON
9. Keep response under 3000 characters total for efficiency
10. ALWAYS cite specific numbers in evidence and decision_rationale
11. When data is missing or unclear, use "Unknown" or "Data not available"
12. decision_rationale must show: observed value → threshold → conclusion
13. Do NOT assume RNA-seq patterns are normal without checking library type
14. Include uncertainties when metadata is insufficient

Respond with complete valid JSON only:
"""

# Context-specific prompts for different experiment types
RNA_SEQ_CONTEXT = """
For RNA-seq analysis, consider these general RNA-seq characteristics:

**Common RNA-seq Patterns:**
- Per base sequence content WARN/FAIL:
  * 5' bias is common with random hexamer priming
  * 3' bias may occur with oligo-dT priming
  * Report observed bias patterns without assuming they are problematic

- Sequence duplication levels:
  * High duplication can be normal for RNA-seq due to highly expressed genes
  * Consider biological vs. technical duplicates
  * Removal depends on experimental design and goals

- GC content deviation:
  * Species-specific variations: Human ~41%, Mouse ~42%
  * Report observed vs expected for the species
  * Moderate deviations may be acceptable

**Quality Thresholds:**
- Per base quality: Compare actual Q scores to Q30 standard
- Adapter content: <0.1% negligible, >1% consider trimming
- N content: >2% may indicate quality issues
- Overrepresented sequences: >1% investigate source

**Decision Framework:**
- Always provide quantitative evidence with specific values
- Base recommendations on actual observed metrics
- Consider experiment-specific factors when available
- Provide clear rationale for preprocessing decisions

**Analysis Approach:**
- Focus on data-driven conclusions
- Avoid assumptions without supporting evidence
- Provide specific parameter recommendations when needed
"""

def get_experiment_context(experiment_type: str) -> str:
    """
    Get experiment-specific context for RNA-seq analysis
    VizR is specialized for RNA-seq, so always return RNA-seq context

    Args:
        experiment_type: Type of sequencing experiment (defaults to RNA-seq)

    Returns:
        RNA-seq specific context
    """
    # VizR is RNA-seq specialized platform
    return RNA_SEQ_CONTEXT

def format_module_details(parsed_data: dict) -> str:
    """
    Format module details with quantitative data for AI analysis

    Args:
        parsed_data: Parsed FastQC data

    Returns:
        Formatted module details string with specific metrics
    """
    details = []

    for module_name, module_data in parsed_data.items():
        status = module_data.get('status', 'unknown')
        details.append(f"- {module_name}: {status.upper()}")

        # Extract quantitative data for each module
        if module_name == 'Basic Statistics':
            # Include all basic statistics
            for row in module_data.get('data', []):
                if len(row) >= 2:
                    details.append(f"  - {row[0]}: {row[1]}")

        elif module_name == 'Per base sequence quality':
            # Include actual position-by-position quality data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data and headers:
                # Add headers
                header_str = "  - Headers: " + "\t".join(headers)
                details.append(header_str)

                # Add all position data
                details.append("  - Position-by-position quality data:")
                for row in data:
                    if len(row) >= 2 and row[0].isdigit():
                        # Format: Position	Mean	Median	LQ	UQ	10th	90th
                        position_data = "\t".join(row)
                        details.append(f"    {position_data}")

                # Also add summary statistics for quick reference
                try:
                    qualities = [float(row[1]) for row in data if len(row) > 1 and row[0].isdigit()]
                    if qualities:
                        avg_quality = sum(qualities) / len(qualities)
                        min_quality = min(qualities)
                        max_quality = max(qualities)
                        details.append(f"  - Summary: Average Q{avg_quality:.1f}, Range Q{min_quality:.1f}-Q{max_quality:.1f}")

                        # Check for quality drops at ends
                        if len(qualities) >= 10:
                            start_avg = sum(qualities[:5]) / 5
                            end_avg = sum(qualities[-5:]) / 5
                            quality_drop = start_avg - end_avg
                            if quality_drop > 2:
                                details.append(f"  - Quality drop at 3' end: {quality_drop:.1f}")
                except (ValueError, IndexError):
                    pass

        elif module_name == 'Per sequence quality scores':
            # Include actual quality score distribution data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data and headers:
                # Add headers
                header_str = "  - Headers: " + "\t".join(headers)
                details.append(header_str)

                # Add all quality score distribution data
                details.append("  - Quality score distribution:")
                for row in data:
                    if len(row) >= 2:
                        quality_data = "\t".join(row)
                        details.append(f"    {quality_data}")

                # Also add summary for quick reference
                try:
                    max_count = 0
                    peak_quality = 0
                    total_sequences = 0
                    for row in data:
                        if len(row) >= 2:
                            count = float(row[1])
                            quality = float(row[0])
                            total_sequences += count
                            if count > max_count:
                                max_count = count
                                peak_quality = quality
                    if peak_quality > 0:
                        peak_percent = (max_count / total_sequences * 100) if total_sequences > 0 else 0
                        details.append(f"  - Summary: Peak at Q{peak_quality:.0f} ({peak_percent:.1f}% of sequences)")
                except (ValueError, IndexError):
                    pass

        elif module_name == 'Per sequence GC content':
            # Include actual GC content distribution data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data and headers:
                # Add headers
                header_str = "  - Headers: " + "\t".join(headers)
                details.append(header_str)

                # Add GC content distribution data
                details.append("  - GC content distribution:")
                for row in data:
                    if len(row) >= 2:
                        gc_data = "\t".join(row)
                        details.append(f"    {gc_data}")

                # Also add summary statistics
                try:
                    gc_values = []
                    counts = []
                    for row in data:
                        if len(row) >= 2:
                            gc_percent = float(row[0])
                            count = float(row[1])
                            gc_values.append(gc_percent)
                            counts.append(count)

                    if gc_values and counts:
                        # Calculate weighted mean
                        total_count = sum(counts)
                        weighted_mean = sum(gc * count for gc, count in zip(gc_values, counts)) / total_count if total_count > 0 else 0
                        min_gc = min(gc_values)
                        max_gc = max(gc_values)
                        details.append(f"  - Summary: Mean GC {weighted_mean:.1f}%, Range {min_gc:.0f}%-{max_gc:.0f}%")

                        # Find peak GC content
                        max_count_idx = counts.index(max(counts))
                        peak_gc = gc_values[max_count_idx]
                        details.append(f"  - Peak at {peak_gc:.0f}% GC content")
                except (ValueError, IndexError):
                    pass

        elif module_name == 'Per base N content':
            # Include actual position-by-position N content data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data and headers:
                # Add headers
                header_str = "  - Headers: " + "\t".join(headers)
                details.append(header_str)

                # Add all position N content data
                details.append("  - Position-by-position N content (%):")
                for row in data:
                    if len(row) >= 2 and row[0].isdigit():
                        n_content_data = "\t".join(row)
                        details.append(f"    {n_content_data}")

                # Also add summary statistics
                try:
                    n_contents = [float(row[1]) for row in data if len(row) > 1 and row[0].isdigit()]
                    if n_contents:
                        avg_n = sum(n_contents) / len(n_contents)
                        max_n = max(n_contents)
                        high_n_positions = [i+1 for i, n in enumerate(n_contents) if n > 2.0]  # Positions with >2% N
                        details.append(f"  - Summary: Average {avg_n:.3f}%, Maximum {max_n:.3f}%")
                        if high_n_positions:
                            details.append(f"  - High N positions (>2%): {high_n_positions[:10]}")  # Show first 10
                except (ValueError, IndexError):
                    pass

        elif module_name == 'Sequence Duplication Levels':
            # Include actual sequence duplication data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data:
                # Show headers if available
                if headers:
                    header_str = "  - Headers: " + "\t".join(headers)
                    details.append(header_str)

                # Add duplication level data
                details.append("  - Sequence duplication levels:")

                # First, show the total deduplicated percentage (special case)
                total_dedup = None
                for row in data:
                    if len(row) >= 2 and 'Total Deduplicated Percentage' in str(row[0]):
                        total_dedup = float(row[1])
                        details.append(f"    Total Deduplicated Percentage: {total_dedup}%")
                        break

                # Then show all duplication level data
                for row in data:
                    if len(row) >= 3 and 'Total Deduplicated Percentage' not in str(row[0]):
                        # Format: Level	Percentage of deduplicated	Percentage of total
                        level_data = "\t".join(row)
                        details.append(f"    {level_data}")

                # Add summary
                if total_dedup is not None:
                    duplicate_percent = 100 - total_dedup
                    details.append(f"  - Summary: {duplicate_percent:.1f}% sequences removed by deduplication")

                    # Analyze duplication patterns
                    high_duplication_levels = []
                    for row in data:
                        if len(row) >= 3 and 'Total Deduplicated Percentage' not in str(row[0]):
                            try:
                                level = row[0]
                                percent_total = float(row[2])
                                if percent_total > 5.0:  # >5% is significant
                                    high_duplication_levels.append(f"{level}({percent_total:.1f}%)")
                            except (ValueError, IndexError):
                                pass

                    if high_duplication_levels:
                        details.append(f"  - High duplication levels (>5%): {', '.join(high_duplication_levels[:5])}")

        elif module_name == 'Overrepresented sequences':
            # List top overrepresented sequences
            data = module_data.get('data', [])
            if data and len(data) > 0:
                details.append(f"  - Number of overrepresented sequences: {len(data)}")
                # Show top 3 sequences
                for i, row in enumerate(data[:3]):
                    if len(row) >= 4:
                        seq = row[0][:30] + "..." if len(row[0]) > 30 else row[0]
                        count = row[1]
                        percent = row[2]
                        source = row[3] if row[3] != "No Hit" else "Unknown"
                        details.append(f"  - Seq{i+1}: {percent}% ({source})")

        elif module_name == 'Adapter Content':
            # Include actual position-by-position adapter content data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data and headers:
                # Add headers
                header_str = "  - Headers: " + "\t".join(headers)
                details.append(header_str)

                # Add all position-by-position adapter content data
                details.append("  - Position-by-position adapter content (%):")
                for row in data:
                    if len(row) >= 2 and row[0].isdigit():
                        # Format: Position	Adapter1	Adapter2	Adapter3	etc.
                        adapter_data = "\t".join(row)
                        details.append(f"    {adapter_data}")

                # Also add summary statistics
                try:
                    max_adapter = 0
                    adapter_names = headers[1:] if len(headers) > 1 else []
                    max_adapter_type = "Unknown"
                    max_position = 0
                    significant_positions = []

                    for row in data:
                        if len(row) >= 2 and row[0].isdigit():
                            position = int(row[0])
                            # Find maximum across all adapter types for this position
                            for i in range(1, len(row)):
                                try:
                                    adapter_val = float(row[i])
                                    if adapter_val > max_adapter:
                                        max_adapter = adapter_val
                                        max_adapter_type = adapter_names[i-1] if i-1 < len(adapter_names) else f"Adapter{i}"
                                        max_position = position
                                    # Track positions with significant adapter content
                                    if adapter_val > 0.1:  # >0.1% is noticeable
                                        significant_positions.append(f"pos{position}({adapter_val:.3f}%)")
                                except (ValueError, IndexError):
                                    pass

                    details.append(f"  - Summary: Maximum {max_adapter:.3f}% at position {max_position} ({max_adapter_type})")

                    # Categorize contamination level
                    if max_adapter < 0.1:
                        details.append(f"  - Assessment: Negligible contamination (<0.1%)")
                    elif max_adapter < 1:
                        details.append(f"  - Assessment: Low contamination (0.1%-1%)")
                    else:
                        details.append(f"  - Assessment: Significant contamination (>1%)")

                    # Show positions with noticeable adapter content
                    if significant_positions:
                        details.append(f"  - Significant positions (>0.1%): {', '.join(significant_positions[:10])}")  # Show first 10

                except (ValueError, IndexError):
                    pass

        elif module_name == 'Per base sequence content':
            # Include actual position-by-position base content data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data and headers:
                # Add headers
                header_str = "  - Headers: " + "\t".join(headers)
                details.append(header_str)

                # Add all position-by-position base content data
                details.append("  - Position-by-position base content (%):")
                for row in data:
                    if len(row) >= 5 and row[0].isdigit():
                        # Format: Position	G%	A%	T%	C%
                        base_content_data = "\t".join(row)
                        details.append(f"    {base_content_data}")

                # Also add summary for quick reference
                if data and status in ['warn', 'fail']:
                    biased_positions = 0
                    extreme_positions = []
                    for i, row in enumerate(data[:20]):  # Check first 20 positions
                        if len(row) >= 5:
                            try:
                                position = row[0]
                                g, a, t, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                                # Check if any base deviates more than 10% from 25%
                                deviations = [abs(base - 25) for base in [g, a, t, c]]
                                max_dev = max(deviations)
                                if max_dev > 10:
                                    biased_positions += 1
                                    if max_dev > 20:  # Extreme bias
                                        extreme_positions.append(f"pos{position}({max_dev:.1f}%)")
                            except (ValueError, IndexError):
                                pass
                    if biased_positions > 0:
                        details.append(f"  - Summary: {biased_positions}/20 positions show >10% bias from expected 25%")
                        if extreme_positions:
                            details.append(f"  - Extreme bias positions: {', '.join(extreme_positions[:5])}")  # Show top 5

        elif module_name == 'Sequence Length Distribution':
            # Include actual sequence length distribution data
            data = module_data.get('data', [])
            headers = module_data.get('headers', [])

            if data and headers:
                # Add headers
                header_str = "  - Headers: " + "\t".join(headers)
                details.append(header_str)

                # Add sequence length distribution data
                details.append("  - Sequence length distribution:")
                for row in data:
                    if len(row) >= 2:
                        length_data = "\t".join(row)
                        details.append(f"    {length_data}")

                # Also add summary statistics
                try:
                    lengths = []
                    counts = []
                    for row in data:
                        if len(row) >= 2:
                            length = row[0]
                            count = float(row[1])
                            counts.append(count)
                            if count > 0:
                                if '-' in str(length):
                                    # Handle range like "35-36"
                                    parts = str(length).split('-')
                                    avg_len = (int(parts[0]) + int(parts[1])) / 2
                                    lengths.append(avg_len)
                                else:
                                    lengths.append(int(length))

                    if lengths and counts:
                        total_sequences = sum(counts)
                        # Calculate weighted mean length
                        weighted_mean = sum(length * count for length, count in zip(lengths, counts)) / total_sequences if total_sequences > 0 else 0
                        details.append(f"  - Summary: Length range {min(lengths):.0f}-{max(lengths):.0f}bp, Mean {weighted_mean:.1f}bp")

                        # Find most common length
                        max_count_idx = counts.index(max(counts))
                        most_common_length = lengths[max_count_idx]
                        most_common_percent = (counts[max_count_idx] / total_sequences * 100) if total_sequences > 0 else 0
                        details.append(f"  - Most common length: {most_common_length:.0f}bp ({most_common_percent:.1f}% of sequences)")
                except (ValueError, IndexError):
                    pass

    return '\n'.join(details)

def build_analysis_prompt(
    parsed_data: dict,
    sample_metadata: dict,
    statistics: dict
) -> str:
    """
    Build complete analysis prompt with all data

    Args:
        parsed_data: Parsed FastQC modules
        sample_metadata: Sample information
        statistics: Module statistics

    Returns:
        Complete formatted prompt
    """
    # Extract basic statistics
    basic_stats = parsed_data.get('Basic Statistics', {})
    total_sequences = 'N/A'
    sequence_length = 'N/A'
    gc_content = 'N/A'

    for row in basic_stats.get('data', []):
        if len(row) >= 2:
            if row[0] == 'Total Sequences':
                total_sequences = row[1]
            elif row[0] == 'Sequence length':
                sequence_length = row[1]
            elif row[0] == '%GC':
                gc_content = row[1]

    # Format the prompt
    prompt = QC_ANALYSIS_PROMPT.format(
        sample_name=sample_metadata.get('sample_name', 'Unknown'),
        group_name=sample_metadata.get('group_name', 'Unknown'),
        experiment_type=sample_metadata.get('experiment_type', 'RNA-seq'),
        total_sequences=total_sequences,
        sequence_length=sequence_length,
        gc_content=gc_content,
        pass_count=statistics.get('pass_count', 0),
        warn_count=statistics.get('warn_count', 0),
        fail_count=statistics.get('fail_count', 0),
        total_modules=statistics.get('total_modules', 0),
        failed_modules=', '.join(statistics.get('failed_modules', [])) or 'None',
        warned_modules=', '.join(statistics.get('warned_modules', [])) or 'None',
        module_details=format_module_details(parsed_data)
    )

    # Add experiment-specific context
    experiment_context = get_experiment_context(
        sample_metadata.get('experiment_type', 'RNA-seq')
    )
    if experiment_context:
        prompt += f"\n\n## Experiment-Specific Considerations\n{experiment_context}"

    return prompt