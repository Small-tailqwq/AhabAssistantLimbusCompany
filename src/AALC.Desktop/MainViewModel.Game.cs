using AALC.Platform.Windows.Tools;
using AALC.Runtime.Tools;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace AALC.Desktop;

public partial class MainViewModel
{
    [ObservableProperty] private string gameDirectory = "";

    public async Task FindGameAtStartupAsync()
    {
        if (!string.IsNullOrWhiteSpace(GameDirectory)) return;
        try
        {
            var directory = await Task.Run(GameInstallationLocator.Find);
            if (directory is null || !string.IsNullOrWhiteSpace(GameDirectory) || IsRunning) return;
            GameDirectory = directory;
            SaveGameDirectory();
        }
        catch (Exception exception) { Error = exception.Message; }
    }

    [RelayCommand(CanExecute = nameof(CanConfigure))]
    private async Task SearchGameDirectoryAsync()
    {
        try
        {
            var directory = await Task.Run(GameInstallationLocator.Find);
            if (directory is null)
                throw new DirectoryNotFoundException("未找到 Limbus Company，请浏览并选择游戏安装目录。");
            GameDirectory = directory;
            SaveGameDirectory();
            Error = "";
            Status = "游戏安装目录已找到并保存";
        }
        catch (Exception exception) { Error = exception.Message; }
    }

    private string GameExecutable() =>
        string.IsNullOrWhiteSpace(GameDirectory) ? "" : Path.Combine(GameDirectory, GameInstallation.ExecutableName);

    private GameTaskContext NewTaskContext() => new(RepositoryRoot, OcrModelsDirectory, new(GameLanguage, GameTheme),
        SelectedWindow, GameExecutable(), "", Publish, UpdatePreview);

    private void SaveGameDirectory()
    {
        var directory = GameInstallation.RequireDirectory(GameDirectory);
        settingsStore.Save(settingsStore.Load() with { GameExecutablePath = Path.Combine(directory, GameInstallation.ExecutableName) });
    }
}
