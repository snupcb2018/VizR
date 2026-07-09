# VizR

VizR is a web-based RNA-seq analysis platform that supports the workflow from raw data acquisition to interactive downstream interpretation within a single environment. The platform combines upstream pipeline execution with a browser-based interface for result exploration, visualization, and gene set analysis.

This public repository provides the distribution files for running VizR through a Windows installer, a prebuilt Docker image, or a source-based deployment.

## 1. Project Overview

VizR is designed for RNA-seq analysis workflows that require both automated execution and interactive interpretation. The platform integrates raw data input, quality control, sequence cleaning, alignment, quantification, differential expression analysis, PCA, clustering, heatmap rendering, Venn-based set comparison, and downstream enrichment analysis in one web application.

The repository includes:

- Backend source code for pipeline control and analysis services
- Frontend source code for the web interface
- Deployment scripts for Docker-based execution
- Windows launcher and installer source files
- English and Korean user manuals

## 2. Key Features

- Workbench-based project organization
- Multiple input methods: local upload, NCBI BioProject retrieval, and server-resident files
- Automated upstream RNA-seq processing pipeline
- Interactive counts, DEG, PCA, clustering, heatmap, and Venn interfaces
- Gene set enrichment analysis workflows integrated into the platform
- Prebuilt Docker image support for simplified deployment
- Windows launcher and installer workflow for local users

## 3. Installation Options

VizR can be used through one of the following installation paths.

### Option 1. Windows Installer

Use the packaged Windows installer if you want the simplest local installation path on Windows.

Windows installer download:

- [GitHub Releases](https://github.com/snupcb2018/VizR/releases)

This installer configures the Windows launcher workflow for VizR and starts the platform through Docker Desktop.

This path is appropriate when:

- You are running Windows
- You want to install VizR without building it manually
- You want a launcher-based workflow
- You prefer not to build the application manually

### Option 2. Prebuilt Docker Image

Use the prebuilt Docker image when you want to run VizR without building the image from source.

Current public image:

- `hjung200x/vizr:latest`

This path is appropriate when:

- Docker is already available
- You want the fastest deployment path
- You are running VizR on a workstation or server environment

### Option 3. Build From Source

Use the source build path when you need to inspect, modify, or rebuild the application image yourself.

This path is appropriate when:

- You want to customize VizR
- You need to inspect the codebase directly
- You want to rebuild the Docker image locally

## 4. Quick Start

### Quick Start A. Windows Installer Path

1. Open the [GitHub Releases](https://github.com/snupcb2018/VizR/releases) page.
2. Download the latest `VizR_Setup.exe` asset.
3. Prepare Docker Desktop on Windows before first use.
4. Run `VizR_Setup.exe`.
5. Complete the installation wizard.
6. Launch VizR from the installed application.
7. Select a local VizR data folder when prompted.

   ![Select VizR Data Folder](docs/images/installer/select-vizr-data-folder.png)

8. Open VizR in the browser at `http://localhost:5001`.

When the installer asks for a **VizR Data Folder**, it is asking for the host folder where VizR will store uploaded files, workbench data, intermediate outputs, and analysis results. This is not the application install path. Inside the Docker container, this folder is mounted as `/vizr`, so server-side file paths used in VizR are interpreted relative to this location.

Recommended example paths on Windows:

- `C:\Users\<username>\Documents\VizR_Data`
- `D:\VizR_Data` for larger datasets on a separate drive

Choose a location on a drive with sufficient free disk space. VizR stores uploaded files, workbench data, intermediate outputs, and analysis results in this folder, so a larger-capacity hard disk or SSD is recommended.

### Quick Start B. Prebuilt Docker Image Path

1. Create or choose a local data folder for VizR.
2. Set `VIZR_PATH` to that folder.
3. Start the container using the provided compose file.

Example:

```bash
git clone https://github.com/snupcb2018/VizR.git
cd VizR
export VIZR_PATH=$HOME/VizR_Data
mkdir -p "$VIZR_PATH/.tmp"
docker compose up -d
```

Open:

- `http://localhost:5001`

### Quick Start C. Source Build Path

1. Clone the repository.
2. Copy `config.example.json` to `config.json`.
3. Update the local path and environment values in `config.json`.
4. Build the Docker image.
5. Start the service stack.

Example:

```bash
git clone https://github.com/snupcb2018/VizR.git
cd VizR
cp config.example.json config.json
docker build -t hjung200x/vizr:latest .
export VIZR_PATH=$HOME/VizR_Data
mkdir -p "$VIZR_PATH/.tmp"
docker compose up -d
```

## 5. Requirements

The exact environment depends on the selected installation path, but the following requirements apply in general.

- Docker Desktop on Windows, or Docker Engine on Linux
- Internet connection for the initial Docker image download
- A writable local data directory for VizR workbench data
- Sufficient disk space for raw FASTQ files, intermediate outputs, references, and result files
- Sufficient CPU and memory resources for RNA-seq pipeline execution

Additional notes:

- The Windows launcher path assumes Docker Desktop is available
- The first launch may take longer because the Docker image must be pulled
- RNA-seq analysis jobs can require substantial storage depending on dataset size

## 6. Configuration

This section mainly applies to users who run VizR through a source build or a manual Docker-based deployment.

If you installed VizR through the Windows installer, you usually do not need to edit configuration files manually.

The repository includes `config.example.json` as a template for local configuration.

Typical workflow:

1. Copy `config.example.json` to `config.json`
2. Update the values for your environment
3. Start VizR using Docker or the launcher path

Current template fields include:

- `vizr_path`
- `environment`
- `log_level`
- `ports.backend`
- `ports.frontend`
- `ui.theme`
- `ui.language`
- `pipeline.max_workers`
- `pipeline.timeout`

Important runtime path behavior:

- In Docker execution, the host VizR data folder is mounted into the container as `/vizr`
- User-entered server paths inside VizR are expected to be under `/vizr/...`
- The Windows launcher also uses the selected VizR data folder as the mounted host path

## 7. Repository Structure

Main directories and files:

- `backend/` - Flask backend and pipeline execution logic
- `frontend/` - React and TypeScript web interface
- `config/` - shared settings and database schema
- `deploy/` - Windows launcher, installer, and packaging files
- `resource/` - bundled resources used by VizR
- `static/` - built frontend assets used by the deployed application
- `docs/` - user manuals
- `docker-compose.yml` - prebuilt image deployment path
- `Dockerfile` - source image build definition

## 8. Manuals

User manuals included in this repository:

- [English User Manual](docs/user-manual-en.md)
- [Korean User Manual](docs/user-manual-kr.md)

Use the manuals for detailed UI guidance and workbench usage instructions.

## 9. Docker Image

The current public Docker image used by the deployment files is:

- `hjung200x/vizr:latest`

The current compose configuration and Windows launcher reference this image directly.

If you rebuild the image locally and want to preserve compatibility with the included deployment files, keep the same image name and tag or update the deployment scripts accordingly.

## 10. Notes for Deployment

- The Windows launcher depends on Docker Desktop.
- The launcher and compose workflow mount the local VizR data folder into the container as `/vizr`.
- The first image pull requires network access.
- Some bundled reference or resource files are large enough that repository size and clone time should be considered during deployment planning.
- This public repository intentionally excludes internal research notes, manuscript drafts, temporary logs, and local runtime artifacts.
- The default administrator account is intended for first-time local setup. Change the administrator password immediately after the first login.
- The default compose/launcher workflow is designed for a trusted local workstation. If VizR is exposed beyond localhost, review Flask debug settings, CORS origins, port exposure, and Docker socket access before deployment.
- The Docker-based clustering workflow may require access to the host Docker socket. Treat this as local-workstation functionality, not as a hardened multi-tenant server configuration.

## 11. Troubleshooting

### Microsoft Defender SmartScreen warning on Windows

Windows may display a Microsoft Defender SmartScreen warning when `VizR_Setup.exe` is launched.

If this happens:

1. Click `More info`
2. Click `Run anyway`

This can occur with newly distributed installers that do not yet have established Windows reputation.

### Docker API compatibility issues on Linux

If Docker-based startup fails in some Linux environments because of Docker client/server API compatibility issues, try setting `DOCKER_API_VERSION` explicitly when launching the compose stack.

Example:

```bash
VIZR_PATH=$HOME/VizR_Data DOCKER_API_VERSION=1.43 docker compose up -d
```

Use this only when the default `docker compose up -d` workflow does not start correctly.

## 12. Citation

Citation information will be updated after manuscript acceptance.

## 13. License

VizR is licensed under the GNU General Public License v3.0 (GPL v3).

This repository is distributed for research and educational use. You may use, modify, and redistribute the software under the terms of GPL v3. If you distribute modified versions, the source code of those modifications must also remain available under the same license.

See the [LICENSE](LICENSE) file for the repository license text.
