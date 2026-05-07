; VizR Installer - RNA-Seq Analysis Platform
; Inno Setup Script

#define MyAppName "VizR"
#define MyAppVersion "1.0"
#define MyAppPublisher "hjung200x"

[Setup]
AppId={{8F9A2C3D-1E4B-4F5A-9C2D-3E6A7B8C9D0E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=VizR_Setup
Compression=lzma
SolidCompression=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"

[Files]
Source: ".\dist\VizR.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\VizR.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\VizR.exe"; Tasks: desktopicon

[Run]
; Only show "Launch VizR" option if Docker Desktop is already installed
Filename: "{app}\VizR.exe"; Description: "Launch VizR"; Flags: nowait postinstall skipifsilent; Check: IsDockerInstalled

[Code]
var
  DataDirPage: TInputDirWizardPage;
  DataDir: String;

// Initialize custom wizard page for VizR_Data folder selection
procedure InitializeWizard;
begin
  // Create custom page for data directory selection
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Select VizR Data Folder',
    'Where should VizR store your RNA-Seq analysis data?',
    'VizR will create a data folder to store your RNA-Seq analysis results and configurations.' + #13#10#13#10 +
    'Select the folder where you want to store VizR data, then click Next.',
    False, '');

  // Set default data directory
  DataDirPage.Add('');
  DataDirPage.Values[0] := ExpandConstant('{userdocs}\VizR_Data');
end;

// Check if Docker Desktop is installed
function IsDockerInstalled: Boolean;
var
  DockerPath: String;
begin
  DockerPath := ExpandConstant('{pf}\Docker\Docker\Docker Desktop.exe');
  Result := FileExists(DockerPath);
end;

// Download Docker Desktop using PowerShell
function DownloadDockerDesktop(DestPath: String): Boolean;
var
  ResultCode: Integer;
  PowerShellCommand: String;
begin
  // PowerShell command to download Docker Desktop
  PowerShellCommand :=
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ' +
    '"& {' +
    '$ProgressPreference = ''SilentlyContinue''; ' +
    'Invoke-WebRequest -Uri ''https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'' ' +
    '-OutFile ''' + DestPath + ''' ' +
    '-UseBasicParsing' +
    '}"';

  Result := Exec('cmd.exe', '/c ' + PowerShellCommand, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;

// Install Docker Desktop
function InstallDockerDesktop(InstallerPath: String): Boolean;
var
  ResultCode: Integer;
begin
  // Run Docker Desktop installer in background (don't wait for completion)
  Result := Exec(InstallerPath, 'install --accept-license', '', SW_SHOW, ewNoWait, ResultCode);
end;

// Save configuration after installation
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile: String;
  ConfigContent: String;
  JsonPath: String;
  DockerInstallerPath: String;
  DownloadChoice: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Save data directory to config file
    DataDir := DataDirPage.Values[0];
    ConfigFile := ExpandConstant('{app}\.vizr_config.json');

    // Convert backslashes to forward slashes for JSON
    JsonPath := DataDir;
    StringChangeEx(JsonPath, '\', '/', True);

    // Create simple JSON config file
    ConfigContent := '{' + #13#10 +
      '  "vizr_path": "' + JsonPath + '",' + #13#10 +
      '  "version": "1.0"' + #13#10 +
      '}';

    SaveStringToFile(ConfigFile, ConfigContent, False);

    // Check Docker Desktop installation
    if not IsDockerInstalled then
    begin
      DownloadChoice := MsgBox(
        'Docker Desktop is not installed!' + #13#10#13#10 +
        'VizR requires Docker Desktop to run.' + #13#10#13#10 +
        'Would you like to download and install Docker Desktop now?' + #13#10 +
        '(This will download about 500MB and may take 5-10 minutes)' + #13#10#13#10 +
        'Click "Yes" to download and install automatically' + #13#10 +
        'Click "No" to skip',
        mbConfirmation, MB_YESNO);

      if DownloadChoice = IDYES then
      begin
        // Automatic download and install
        DockerInstallerPath := ExpandConstant('{tmp}\DockerDesktopInstaller.exe');

        if MsgBox('Downloading Docker Desktop (about 500MB)...' + #13#10#13#10 +
                  'Please wait patiently - this may take 5-10 minutes.' + #13#10#13#10 +
                  'Click OK to start download now.',
                  mbInformation, MB_OK) = IDOK then
        begin
          if DownloadDockerDesktop(DockerInstallerPath) then
          begin
            MsgBox('Download completed!' + #13#10#13#10 +
                   'Docker Desktop will now be installed.',
                   mbInformation, MB_OK);

            // Start Docker Desktop installer
            InstallDockerDesktop(DockerInstallerPath);
          end
          else
          begin
            MsgBox('Download failed!' + #13#10#13#10 +
                   'Please check your internet connection.',
                   mbError, MB_OK);
          end;
        end;
      end;
    end;
  end;
end;
