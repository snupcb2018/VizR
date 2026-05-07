#!/usr/bin/env Rscript
#
# WGCNA Clustering for VizR
# Weighted Gene Co-expression Network Analysis
#
# Usage:
#   DEG-filtered:
#     Rscript run_wgcna.R --source-type deg --matrix <matrix.RData> --soft-power auto --output <dir>
#
#   Variance-filtered (recommended):
#     Rscript run_wgcna.R --source-type variance --tmm-matrix <genes.TMM.matrix> --top-n-genes <N> --soft-power auto --output <dir>
#
#   Full TMM:
#     Rscript run_wgcna.R --source-type tmm --tmm-matrix <genes.TMM.matrix> --soft-power auto --output <dir>
#

# Disable X11 for headless environment
options(bitmapType="cairo")
options(stringsAsFactors = FALSE)

# Load WGCNA library
library(WGCNA)

# Allow multi-threading
allowWGCNAThreads()

# Parse command line arguments
args <- commandArgs(trailingOnly = TRUE)

# Default values
source_type <- "variance"  # "deg" | "variance" | "tmm"
matrix_file <- NULL
tmm_matrix_file <- NULL
top_n_genes <- 5000
soft_power <- "auto"  # "auto" or numeric value
min_module_size <- 30
deep_split <- 2
merge_cut_height <- 0.25
output_dir <- "wgcna_results"

# Parse arguments
i <- 1
while (i <= length(args)) {
    if (args[i] == "--source-type") {
        source_type <- args[i + 1]
        i <- i + 2
    } else if (args[i] == "--matrix") {
        matrix_file <- args[i + 1]
        i <- i + 2
    } else if (args[i] == "--tmm-matrix") {
        tmm_matrix_file <- args[i + 1]
        i <- i + 2
    } else if (args[i] == "--top-n-genes") {
        top_n_genes <- as.integer(args[i + 1])
        i <- i + 2
    } else if (args[i] == "--soft-power") {
        if (args[i + 1] == "auto") {
            soft_power <- "auto"
        } else {
            soft_power <- as.numeric(args[i + 1])
        }
        i <- i + 2
    } else if (args[i] == "--min-module-size") {
        min_module_size <- as.integer(args[i + 1])
        i <- i + 2
    } else if (args[i] == "--deep-split") {
        deep_split <- as.integer(args[i + 1])
        i <- i + 2
    } else if (args[i] == "--merge-cut-height") {
        merge_cut_height <- as.numeric(args[i + 1])
        i <- i + 2
    } else if (args[i] == "--output") {
        output_dir <- args[i + 1]
        i <- i + 2
    } else {
        i <- i + 1
    }
}

# Validate required arguments based on source type
if (source_type == "deg") {
    if (is.null(matrix_file)) {
        stop("Error: --matrix is required for source-type 'deg'")
    }
    if (!file.exists(matrix_file)) {
        stop(paste("Error: Matrix file not found:", matrix_file))
    }
} else if (source_type %in% c("variance", "tmm")) {
    if (is.null(tmm_matrix_file)) {
        stop("Error: --tmm-matrix is required for source-type '", source_type, "'")
    }
    if (!file.exists(tmm_matrix_file)) {
        stop(paste("Error: TMM matrix file not found:", tmm_matrix_file))
    }
}

cat("🔬 [WGCNA] Starting WGCNA co-expression network analysis...\n")
cat("   ├─ Source type:", source_type, "\n")
cat("   ├─ Soft power:", soft_power, "\n")
cat("   ├─ Min module size:", min_module_size, "\n")
cat("   ├─ Deep split:", deep_split, "\n")
cat("   └─ Merge cut height:", merge_cut_height, "\n")

# Create output directory
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

# Load and process data based on source type
cat("📂 [WGCNA] Loading expression matrix...\n")

if (source_type == "deg") {
    # ========== Option 1: DEG-filtered ==========
    cat("   ├─ Method: DEG-filtered matrix\n")
    cat("   └─ File:", matrix_file, "\n")

    load(matrix_file)

    if (!exists("primary_data")) {
        stop("Error: 'primary_data' matrix not found in RData file")
    }

    expr_matrix <- primary_data
    cat("   └─ Loaded:", nrow(expr_matrix), "genes x", ncol(expr_matrix), "samples\n")

} else if (source_type == "variance") {
    # ========== Option 2: Variance-filtered (Recommended) ==========
    cat("   ├─ Method: Variance-filtered (recommended)\n")
    cat("   ├─ File:", tmm_matrix_file, "\n")
    cat("   └─ Top N genes:", top_n_genes, "\n")

    # Read TMM matrix
    tmm_mat <- read.table(tmm_matrix_file, header = TRUE, row.names = 1, sep = "\t", check.names = FALSE)
    cat("   ├─ Total genes:", nrow(tmm_mat), "\n")

    # Log2 transformation
    mat_log <- log2(tmm_mat + 1)

    # Filter low expression genes: keep genes with value > 1 in at least 40% of samples
    keep_expr <- rowMeans(mat_log > 1) >= 0.4
    mat_filtered <- mat_log[keep_expr, , drop = FALSE]
    cat("   ├─ After expression filter:", nrow(mat_filtered), "genes\n")

    # Select top N genes by MAD (Median Absolute Deviation)
    mad_vals <- apply(mat_filtered, 1, mad, constant = 1)
    N <- min(top_n_genes, nrow(mat_filtered))
    top_idx <- order(mad_vals, decreasing = TRUE)[seq_len(N)]
    expr_matrix <- mat_filtered[top_idx, , drop = FALSE]

    cat("   └─ Selected top", N, "highly variable genes (by MAD)\n")

} else if (source_type == "tmm") {
    # ========== Option 3: Full TMM (not recommended) ==========
    cat("   ├─ Method: Full TMM matrix (not recommended - high noise)\n")
    cat("   └─ File:", tmm_matrix_file, "\n")

    # Read TMM matrix
    tmm_mat <- read.table(tmm_matrix_file, header = TRUE, row.names = 1, sep = "\t", check.names = FALSE)
    cat("   ├─ Total genes:", nrow(tmm_mat), "\n")

    # Replace NA with 0
    tmm_mat[is.na(tmm_mat)] <- 0

    # Log2 transformation
    mat_log <- log2(tmm_mat + 1)

    # Remove genes with NA, NaN, or Inf values
    valid_genes <- complete.cases(mat_log) &
                   apply(mat_log, 1, function(x) all(is.finite(x)))
    mat_clean <- mat_log[valid_genes, , drop = FALSE]
    cat("   ├─ After removing NA/Inf:", nrow(mat_clean), "genes\n")

    # Filter low expression genes: keep genes with value > 1 in at least 40% of samples
    keep_expr <- rowMeans(mat_clean > 1) >= 0.4
    expr_matrix <- mat_clean[keep_expr, , drop = FALSE]
    cat("   ├─ After expression filter:", nrow(expr_matrix), "genes\n")

    cat("   ⚠️  Warning: Using all filtered genes - may cause memory issues\n")
    cat("   └─ Final:", nrow(expr_matrix), "genes x", ncol(expr_matrix), "samples\n")
}

# WGCNA requires samples as rows, genes as columns
cat("🔄 [WGCNA] Transposing matrix (samples as rows)...\n")
datExpr <- t(expr_matrix)
cat("   └─ Expression matrix:", nrow(datExpr), "samples x", ncol(datExpr), "genes\n")

# Check for excessive missing values
gsg <- goodSamplesGenes(datExpr, verbose = 3)
if (!gsg$allOK) {
    cat("⚠️  [WGCNA] Removing genes and samples with too many missing values...\n")
    if (sum(!gsg$goodGenes) > 0) {
        cat("   ├─ Removing", sum(!gsg$goodGenes), "genes\n")
    }
    if (sum(!gsg$goodSamples) > 0) {
        cat("   └─ Removing", sum(!gsg$goodSamples), "samples\n")
    }
    datExpr <- datExpr[gsg$goodSamples, gsg$goodGenes]
}

cat("   └─ Final data:", nrow(datExpr), "samples x", ncol(datExpr), "genes\n")

# Check for minimum sample size
if (nrow(datExpr) < 15) {
    cat("⚠️  [WGCNA] Warning: Sample size is", nrow(datExpr), "(minimum 15 recommended)\n")
    cat("   └─ Results may be unreliable with small sample sizes\n")
}

# Soft thresholding power selection
if (soft_power == "auto") {
    cat("⚙️  [WGCNA] Auto-selecting soft-thresholding power...\n")
    cat("   ├─ This may take several minutes...\n")

    powers <- c(1:10, seq(from = 12, to = 20, by = 2))
    sft <- pickSoftThreshold(datExpr, powerVector = powers, verbose = 5)

    # Select power based on scale-free topology fit
    if (is.finite(sft$powerEstimate)) {
        soft_power <- sft$powerEstimate
        cat("   ├─ Estimated power:", soft_power, "\n")
        cat("   └─ Scale-free R²:", round(sft$fitIndices[sft$fitIndices$Power == soft_power, "SFT.R.sq"], 3), "\n")
    } else {
        # Use default if estimation fails
        soft_power <- 6
        cat("   ⚠️  Power estimation failed. Using default power:", soft_power, "\n")
    }

    # Save power selection plot data
    power_file <- file.path(output_dir, "soft_threshold_power.tsv")
    write.table(sft$fitIndices, power_file, sep = "\t", quote = FALSE, row.names = FALSE)
    cat("   └─ Power selection data saved to:", power_file, "\n")
} else {
    cat("⚙️  [WGCNA] Using user-specified soft-thresholding power:", soft_power, "\n")
}

# Network construction and module detection
cat("🔄 [WGCNA] Constructing network and detecting modules...\n")
cat("   ├─ Soft power:", soft_power, "\n")
cat("   ├─ Min module size:", min_module_size, "\n")
cat("   ├─ Deep split:", deep_split, "\n")
cat("   └─ Merge cut height:", merge_cut_height, "\n")
cat("   ⏳ This may take 10-30 minutes depending on data size...\n")

net <- blockwiseModules(
    datExpr,
    power = soft_power,
    TOMType = "unsigned",
    minModuleSize = min_module_size,
    deepSplit = deep_split,
    mergeCutHeight = merge_cut_height,
    numericLabels = TRUE,
    pamRespectsDendro = FALSE,
    saveTOMs = FALSE,
    verbose = 3
)

cat("✅ [WGCNA] Network construction completed!\n")

# Convert numeric labels to colors
moduleLabels <- net$colors
moduleColors <- labels2colors(moduleLabels)
nModules <- length(unique(moduleColors))

cat("📊 [WGCNA] Detected", nModules, "modules\n")

# Count genes per module
module_counts <- table(moduleColors)
for (mod in names(sort(module_counts, decreasing = TRUE))) {
    cat(sprintf("   ├─ Module %s: %d genes\n", mod, module_counts[mod]))
}

# Calculate module eigengenes
cat("📈 [WGCNA] Calculating module eigengenes...\n")
MEs <- moduleEigengenes(datExpr, moduleColors)$eigengenes
MEs <- orderMEs(MEs)

# Save module assignments
cat("💾 [WGCNA] Saving module assignments...\n")
module_assignment <- data.frame(
    gene_id = colnames(datExpr),
    module = moduleColors,
    stringsAsFactors = FALSE
)
module_file <- file.path(output_dir, "module_colors.tsv")
write.table(module_assignment, module_file, sep = "\t", quote = FALSE, row.names = FALSE)
cat("   └─", module_file, "\n")

# Save module eigengenes
cat("💾 [WGCNA] Saving module eigengenes...\n")
ME_df <- data.frame(
    sample = rownames(datExpr),
    MEs,
    stringsAsFactors = FALSE
)
eigengene_file <- file.path(output_dir, "module_eigengenes.tsv")
write.table(ME_df, eigengene_file, sep = "\t", quote = FALSE, row.names = FALSE)
cat("   └─", eigengene_file, "\n")

# Calculate module membership (kME)
cat("📊 [WGCNA] Calculating module membership (kME)...\n")
geneModuleMembership <- as.data.frame(cor(datExpr, MEs, use = "p"))
MMPvalue <- as.data.frame(corPvalueStudent(as.matrix(geneModuleMembership), nrow(datExpr)))

# Save genes for each module
cat("🎯 [WGCNA] Extracting genes for each module...\n")

# Create modules directory
modules_dir <- file.path(output_dir, "modules")
dir.create(modules_dir, showWarnings = FALSE, recursive = TRUE)

for (module in unique(moduleColors)) {
    # Get genes in this module
    module_genes <- colnames(datExpr)[moduleColors == module]

    if (length(module_genes) > 0) {
        # Get module membership for this module
        module_column <- paste0("ME", module)

        if (module_column %in% colnames(geneModuleMembership)) {
            module_data <- data.frame(
                gene_id = module_genes,
                module_membership = geneModuleMembership[module_genes, module_column],
                stringsAsFactors = FALSE
            )

            # Add expression values
            expr_values <- t(datExpr[, module_genes, drop = FALSE])
            module_data <- cbind(module_data, expr_values)

            # Sort by module membership (descending)
            module_data <- module_data[order(-module_data$module_membership), ]

            # Save module file
            module_file <- file.path(modules_dir, paste0(module, ".tsv"))
            write.table(module_data, module_file, sep = "\t", quote = FALSE, row.names = FALSE)

            cat(sprintf("   ├─ Module %s: %d genes (file: %s.tsv)\n", module, length(module_genes), module))
        }
    }
}

# Save network statistics
cat("💾 [WGCNA] Saving network statistics...\n")
stats_file <- file.path(output_dir, "network_stats.txt")
sink(stats_file)
cat("WGCNA Network Statistics\n")
cat("========================\n\n")
cat("Input:\n")
cat("  - Source type:", source_type, "\n")
if (source_type == "deg") {
    cat("  - Matrix file:", matrix_file, "\n")
} else {
    cat("  - TMM matrix file:", tmm_matrix_file, "\n")
}
if (source_type == "variance") {
    cat("  - Top N genes (MAD):", top_n_genes, "\n")
}
cat("  - Samples:", nrow(datExpr), "\n")
cat("  - Genes:", ncol(datExpr), "\n\n")

cat("Parameters:\n")
cat("  - Soft-thresholding power:", soft_power, "\n")
cat("  - Min module size:", min_module_size, "\n")
cat("  - Deep split:", deep_split, "\n")
cat("  - Merge cut height:", merge_cut_height, "\n\n")

cat("Results:\n")
cat("  - Number of modules:", nModules, "\n\n")
cat("Module sizes:\n")
for (mod in names(sort(module_counts, decreasing = TRUE))) {
    cat(sprintf("  - %s: %d genes\n", mod, module_counts[mod]))
}
sink()
cat("   └─", stats_file, "\n")

# Save summary
cat("📝 [WGCNA] Saving analysis summary...\n")
summary_file <- file.path(output_dir, "summary.txt")
sink(summary_file)
cat("WGCNA Co-expression Network Analysis Summary\n")
cat("=============================================\n\n")
cat("Parameters:\n")
cat("  - Source type:", source_type, "\n")
cat("  - Soft power:", soft_power, "\n")
cat("  - Min module size:", min_module_size, "\n")
cat("  - Deep split:", deep_split, "\n")
cat("  - Merge cut height:", merge_cut_height, "\n")
if (source_type == "variance") {
    cat("  - Top N genes (MAD):", top_n_genes, "\n")
}
cat("\nInput:\n")
if (source_type == "deg") {
    cat("  - Matrix file:", matrix_file, "\n")
} else {
    cat("  - TMM matrix file:", tmm_matrix_file, "\n")
}
cat("  - Genes:", ncol(datExpr), "\n")
cat("  - Samples:", nrow(datExpr), "\n\n")
cat("Results:\n")
cat("  - Total modules:", nModules, "\n")
for (mod in names(sort(module_counts, decreasing = TRUE))) {
    cat(sprintf("  - Module %s: %d genes\n", mod, module_counts[mod]))
}
cat("\nOutput files:\n")
cat("  - Module assignments:", file.path(output_dir, "module_colors.tsv"), "\n")
cat("  - Module eigengenes:", eigengene_file, "\n")
cat("  - Network statistics:", stats_file, "\n")
cat("  - Module genes: modules/<color>.tsv\n")
if (soft_power == "auto") {
    cat("  - Power selection:", file.path(output_dir, "soft_threshold_power.tsv"), "\n")
}
sink()
cat("   └─", summary_file, "\n")

cat("\n✅ [WGCNA] Analysis complete! Results saved to:", output_dir, "\n")
cat("📊 Detected", nModules, "co-expression modules\n")
