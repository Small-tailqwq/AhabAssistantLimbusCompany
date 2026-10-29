using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using AALC.Platform.Windows;
using AALC.Platform.Windows.Tools;
using AALC.Runtime;
using AALC.Runtime.Mail;
using AALC.Runtime.Tools;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public partial class MainViewModel
{
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasInstalledLocalization))] private string installedLocalization = "";
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasLatestLocalization))] private string latestLocalization = "";
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasLocalizationNotes))] private string localizationNotes = "";
    public bool HasInstalledLocalization => InstalledLocalization.Length > 0;
    public bool HasLatestLocalization => LatestLocalization.Length > 0;
    public bool HasLocalizationNotes => LocalizationNotes.Length > 0;
    [ObservableProperty] private bool hasToolMessages;
    [ObservableProperty, NotifyCanExecuteChangedFor(nameof(InstallLocalizationCommand))]
    private LlcRelease? localizationRelease;
    public ObservableCollection<string> ToolMessages { get; } = [];

    partial void OnGameDirectoryChanged(string value)
    {
        LocalizationRelease = null;
        InstalledLocalization = "";
        LatestLocalization = "";
        LocalizationNotes = "";
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private async Task CheckLocalizationAsync()
    {
        var directory = GameDirectory;
        LocalizationRelease = null;
        await RunToolAsync(async (progress, token) =>
        {
            var installed = LlcLocalization.InstalledVersion(directory);
            Dispatcher.UIThread.Invoke(() => InstalledLocalization = installed);
            progress.Report("正在查询零协最新版本…");
            using var client = new HttpClient();
            var release = await new LlcLocalization(client).CheckAsync(token);
            Dispatcher.UIThread.Invoke(() =>
            {
                LocalizationRelease = release;
                LatestLocalization = release.Tag;
                LocalizationNotes = release.Notes;
            });
            return installed == release.Tag ? $"汉化已是最新版本：{release.Tag}" : $"可安装汉化：{release.Tag}";
        });
    }

    private bool CanInstallLocalization() => !IsRunning && LocalizationRelease is not null;

    [RelayCommand(CanExecute = nameof(CanInstallLocalization))]
    private async Task InstallLocalizationAsync()
    {
        var directory = GameDirectory;
        var release = LocalizationRelease!;
        await RunToolAsync(async (progress, token) =>
        {
            GameFiles.RequireGameClosed();
            using var client = new HttpClient();
            var installed = await new LlcLocalization(client).InstallAsync(directory, release, progress, token);
            Dispatcher.UIThread.Invoke(() => InstalledLocalization = installed.Version);
            if (installed.BackupDirectory is not null) progress.Report($"原汉化备份：{installed.BackupDirectory}");
            return $"零协汉化 {installed.Version} 已安装。启动游戏后在语言设置中选择 LLC_zh-CN。";
        });
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private Task DisableTutorialsAsync() => RunToolAsync((progress, token) => GameFiles.SetTutorialsDisabledAsync(true, progress, token));

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private Task EnableTutorialsAsync() => RunToolAsync((progress, token) => GameFiles.SetTutorialsDisabledAsync(false, progress, token));

    [RelayCommand(CanExecute = nameof(CanRunMail))]
    private async Task CaptureScreenshotAsync()
    {
        var selected = SelectedWindow!;
        await RunToolAsync(async (progress, token) =>
        {
            progress.Report("正在采集游戏窗口…");
            using var window = new GameWindow(selected);
            var frame = await window.CaptureAsync(token);
            token.ThrowIfCancellationRequested();
            var directory = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "screenshots"));
            Directory.CreateDirectory(directory);
            var path = EvidencePaths.RequireExternalPath(Path.Combine(directory, $"screenshot_{DateTime.Now:yyyyMMdd-HHmmss-fff}.png"));
            using (var bitmap = CreateBitmap(frame))
            using (var output = new FileStream(path, FileMode.CreateNew)) bitmap.Save(output);
            UpdatePreview(frame);
            return $"截图已保存：{path}";
        });
    }

    [RelayCommand]
    private void OpenScreenshotDirectory()
    {
        try
        {
            var path = EvidencePaths.RequireExternalPath(Path.Combine(EvidencePaths.ResolveRoot(), "screenshots"));
            Directory.CreateDirectory(path);
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            Error = "";
        }
        catch (Exception exception) { Error = exception.Message; }
    }

    private async Task RunToolAsync(Func<IProgress<string>, CancellationToken, Task<string>> operation)
    {
        ToolMessages.Clear();
        HasToolMessages = false;
        var finalMessage = "";
        var progress = new Progress<string>(message => { ToolMessages.Add(message); HasToolMessages = true; });
        await RunAsync(async token =>
        {
            try
            {
                var message = await operation(progress, token);
                finalMessage = message;
                return new RunResult(RunOutcome.Completed, message, 0, 0);
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested)
            {
                finalMessage = "已停止";
                return new RunResult(RunOutcome.Cancelled, "已停止", 0, 0);
            }
            catch (OperationCanceledException exception)
            {
                throw new TimeoutException("工具操作等待超时，请重试。", exception);
            }
        });
        if (finalMessage.Length > 0) { ToolMessages.Add(finalMessage); HasToolMessages = true; }
    }
}
