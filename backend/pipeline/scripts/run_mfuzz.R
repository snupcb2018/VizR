#!/usr/bin/env Rscript
#
# Mfuzz Clustering for VizR
# Fuzzy c-means clustering for time-series gene expression data
#
# Usage:
#   DEG-filtered:
#     Rscript run_mfuzz.R --source-type deg --matrix <matrix.RData> --clusters <n> --output <dir>
#
#   Variance-filtered (recommended):
#     Rscript run_mfuzz.R --source-type variance --tmm-matrix <genes.TMM.matrix> --top-n-genes <N> --clusters <n> --output <dir>
#
#   Full TMM:
#     Rscript run_mfuzz.R --source-type tmm --tmm-matrix <genes.TMM.matrix> --clusters <n> --output <dir>
#

# Disable X11 for headless environment
options(bitmapType="cairo")

library(Mfuzz)
library(Biobase)

# Parse command line arguments
args <- commandArgs(trailingOnly = TRUE)

# Default values
source_type <- "deg"  # "deg" | "variance" | "tmm"
matrix_file <- NULL
tmm_matrix_file <- NULL
top_n_genes <- 8000
cluster_count <- 6
m_value <- NULL  # NULL means auto-estimate
min_membership <- 0.5
output_dir <- "mfuzz_results"

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
    } else if (args[i] == "--clusters") {
        cluster_count <- as.integer(args[i + 1])
        i <- i + 2
    } else if (args[i] == "--m") {
        m_value <- as.numeric(args[i + 1])
        i <- i + 2
    } else if (args[i] == "--min-membership") {
        min_membership <- as.numeric(args[i + 1])
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

cat("🔬 [MFUZZ] Starting Mfuzz clustering analysis...\n")
cat("   ├─ Source type:", source_type, "\n")
cat("   ├─ Cluster count:", cluster_count, "\n")
cat("   ├─ Min membership:", min_membership, "\n")

# Create output directory
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

# Load and process data based on source type
cat("📂 [MFUZZ] Loading expression matrix...\n")

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
    # ========== Option 2: Variance-filtered (ChatGPT recommendation) ==========
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

    cat("   ⚠️  Warning: Using all filtered genes - may still cause unstable clustering\n")
    cat("   └─ Final:", nrow(expr_matrix), "genes x", ncol(expr_matrix), "samples\n")
}

# Create ExpressionSet object for Mfuzz
cat("📦 [MFUZZ] Creating ExpressionSet object...\n")
eset <- new("ExpressionSet", exprs = as.matrix(expr_matrix))

# Standardize the data (Z-score normalization)
cat("📊 [MFUZZ] Standardizing expression data (Z-score)...\n")
eset.s <- standardise(eset)

# Estimate or use m parameter
if (is.null(m_value)) {
    cat("⚙️  [MFUZZ] Auto-estimating fuzzification parameter (m)...\n")
    m_value <- mestimate(eset.s)
    cat("   └─ Estimated m:", round(m_value, 3), "\n")
} else {
    cat("⚙️  [MFUZZ] Using user-specified m:", m_value, "\n")
}

# Run Mfuzz clustering
cat("🔄 [MFUZZ] Running fuzzy c-means clustering...\n")
cat("   ├─ Clusters:", cluster_count, "\n")
cat("   └─ Fuzzification (m):", round(m_value, 3), "\n")

cl <- mfuzz(eset.s, c = cluster_count, m = m_value)

cat("✅ [MFUZZ] Clustering completed!\n")

# Save cluster centroids
cat("💾 [MFUZZ] Saving cluster centroids...\n")
centroids_file <- file.path(output_dir, "cluster_centroids.tsv")
write.table(cl$centers, centroids_file, sep = "\t", quote = FALSE, row.names = TRUE, col.names = NA)
cat("   └─", centroids_file, "\n")

# Extract core genes for each cluster (membership > min_membership)
cat("🎯 [MFUZZ] Extracting core genes (membership >", min_membership, ")...\n")

for (i in 1:cluster_count) {
    # Get genes with membership > cutoff for this cluster
    cluster_genes <- names(which(cl$membership[, i] > min_membership))

    if (length(cluster_genes) > 0) {
        # Create cluster data frame with membership values and expression
        cluster_data <- data.frame(
            gene_id = cluster_genes,
            membership = cl$membership[cluster_genes, i],
            stringsAsFactors = FALSE
        )

        # Add expression values
        expr_values <- expr_matrix[cluster_genes, , drop = FALSE]
        cluster_data <- cbind(cluster_data, expr_values)

        # Sort by membership (descending)
        cluster_data <- cluster_data[order(-cluster_data$membership), ]

        # Save cluster file
        cluster_file <- file.path(output_dir, sprintf("cluster_%d.tsv", i))
        write.table(cluster_data, cluster_file, sep = "\t", quote = FALSE, row.names = FALSE)

        cat(sprintf("   ├─ Cluster %d: %d genes (file: cluster_%d.tsv)\n", i, length(cluster_genes), i))
    } else {
        cat(sprintf("   ├─ Cluster %d: 0 genes (membership cutoff too high)\n", i))
    }
}

# Save full membership matrix
cat("💾 [MFUZZ] Saving full membership matrix...\n")
membership_file <- file.path(output_dir, "membership_matrix.tsv")
write.table(cl$membership, membership_file, sep = "\t", quote = FALSE, row.names = TRUE, col.names = NA)
cat("   └─", membership_file, "\n")

# Generate cluster plots
cat("📊 [MFUZZ] Generating cluster plots...\n")
plot_file <- file.path(output_dir, "mfuzz_clusters.pdf")

# Use tryCatch to handle plotting errors gracefully
tryCatch({
    pdf(plot_file, width = 12, height = 8)
    mfuzz.plot(eset.s, cl = cl, mfrow = c(2, 3), time.labels = colnames(expr_matrix))
    dev.off()
    cat("   └─", plot_file, "\n")
}, error = function(e) {
    dev.off()  # Ensure device is closed
    cat("   ⚠️  Warning: Could not generate PDF plots (", e$message, ")\n")
    cat("   └─ Cluster data files saved successfully\n")
})

# Save summary
cat("📝 [MFUZZ] Saving analysis summary...\n")
summary_file <- file.path(output_dir, "summary.txt")
sink(summary_file)
cat("Mfuzz Clustering Analysis Summary\n")
cat("==================================\n\n")
cat("Parameters:\n")
cat("  - Source type:", source_type, "\n")
cat("  - Cluster count (c):", cluster_count, "\n")
cat("  - Fuzzification (m):", round(m_value, 3), "\n")
cat("  - Min membership cutoff:", min_membership, "\n")
if (source_type == "variance") {
    cat("  - Top N genes (MAD):", top_n_genes, "\n")
}
cat("\nInput:\n")
if (source_type == "deg") {
    cat("  - Matrix file:", matrix_file, "\n")
} else {
    cat("  - TMM matrix file:", tmm_matrix_file, "\n")
}
cat("  - Genes:", nrow(expr_matrix), "\n")
cat("  - Samples:", ncol(expr_matrix), "\n\n")
cat("Results:\n")
for (i in 1:cluster_count) {
    cluster_genes <- names(which(cl$membership[, i] > min_membership))
    cat(sprintf("  - Cluster %d: %d genes\n", i, length(cluster_genes)))
}
cat("\nOutput files:\n")
cat("  - Cluster centroids:", centroids_file, "\n")
cat("  - Membership matrix:", membership_file, "\n")
cat("  - Cluster plots:", plot_file, "\n")
for (i in 1:cluster_count) {
    cluster_file <- file.path(output_dir, sprintf("cluster_%d.tsv", i))
    if (file.exists(cluster_file)) {
        cat("  - Cluster", i, "genes:", cluster_file, "\n")
    }
}
sink()
cat("   └─", summary_file, "\n")

cat("\n✅ [MFUZZ] Analysis complete! Results saved to:", output_dir, "\n")
