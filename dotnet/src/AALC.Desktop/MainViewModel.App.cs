using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Platform;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using AALC.Platform.Windows;
using AALC.Runtime;
using AALC.Runtime.Configuration;

namespace AALC.Desktop;

public sealed record AboutComponent(string Name, string Version, string License);

public partial class MainViewModel
{
    private int logoClicks;
    private readonly WindowIcon?[] logoIcons = new WindowIcon?[3];
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(FullName), nameof(LogoSource), nameof(LogoIcon), nameof(IsAngelaIce), nameof(IsAngelaGold), nameof(IsAngela))]
    private int logoVariant;

    public string FullName => LogoVariant == 0
        ? "AI-powered Ahab Assistant for Limbus Company"
        : "AI-powered Angela Assistant for Limbus Company";
    // 矢量 DrawingImage 由 scripts/build_dotnet_logos.py 生成，任意尺寸和 DPI 下都不经位图缩放。
    public IImage LogoSource
    {
        get
        {
            var key = LogoVariant switch
            {
                1 => "LogoAngelaIce",
                2 => "LogoAngelaGold",
                _ => "Logo"
            };
            Application.Current!.TryGetResource(key, null, out var logo);
            return (IImage)logo!;
        }
    }
    public bool IsAngelaIce => LogoVariant == 1;
    public bool IsAngelaGold => LogoVariant == 2;
    public bool IsAngela => LogoVariant != 0;
    public WindowIcon LogoIcon
    {
        get
        {
            if (logoIcons[LogoVariant] is { } icon) return icon;
            var asset = LogoVariant switch
            {
                1 => "LogoAngelaIce.ico",
                2 => "LogoAngelaGold.ico",
                _ => "Logo.ico"
            };
            using var stream = AssetLoader.Open(new Uri($"avares://AAALC/Assets/{asset}"));
            return logoIcons[LogoVariant] = new WindowIcon(stream);
        }
    }

    [RelayCommand]
    private void RevealAngela()
    {
        if (LogoVariant != 0 || ++logoClicks < 5) return;
        LogoVariant = Random.Shared.Next(1, 3);
    }

    public ChoiceItem[] StartPages { get; } = [new("daily", "日常任务"), new("mirror", "镜牢"), new("monitor", "运行监控")];
    [ObservableProperty] private ChoiceItem? selectedStartPage;
    [ObservableProperty] private bool showMonitorOnRun = true;
    [ObservableProperty] private bool findWindowsOnStartup = true;
    private bool rememberAngela;
    public bool RememberAngela
    {
        get => rememberAngela;
        set
        {
            if (value == rememberAngela) return;
            try
            {
                var settings = settingsStore.Load();
                settingsStore.Save(settings with { App = (settings.App ?? new()) with { RememberAngela = value } });
                SetProperty(ref rememberAngela, value);
                Error = "";
            }
            catch (Exception exception)
            {
                Error = exception.Message;
                OnPropertyChanged();
            }
        }
    }
    public string ProfileDirectory => settingsStore.DirectoryPath;
    public string DataDirectory
    {
        get
        {
            try { return EvidencePaths.ResolveRoot(); }
            catch (Exception exception) { return exception.Message; }
        }
    }

    public static string AppVersion { get; } = Short(typeof(MainViewModel));

    // 版本取自 deps.json 中实际解析的包，不加载 OpenCV/ONNX 程序集，保持启动期不初始化视觉库。
    public AboutComponent[] AboutComponents => aboutComponents ??= BuildAboutComponents();
    private AboutComponent[]? aboutComponents;

    private static AboutComponent[] BuildAboutComponents()
    {
        var packages = PackageVersions();
        string Package(string id) => packages.GetValueOrDefault(id, "—");
        return
        [
            new(".NET", Environment.Version.ToString(), "MIT"),
            new("Avalonia", Package("Avalonia"), "MIT"),
            new("SukiUI", Package("SukiUI"), "MIT"),
            new("CommunityToolkit.Mvvm", Package("CommunityToolkit.Mvvm"), "MIT"),
            new("OpenCvSharp", Package("OpenCvSharp4"), "Apache-2.0"),
            new("ONNX Runtime", Package("Microsoft.ML.OnnxRuntime"), "MIT"),
            new("PaddleOCR 模型", "PP-OCRv4", "Apache-2.0"),
            new("零协汉化（可选安装）", "—", "CC BY-NC-SA 4.0"),
        ];
    }

    private static Dictionary<string, string> PackageVersions()
    {
        try
        {
            var path = Path.Combine(AppContext.BaseDirectory, $"{Assembly.GetEntryAssembly()!.GetName().Name}.deps.json");
            using var document = JsonDocument.Parse(File.ReadAllText(path));
            return document.RootElement.GetProperty("libraries").EnumerateObject()
                .Select(library => library.Name.Split('/'))
                .Where(parts => parts.Length == 2)
                .GroupBy(parts => parts[0])
                .ToDictionary(group => group.Key, group => group.First()[1]);
        }
        catch (Exception exception) when (exception is IOException or JsonException or KeyNotFoundException or UnauthorizedAccessException)
        {
            return [];
        }
    }

    private static string Short(Type type)
    {
        var version = type.Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
            ?? type.Assembly.GetName().Version?.ToString() ?? "—";
        var metadata = version.IndexOf('+');
        return metadata >= 0 ? version[..metadata] : version;
    }

    private void LoadAppSettings(AppSettings settings)
    {
        SelectedStartPage = StartPages.FirstOrDefault(item => item.Key == settings.StartPage) ?? StartPages[0];
        ShowMonitorOnRun = settings.ShowMonitorOnRun;
        FindWindowsOnStartup = settings.FindWindowsOnStartup;
        rememberAngela = settings.RememberAngela;
        if (rememberAngela) LogoVariant = Random.Shared.Next(1, 3);
    }

    private AppSettings GetAppSettings() => new(SelectedStartPage?.Key ?? "daily", ShowMonitorOnRun, FindWindowsOnStartup, RememberAngela);

    /// <summary>启动后静默查找游戏窗口；找不到不提示错误，避免首屏出现红字。</summary>
    public void FindWindowsAtStartup()
    {
        if (!FindWindowsOnStartup || IsRunning) return;
        try
        {
            foreach (var window in GameWindow.Find()) Windows.Add(window);
            SelectedWindow = Windows.FirstOrDefault();
        }
        catch { }
    }

    [RelayCommand] private void OpenProfileDirectory() => OpenDirectory(() => ProfileDirectory);
    [RelayCommand] private void OpenDataDirectory() => OpenDirectory(EvidencePaths.ResolveRoot);

    private void OpenDirectory(Func<string> resolve)
    {
        try
        {
            var path = resolve();
            Directory.CreateDirectory(path);
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            Error = "";
        }
        catch (Exception exception) { Error = exception.Message; }
    }
}
