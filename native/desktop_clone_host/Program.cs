using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace AALC.DesktopCloneHost
{
    internal static class NativeMethods
    {
        internal const uint NoChildSessionId = 0xFFFFFFFF;
        internal const int ErrorNotFound = 1168;
        internal const int DwmUseImmersiveDarkMode = 20;
        internal const int DwmUseImmersiveDarkModeBefore20H1 = 19;

        [DllImport("wtsapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool WTSGetChildSessionId(out uint sessionId);

        [DllImport("wtsapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool WTSIsChildSessionsEnabled(
            [MarshalAs(UnmanagedType.Bool)] out bool enabled);

        [DllImport("wtsapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool WTSLogoffSession(
            IntPtr serverHandle,
            uint sessionId,
            [MarshalAs(UnmanagedType.Bool)] bool wait);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool EnableWindow(
            IntPtr windowHandle,
            [MarshalAs(UnmanagedType.Bool)] bool enable);

        [DllImport("dwmapi.dll")]
        internal static extern int DwmSetWindowAttribute(
            IntPtr windowHandle,
            int attribute,
            ref int value,
            int valueSize);
    }

    [ComImport]
    [Guid("302D8188-0052-4807-806A-362B628F9AC5")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IMsRdpExtendedSettings
    {
        void set_Property(
            [In, MarshalAs(UnmanagedType.BStr)] string propertyName,
            [In, MarshalAs(UnmanagedType.Struct)] ref object value);

        [return: MarshalAs(UnmanagedType.Struct)]
        object get_Property([In, MarshalAs(UnmanagedType.BStr)] string propertyName);
    }

    [ComImport]
    [Guid("336D5562-EFA8-482E-8CB3-C5C0FC7A7DB6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
    [TypeLibType(TypeLibTypeFlags.FDispatchable)]
    internal interface IMsTscAxEvents
    {
        [DispId(3)]
        void OnLoginComplete();

        [DispId(4)]
        void OnDisconnected([In] int disconnectReason);

        [DispId(10)]
        void OnFatalError([In] int errorCode);

        [DispId(22)]
        void OnLogonError([In] int errorCode);
    }

    internal sealed class RdpFailureEventArgs : EventArgs
    {
        internal RdpFailureEventArgs(
            string stage,
            int errorCode,
            int extendedErrorCode,
            string description)
        {
            Stage = stage;
            ErrorCode = errorCode;
            ExtendedErrorCode = extendedErrorCode;
            Description = description;
        }

        internal string Stage { get; private set; }
        internal int ErrorCode { get; private set; }
        internal int ExtendedErrorCode { get; private set; }
        internal string Description { get; private set; }
    }

    internal sealed class RdpHost : AxHost
    {
        private const string RdpClientClsid = "A0C63C30-F08D-4AB4-907C-34905D770C7D";
        private ConnectionPointCookie _eventCookie;
        private RdpEventSink _eventSink;
        private bool _connectionAttemptInProgress;
        private bool _connectionFailureReported;
        private bool _disconnectRequested;

        internal event EventHandler<RdpFailureEventArgs> ConnectionFailed;
        internal event EventHandler LoginCompleted;

        internal RdpHost() : base(RdpClientClsid)
        {
            BackColor = Color.Black;
        }

        internal int ConnectedState
        {
            get
            {
                dynamic client = GetOcx();
                return Convert.ToInt32(client.Connected);
            }
        }

        internal int ExtendedDisconnectReason
        {
            get
            {
                dynamic client = GetOcx();
                return Convert.ToInt32(client.ExtendedDisconnectReason);
            }
        }

        /// <summary>
        /// 连接完成后重新套用 SmartSizing，并回报是否真的生效。
        /// </summary>
        /// <remarks>
        /// 在 Connect() 之前设置的 SmartSizing 不会作用于已协商的会话：远端画面
        /// 按 1:1 画在控件左上角，控件其余区域由 OCX 自绘成白色。AxHost 的
        /// BackColor 到不了被宿主的 OCX，所以只能让缩放真正生效，或者不要把控件
        /// 放大到超过会话分辨率。
        /// </remarks>
        /// <summary>回读连接实际生效的音频重定向模式（0 送回客户端，1 远端播放，2 关闭）。</summary>
        internal int GetAudioRedirectionMode()
        {
            try
            {
                dynamic client = GetOcx();
                return Convert.ToInt32(client.AdvancedSettings7.AudioRedirectionMode);
            }
            catch
            {
                return -1;
            }
        }

        internal bool ApplySmartSizing()
        {
            try
            {
                dynamic client = GetOcx();
                dynamic advancedSettings = client.AdvancedSettings7;
                advancedSettings.SmartSizing = true;
                return Convert.ToBoolean(advancedSettings.SmartSizing);
            }
            catch
            {
                return false;
            }
        }

        internal void ConnectToChildSession(
            int width,
            int height,
            int rdpPort,
            string connectingText,
            string disconnectedText,
            string startProgram,
            string startWorkDir)
        {
            CreateControl();
            dynamic client = GetOcx();
            client.Server = "localhost";
            client.DesktopWidth = Math.Max(200, Math.Min(width, 8192));
            client.DesktopHeight = Math.Max(200, Math.Min(height, 8192));
            client.ColorDepth = 32;
            client.ConnectingText = connectingText;
            client.DisconnectedText = disconnectedText;

            dynamic securedSettings = client.SecuredSettings2;
            securedSettings.KeyboardHookMode = 1;
            // 精简 shell：指定初始程序后子会话不运行 explorer，
            // Run 键与启动文件夹的自启动因此不会执行。
            if (!string.IsNullOrEmpty(startProgram))
            {
                securedSettings.StartProgram = startProgram;
                if (!string.IsNullOrEmpty(startWorkDir))
                {
                    securedSettings.WorkDir = startWorkDir;
                }
            }

            dynamic advancedSettings = client.AdvancedSettings7;
            advancedSettings.RDPPort = rdpPort;
            advancedSettings.EnableCredSspSupport = true;
            advancedSettings.EnableWindowsKey = 1;
            advancedSettings.SmartSizing = true;
            // 0 = 把远端声音送回客户端播放。这本来就是默认值，但分身自始至终
            // 没有声音，显式写死并在连接后回读，用来区分"客户端没请求重定向"
            // 和"客户端请求了但子会话没把音频送过来"。
            advancedSettings.AudioRedirectionMode = 0;

            object connectToChildSession = true;
            IMsRdpExtendedSettings extendedSettings = (IMsRdpExtendedSettings)client;
            extendedSettings.set_Property("ConnectToChildSession", ref connectToChildSession);
            object configuredValue = extendedSettings.get_Property("ConnectToChildSession");
            if (!Convert.ToBoolean(configuredValue))
            {
                throw new InvalidOperationException(
                    "RDP ActiveX 未接受 ConnectToChildSession=true。");
            }

            _connectionAttemptInProgress = true;
            _connectionFailureReported = false;
            _disconnectRequested = false;
            try
            {
                client.Connect();
            }
            catch
            {
                _connectionAttemptInProgress = false;
                throw;
            }
        }

        internal bool DisconnectSession()
        {
            if (ConnectedState != 0)
            {
                _disconnectRequested = true;
                _connectionAttemptInProgress = false;
                dynamic client = GetOcx();
                client.Disconnect();
                return true;
            }
            return !_connectionAttemptInProgress;
        }

        internal void SetInputBlocked(bool blocked)
        {
            TabStop = !blocked;
            if (IsHandleCreated)
            {
                NativeMethods.EnableWindow(Handle, !blocked);
            }
        }

        internal void UpdateStatusTexts(
            string connectingText,
            string disconnectedText)
        {
            if (!IsHandleCreated)
            {
                return;
            }
            try
            {
                dynamic client = GetOcx();
                if (Convert.ToInt32(client.Connected) == 0)
                {
                    client.ConnectingText = connectingText;
                    client.DisconnectedText = disconnectedText;
                }
            }
            catch
            {
            }
        }

        protected override void CreateSink()
        {
            base.CreateSink();
            _eventSink = new RdpEventSink(this);
            _eventCookie = new ConnectionPointCookie(
                GetOcx(),
                _eventSink,
                typeof(IMsTscAxEvents));
        }

        protected override void DetachSink()
        {
            try
            {
                if (_eventCookie != null)
                {
                    _eventCookie.Disconnect();
                    _eventCookie = null;
                }
                _eventSink = null;
            }
            finally
            {
                base.DetachSink();
            }
        }

        private void OnLoginComplete()
        {
            _connectionAttemptInProgress = false;
            _connectionFailureReported = false;
            EventHandler handler = LoginCompleted;
            if (handler != null)
            {
                handler(this, EventArgs.Empty);
            }
        }

        private void OnDisconnected(int disconnectReason)
        {
            bool failedWhileConnecting = _connectionAttemptInProgress;
            _connectionAttemptInProgress = false;
            if (_disconnectRequested)
            {
                _disconnectRequested = false;
                return;
            }
            if (_connectionFailureReported)
            {
                return;
            }

            int extendedReason = TryGetExtendedDisconnectReason();
            if (!failedWhileConnecting
                && disconnectReason >= 1
                && disconnectReason <= 3
                && extendedReason >= 0
                && extendedReason <= 2)
            {
                return;
            }
            string description = TryGetErrorDescription(
                disconnectReason,
                extendedReason);
            ReportConnectionFailure(
                failedWhileConnecting ? "connect" : "disconnect",
                disconnectReason,
                extendedReason,
                description);
        }

        private void OnFatalError(int errorCode)
        {
            _connectionAttemptInProgress = false;
            if (!_disconnectRequested)
            {
                ReportConnectionFailure(
                    "fatal",
                    errorCode,
                    TryGetExtendedDisconnectReason(),
                    "RDP 客户端发生致命错误。");
            }
        }

        private void OnLogonError(int errorCode)
        {
            if (_disconnectRequested || IsNonTerminalLogonEvent(errorCode))
            {
                return;
            }
            _connectionAttemptInProgress = false;
            ReportConnectionFailure(
                "logon",
                errorCode,
                TryGetExtendedDisconnectReason(),
                GetLogonErrorDescription(errorCode));
        }

        private int TryGetExtendedDisconnectReason()
        {
            try
            {
                return ExtendedDisconnectReason;
            }
            catch
            {
                return 0;
            }
        }

        private string TryGetErrorDescription(
            int disconnectReason,
            int extendedDisconnectReason)
        {
            try
            {
                dynamic client = GetOcx();
                string description = Convert.ToString(
                    client.GetErrorDescription(
                        disconnectReason,
                        extendedDisconnectReason));
                return string.IsNullOrWhiteSpace(description)
                    ? "RDP 连接失败。"
                    : description;
            }
            catch
            {
                return "RDP 连接失败。";
            }
        }

        private void ReportConnectionFailure(
            string stage,
            int errorCode,
            int extendedErrorCode,
            string description)
        {
            if (_connectionFailureReported)
            {
                return;
            }
            _connectionFailureReported = true;
            EventHandler<RdpFailureEventArgs> handler = ConnectionFailed;
            if (handler != null)
            {
                handler(
                    this,
                    new RdpFailureEventArgs(
                        stage,
                        errorCode,
                        extendedErrorCode,
                        description));
            }
        }

        private static bool IsNonTerminalLogonEvent(int errorCode)
        {
            return errorCode == -5
                || errorCode == -4
                || errorCode == -2
                || errorCode == 3;
        }

        private static string GetLogonErrorDescription(int errorCode)
        {
            switch (errorCode)
            {
                case -7:
                    return "Winlogon 正在显示拒绝断开现有会话对话框。";
                case -6:
                    return "Winlogon 正在显示无权限对话框。";
                case -3:
                    return "Winlogon 已静默终止登录。";
                case -1:
                    return "RDP 登录被拒绝。";
                case 0:
                    return "RDP 登录凭据无效；Child Session 未完成免凭据登录。";
                case 1:
                    return "Windows 密码已过期。";
                case 2:
                    return "RDP 登录处理失败。";
                default:
                    return "RDP 登录阶段发生错误。";
            }
        }

        [ComVisible(true)]
        [ClassInterface(ClassInterfaceType.None)]
        private sealed class RdpEventSink : IMsTscAxEvents
        {
            private readonly RdpHost _owner;

            internal RdpEventSink(RdpHost owner)
            {
                _owner = owner;
            }

            public void OnLoginComplete()
            {
                _owner.OnLoginComplete();
            }

            public void OnDisconnected(int disconnectReason)
            {
                _owner.OnDisconnected(disconnectReason);
            }

            public void OnFatalError(int errorCode)
            {
                _owner.OnFatalError(errorCode);
            }

            public void OnLogonError(int errorCode)
            {
                _owner.OnLogonError(errorCode);
            }
        }
    }

    internal sealed class CloneToolStripColorTable : ProfessionalColorTable
    {
        private readonly Color _background;
        private readonly Color _hover;
        private readonly Color _checked;
        private readonly Color _border;

        internal CloneToolStripColorTable(bool dark)
        {
            UseSystemColors = false;
            _background = dark
                ? Color.FromArgb(31, 31, 31)
                : Color.White;
            _hover = dark
                ? Color.FromArgb(58, 58, 58)
                : Color.FromArgb(245, 245, 245);
            _checked = Color.FromArgb(156, 8, 11);
            _border = dark
                ? Color.FromArgb(85, 85, 85)
                : Color.FromArgb(208, 208, 208);
        }

        public override Color ToolStripGradientBegin { get { return _background; } }
        public override Color ToolStripGradientMiddle { get { return _background; } }
        public override Color ToolStripGradientEnd { get { return _background; } }
        public override Color ToolStripBorder { get { return _border; } }
        public override Color ButtonSelectedGradientBegin { get { return _hover; } }
        public override Color ButtonSelectedGradientMiddle { get { return _hover; } }
        public override Color ButtonSelectedGradientEnd { get { return _hover; } }
        public override Color ButtonSelectedBorder { get { return _border; } }
        public override Color ButtonPressedGradientBegin { get { return _checked; } }
        public override Color ButtonPressedGradientMiddle { get { return _checked; } }
        public override Color ButtonPressedGradientEnd { get { return _checked; } }
        public override Color ButtonCheckedGradientBegin { get { return _checked; } }
        public override Color ButtonCheckedGradientMiddle { get { return _checked; } }
        public override Color ButtonCheckedGradientEnd { get { return _checked; } }
        public override Color ButtonCheckedHighlight { get { return _checked; } }
        public override Color ButtonCheckedHighlightBorder { get { return _border; } }
        public override Color ButtonPressedHighlight { get { return _checked; } }
        public override Color ButtonPressedHighlightBorder { get { return _border; } }
    }

    internal sealed class HostForm : Form
    {
        private const int InitialConnectionRetryCount = 3;
        private readonly RdpHost _rdpHost;
        private readonly Panel _viewerPanel;
        private readonly ToolStrip _toolbar;
        private readonly ToolStripButton _muteButton;
        private readonly ToolStripButton _inputButton;
        private readonly Dictionary<string, ToolStripButton> _toolButtons =
            new Dictionary<string, ToolStripButton>(
                StringComparer.OrdinalIgnoreCase);
        private readonly AudioSessionController _audioSessionController;
        private readonly StreamReader _reader;
        private readonly StreamWriter _writer;
        private readonly object _writeLock = new object();
        private readonly object _sessionLock = new object();
        private readonly object _logoffLock = new object();
        private readonly object _uiCommandLock = new object();
        private readonly Queue<string> _pendingUiCommands =
            new Queue<string>();
        private readonly ManualResetEventSlim _ownedSessionReady =
            new ManualResetEventSlim(false);
        private readonly ManualResetEventSlim _activeXDisconnectCompleted =
            new ManualResetEventSlim(false);
        private readonly ManualResetEventSlim _audioRestoreCompleted =
            new ManualResetEventSlim(false);
        private readonly int _desktopWidth;
        private readonly int _desktopHeight;
        private readonly int _rdpPort;
        private volatile bool _showRequested;
        private string _connectingText;
        private string _disconnectedText;
        private readonly string _startProgram;
        private readonly string _startWorkDir;
        private readonly System.Windows.Forms.Timer _statusTimer;
        private bool _ownershipFailed;
        private bool _reportedConnected;
        private volatile bool _activeXDisconnectSucceeded;
        private volatile bool _audioRestoreSucceeded;
        private volatile bool _logoffStarted;
        private bool _loginCompleted;
        private int _connectionRetryCount;
        private int _connectionGeneration;
        private DateTime? _retryAtUtc;
        private uint? _candidateSessionId;
        private uint? _ownedSessionId;
        private bool _darkTheme;
        private bool _userMuted;
        private bool _inputBlocked;
        private bool _audioFailureReported;
        private string _lastAudioFailureReport;
        private DateTime _nextAudioRetryUtc;
        private FormWindowState _windowStateBeforeHide =
            FormWindowState.Normal;
        private bool _initialDisplaySuppressed;
        private bool _smartSizingActive;
        private string _lastLayoutReport;

        internal HostForm(
            NamedPipeClientStream pipe,
            int desktopWidth,
            int desktopHeight,
            int rdpPort,
            bool showOnStart,
            string windowTitle,
            string connectingText,
            string disconnectedText,
            string startProgram,
            string startWorkDir,
            bool darkTheme,
            string visibleTools,
            string muteText,
            string inputText)
        {
            _desktopWidth = desktopWidth;
            _desktopHeight = desktopHeight;
            _rdpPort = rdpPort;
            _showRequested = showOnStart;
            _connectingText = connectingText;
            _disconnectedText = disconnectedText;
            _startProgram = startProgram;
            _startWorkDir = startWorkDir;
            _darkTheme = darkTheme;
            _reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, true);
            _writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true);
            _writer.AutoFlush = true;
            Send("hello\trdp-host\t1");
            Send("rdp-diagnostic\thost-bootstrap\tpipe-ready");

            Text = windowTitle;
            Width = 1280;
            Height = 760;
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;
            BackColor = Color.Black;
            _initialDisplaySuppressed = !showOnStart;
            if (_initialDisplaySuppressed)
            {
                Opacity = 0;
                ShowInTaskbar = false;
            }
            try
            {
                Icon = System.Drawing.Icon.ExtractAssociatedIcon(
                    Application.ExecutablePath);
            }
            catch
            {
            }

            Send("rdp-diagnostic\thost-bootstrap\tcreating-activex");
            _rdpHost = new RdpHost();
            Send("rdp-diagnostic\thost-bootstrap\tactivex-created");
            _rdpHost.ConnectionFailed += OnRdpConnectionFailed;
            _rdpHost.LoginCompleted += OnRdpLoginCompleted;
            _viewerPanel = new Panel();
            _viewerPanel.BackColor = Color.Black;
            _viewerPanel.Dock = DockStyle.Fill;
            _viewerPanel.Controls.Add(_rdpHost);
            _viewerPanel.ClientSizeChanged += delegate { LayoutRdpHost(); };

            _toolbar = new ToolStrip();
            _toolbar.AutoSize = true;
            _toolbar.CanOverflow = false;
            _toolbar.Dock = DockStyle.Top;
            _toolbar.GripStyle = ToolStripGripStyle.Hidden;
            _toolbar.Padding = new Padding(6, 3, 6, 3);
            _toolbar.RenderMode = ToolStripRenderMode.Professional;
            _toolbar.ShowItemToolTips = true;
            _toolbar.TabStop = true;

            _muteButton = CreateToolButton(muteText);
            _muteButton.Click += delegate
            {
                SetUserMuted(!_userMuted);
            };
            _inputButton = CreateToolButton(inputText);
            _inputButton.Click += delegate
            {
                SetInputBlocked(!_inputBlocked);
            };
            _toolButtons.Add("mute", _muteButton);
            _toolButtons.Add("input", _inputButton);
            _toolbar.Items.Add(_muteButton);
            _toolbar.Items.Add(_inputButton);

            HashSet<string> visibleToolIds = ParseToolIds(visibleTools);
            _muteButton.Visible = visibleToolIds.Contains("mute");
            _inputButton.Visible = visibleToolIds.Contains("input");
            UpdateToolbarVisibility();

            Controls.Add(_viewerPanel);
            Controls.Add(_toolbar);
            LayoutRdpHost();
            Send("rdp-diagnostic\thost-bootstrap\tactivex-added");

            _audioSessionController = new AudioSessionController();
            // 注意：这里不要碰 WASAPI。清理遗留静音被推迟到 RDP 登录完成之后
            // （OnRdpLoginCompleted），因为在 mstscax 建立自己的音频渲染流之前
            // 就创建本进程的音频会话，可能干扰它打开输出设备。
            ApplyTheme(_darkTheme);
            ApplyEffectiveMute();
            ApplyInputBlocked();

            _statusTimer = new System.Windows.Forms.Timer();
            _statusTimer.Interval = 500;
            _statusTimer.Tick += PollConnectionState;

            Shown += OnShown;
            FormClosing += OnFormClosing;

            // 命令线程必须最后启动。它的 finally 会走 LogoffAndExitFromWorker →
            // RestoreAudioBeforeExit，而 _audioSessionController 直到本构造函数
            // 后段才赋值；构造期间断线会让该路径解引用 null。写端已就绪，握手
            // 消息先发无妨，控制端此时发来的命令由管道缓冲区暂存。
            Thread readerThread = new Thread(ReadCommands);
            readerThread.IsBackground = true;
            readerThread.Name = "AALC Desktop Clone Host Commands";
            readerThread.Start();
            Send("rdp-diagnostic\thost-bootstrap\tform-ready");
        }

        protected override void OnHandleCreated(EventArgs eventArgs)
        {
            base.OnHandleCreated(eventArgs);
            ApplyTitleBarTheme();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && _audioSessionController != null)
            {
                _audioSessionController.Dispose();
            }
            base.Dispose(disposing);
        }

        private static ToolStripButton CreateToolButton(string text)
        {
            ToolStripButton button = new ToolStripButton();
            button.AutoToolTip = true;
            button.CheckOnClick = false;
            button.DisplayStyle = ToolStripItemDisplayStyle.Text;
            button.Margin = new Padding(3, 0, 3, 0);
            button.Padding = new Padding(8, 2, 8, 2);
            button.Text = text;
            button.ToolTipText = text;
            button.AccessibleName = text;
            return button;
        }

        private static void SetToolButtonText(
            ToolStripButton button,
            string text)
        {
            button.Text = text;
            button.ToolTipText = text;
            button.AccessibleName = text;
        }

        private static HashSet<string> ParseToolIds(string value)
        {
            HashSet<string> result = new HashSet<string>(
                StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrWhiteSpace(value))
            {
                return result;
            }
            string[] parts = value.Split(',');
            foreach (string part in parts)
            {
                string toolId = part.Trim();
                if (toolId.Length != 0)
                {
                    result.Add(toolId);
                }
            }
            return result;
        }

        private void LayoutRdpHost()
        {
            if (_viewerPanel == null || _rdpHost == null)
            {
                return;
            }
            int availableWidth = _viewerPanel.ClientSize.Width;
            int availableHeight = _viewerPanel.ClientSize.Height;
            if (availableWidth <= 0
                || availableHeight <= 0
                || _desktopWidth <= 0
                || _desktopHeight <= 0)
            {
                return;
            }

            double scale = Math.Min(
                (double)availableWidth / _desktopWidth,
                (double)availableHeight / _desktopHeight);
            // 永远不把控件放大到超过会话分辨率。控件比远端画面大时，多出来的
            // 部分由 OCX 自己绘制成浅灰/白底，而 AxHost.BackColor 到不了被宿主
            // 的控件，我们无法改它。控件恰好等于（或小于）会话尺寸时 OCX 内部
            // 没有富余区域，所有留白都落在黑色的 _viewerPanel 上。
            // SmartSizing 仍然保留：窗口比 1080p 小时负责等比缩小填满控件。
            scale = Math.Min(scale, 1.0);
            int width = Math.Max(
                1,
                Math.Min(
                    availableWidth,
                    (int)Math.Round(_desktopWidth * scale)));
            int height = Math.Max(
                1,
                Math.Min(
                    availableHeight,
                    (int)Math.Round(_desktopHeight * scale)));
            _rdpHost.SetBounds(
                (availableWidth - width) / 2,
                (availableHeight - height) / 2,
                width,
                height);

            // 按内容去重上报，用来确认留白究竟落在控件外（黑）还是控件内（灰）。
            string layout = "panel=" + availableWidth + "x" + availableHeight
                + " control=" + width + "x" + height
                + " session=" + _desktopWidth + "x" + _desktopHeight
                + " smart=" + (_smartSizingActive ? "on" : "off");
            if (layout != _lastLayoutReport)
            {
                _lastLayoutReport = layout;
                Send("rdp-diagnostic\tlayout\t" + layout);
            }
        }

        private void ApplyTheme(bool dark)
        {
            _darkTheme = dark;
            Color background = dark
                ? Color.FromArgb(31, 31, 31)
                : Color.White;
            Color foreground = dark
                ? Color.FromArgb(245, 245, 245)
                : Color.FromArgb(30, 30, 30);
            _toolbar.BackColor = background;
            _toolbar.ForeColor = foreground;
            _toolbar.Renderer = new ToolStripProfessionalRenderer(
                new CloneToolStripColorTable(dark));
            foreach (ToolStripItem item in _toolbar.Items)
            {
                item.BackColor = background;
                item.ForeColor = foreground;
            }
            UpdateToolButtonColors();
            ApplyTitleBarTheme();
            _toolbar.Invalidate();
        }

        private void UpdateToolButtonColors()
        {
            Color foreground = _darkTheme
                ? Color.FromArgb(245, 245, 245)
                : Color.FromArgb(30, 30, 30);
            _muteButton.ForeColor = _muteButton.Checked
                ? Color.White
                : foreground;
            _inputButton.ForeColor = _inputButton.Checked
                ? Color.White
                : foreground;
        }

        private void ApplyTitleBarTheme()
        {
            if (!IsHandleCreated)
            {
                return;
            }
            int enabled = _darkTheme ? 1 : 0;
            try
            {
                int result = NativeMethods.DwmSetWindowAttribute(
                    Handle,
                    NativeMethods.DwmUseImmersiveDarkMode,
                    ref enabled,
                    sizeof(int));
                if (result != 0)
                {
                    NativeMethods.DwmSetWindowAttribute(
                        Handle,
                        NativeMethods.DwmUseImmersiveDarkModeBefore20H1,
                        ref enabled,
                        sizeof(int));
                }
            }
            catch (DllNotFoundException)
            {
            }
            catch (EntryPointNotFoundException)
            {
            }
        }

        private void UpdateToolbarVisibility()
        {
            bool anyVisible = false;
            foreach (ToolStripItem item in _toolbar.Items)
            {
                if (item.Available)
                {
                    anyVisible = true;
                    break;
                }
            }
            _toolbar.Visible = anyVisible;
        }

        private void SetToolVisible(string toolId, bool visible)
        {
            ToolStripButton button;
            if (!_toolButtons.TryGetValue(toolId, out button))
            {
                return;
            }
            button.Available = visible;
            UpdateToolbarVisibility();
            LayoutRdpHost();
        }

        private void SetUserMuted(bool muted)
        {
            _userMuted = muted;
            _muteButton.Checked = muted;
            UpdateToolButtonColors();
            ApplyEffectiveMute();
            SendToolState("mute", muted);
        }

        private void ApplyEffectiveMute(bool refreshEndpoint = false)
        {
            bool muted = _userMuted || !_showRequested;
            bool applied = refreshEndpoint
                ? _audioSessionController.RefreshMuted(muted)
                : _audioSessionController.SetMuted(muted);
            if (applied)
            {
                _audioFailureReported = false;
                _lastAudioFailureReport = null;
                _nextAudioRetryUtc = muted
                    ? DateTime.UtcNow.AddSeconds(1)
                    : DateTime.MinValue;
                return;
            }

            _nextAudioRetryUtc = DateTime.UtcNow.AddSeconds(2);
            _audioFailureReported = true;
            string detail = _audioSessionController.LastError;
            string report = "failed"
                + " want=" + (muted ? "mute" : "unmute")
                + " tracked=" + _audioSessionController.TrackedEndpointCount
                + " detail=" + (string.IsNullOrEmpty(detail) ? "none" : detail);
            // 按内容去重而不是只报一次：失败的静音和失败的取消静音是两种
            // 故障，只报首次会把后者完全隐藏（正是这次无法定位的原因）。
            if (report != _lastAudioFailureReport)
            {
                _lastAudioFailureReport = report;
                Send("rdp-diagnostic\taudio-mute\t" + report);
            }
        }

        private void SetInputBlocked(bool blocked)
        {
            _inputBlocked = blocked;
            _inputButton.Checked = blocked;
            UpdateToolButtonColors();
            ApplyInputBlocked();
            SendToolState("input", blocked);
        }

        private void ApplyInputBlocked()
        {
            if (_inputBlocked)
            {
                ActiveControl = _toolbar;
                _toolbar.Focus();
            }
            _rdpHost.SetInputBlocked(_inputBlocked);
        }

        private void SendToolState(string toolId, bool enabled)
        {
            Send(
                "tool-state\t"
                + toolId
                + "\t"
                + (enabled ? "1" : "0"));
        }

        private void RestoreInitialDisplaySettings()
        {
            if (!_initialDisplaySuppressed)
            {
                return;
            }
            _initialDisplaySuppressed = false;
            Opacity = 1;
            ShowInTaskbar = true;
        }

        private void SetDesktopVisible(bool visible)
        {
            if (visible)
            {
                RestoreInitialDisplaySettings();
                _showRequested = true;
                ApplyEffectiveMute();
                Show();
                FormWindowState restoreState = _windowStateBeforeHide;
                if (restoreState == FormWindowState.Minimized)
                {
                    restoreState = FormWindowState.Normal;
                }
                WindowState = restoreState;
                BringToFront();
                Activate();
                ApplyInputBlocked();
                Send("shown");
                return;
            }

            if (WindowState != FormWindowState.Minimized)
            {
                _windowStateBeforeHide = WindowState;
            }
            _showRequested = false;
            ApplyEffectiveMute();
            Hide();
            RestoreInitialDisplaySettings();
            Send("hidden");
        }

        private void OnShown(object sender, EventArgs eventArgs)
        {
            try
            {
                Send("rdp-diagnostic\thost-lifecycle\tshown");
                FlushPendingUiCommands();
                if (!_showRequested && Visible)
                {
                    SetDesktopVisible(false);
                }
                uint existingSessionId;
                bool childSessionRead = NativeMethods.WTSGetChildSessionId(
                    out existingSessionId);
                if (childSessionRead
                    && existingSessionId != NativeMethods.NoChildSessionId)
                {
                    throw new InvalidOperationException(
                        "检测到已有 Child Session，AALC 拒绝接管。");
                }
                if (!childSessionRead
                    && Marshal.GetLastWin32Error() != NativeMethods.ErrorNotFound)
                {
                    throw new InvalidOperationException(
                        "启动前无法确认 Child Session 为空。");
                }
                bool childSessionsEnabled;
                if (!NativeMethods.WTSIsChildSessionsEnabled(
                    out childSessionsEnabled))
                {
                    throw new InvalidOperationException(
                        "无法读取 Windows Child Session 启用状态。");
                }
                if (!childSessionsEnabled)
                {
                    throw new InvalidOperationException(
                        "Windows Child Session 尚未启用。");
                }
                Send("rdp-diagnostic\tchild-sessions-enabled\t1");
                StartRdpConnection();
                _statusTimer.Start();
            }
            catch (Exception exception)
            {
                SendError("启动 RDP Child Session 失败", exception);
            }
        }

        private void PollConnectionState(object sender, EventArgs eventArgs)
        {
            if (_logoffStarted)
            {
                return;
            }
            try
            {
                if ((_audioFailureReported
                        || _userMuted
                        || !_showRequested)
                    && DateTime.UtcNow >= _nextAudioRetryUtc)
                {
                    ApplyEffectiveMute(true);
                }
                int connected = _rdpHost.ConnectedState;
                if (_retryAtUtc.HasValue)
                {
                    if (DateTime.UtcNow < _retryAtUtc.Value)
                    {
                        return;
                    }
                    if (connected != 0)
                    {
                        _rdpHost.DisconnectSession();
                        _retryAtUtc = DateTime.UtcNow.AddMilliseconds(250);
                        return;
                    }
                    _retryAtUtc = null;
                    StartRdpConnection();
                    return;
                }

                if (connected == 1 && _loginCompleted && !HasReportedConnected())
                {
                    if (!TryConfirmAndReportOwnedChildSession())
                    {
                        Send(
                            "rdp-diagnostic\tpoll-session-id\tunavailable-"
                            + Marshal.GetLastWin32Error());
                    }
                }
                else if (connected == 0 && HasReportedConnected())
                {
                    lock (_sessionLock)
                    {
                        _reportedConnected = false;
                    }
                    Send("rdp-disconnected\t" + _rdpHost.ExtendedDisconnectReason);
                }
            }
            catch (Exception exception)
            {
                SendError("读取 RDP Child Session 状态失败", exception);
            }
        }

        private void StartRdpConnection()
        {
            if (_logoffStarted)
            {
                return;
            }
            int generation = Interlocked.Increment(ref _connectionGeneration);
            _loginCompleted = false;
            lock (_sessionLock)
            {
                if (!_ownedSessionId.HasValue)
                {
                    _candidateSessionId = null;
                    _ownershipFailed = false;
                }
            }
            Thread discoveryThread = new Thread(new ThreadStart(
                delegate { DiscoverCandidateChildSession(generation); }));
            discoveryThread.IsBackground = true;
            discoveryThread.Name = "AALC Child Session Discovery";
            discoveryThread.Start();
            if (!string.IsNullOrEmpty(_startProgram))
            {
                Send("rdp-diagnostic\tstart-program\tminimal-shell");
            }
            _rdpHost.ConnectToChildSession(
                _desktopWidth,
                _desktopHeight,
                _rdpPort,
                _connectingText,
                _disconnectedText,
                _startProgram,
                _startWorkDir);
            ApplyInputBlocked();
            ApplyEffectiveMute();
        }

        private void OnRdpLoginCompleted(object sender, EventArgs eventArgs)
        {
            _loginCompleted = true;
            _retryAtUtc = null;
            _smartSizingActive = _rdpHost.ApplySmartSizing();
            Send(
                "rdp-diagnostic\tsmart-sizing\t"
                + (_smartSizingActive ? "on" : "off"));
            Send(
                "rdp-diagnostic\taudio-redirection\tmode="
                + _rdpHost.GetAudioRedirectionMode());
            // 音频通道此时已建立，客户端渲染流也已就绪，这时清理上次遗留的
            // 静音才不会和 mstscax 抢音频设备的初始化。
            _audioSessionController.ClearStaleMutes();
            LayoutRdpHost();
            ApplyInputBlocked();
            ApplyEffectiveMute();
            if (!TryConfirmAndReportOwnedChildSession())
            {
                Send(
                    "rdp-diagnostic\tlogin-complete-session-id\tunavailable-"
                    + Marshal.GetLastWin32Error());
                int generation = Interlocked.CompareExchange(
                    ref _connectionGeneration,
                    0,
                    0);
                Thread confirmationThread = new Thread(new ThreadStart(
                    delegate { ConfirmOwnedChildSession(generation); }));
                confirmationThread.IsBackground = true;
                confirmationThread.Name = "AALC Child Session Confirmation";
                confirmationThread.Start();
            }
            Send("rdp-login-complete");
        }

        private void DiscoverCandidateChildSession(int generation)
        {
            DateTime deadline = DateTime.UtcNow.AddSeconds(90);
            while (DateTime.UtcNow < deadline)
            {
                if (_logoffStarted)
                {
                    return;
                }
                if (generation != Interlocked.CompareExchange(
                    ref _connectionGeneration,
                    0,
                    0))
                {
                    return;
                }
                if (TryObserveCandidateChildSession())
                {
                    return;
                }
                Thread.Sleep(100);
            }
            if (!_logoffStarted)
            {
                Send("rdp-diagnostic\tsession-discovery\ttimeout");
            }
        }

        private bool TryObserveCandidateChildSession()
        {
            uint sessionId;
            if (!NativeMethods.WTSGetChildSessionId(out sessionId)
                || sessionId == NativeMethods.NoChildSessionId)
            {
                return false;
            }

            bool observed = false;
            lock (_sessionLock)
            {
                if (!_candidateSessionId.HasValue)
                {
                    _candidateSessionId = sessionId;
                    observed = true;
                }
                else if (_candidateSessionId.Value != sessionId)
                {
                    return false;
                }
            }
            if (observed)
            {
                Send("rdp-diagnostic\tcandidate-session-id\t" + sessionId);
                Send("rdp-transport-connected");
            }
            return true;
        }

        private void ConfirmOwnedChildSession(int generation)
        {
            DateTime deadline = DateTime.UtcNow.AddSeconds(10);
            while (DateTime.UtcNow < deadline)
            {
                if (generation != Interlocked.CompareExchange(
                    ref _connectionGeneration,
                    0,
                    0))
                {
                    return;
                }
                if (TryConfirmAndReportOwnedChildSession())
                {
                    return;
                }
                Thread.Sleep(100);
            }
            if (!_logoffStarted)
            {
                Send("rdp-diagnostic\tsession-confirmation\ttimeout");
            }
        }

        private bool TryConfirmAndReportOwnedChildSession()
        {
            uint? sessionToReport = null;
            string ownershipError = null;
            uint sessionId;
            if (!NativeMethods.WTSGetChildSessionId(out sessionId)
                || sessionId == NativeMethods.NoChildSessionId)
            {
                return false;
            }

            lock (_sessionLock)
            {
                if (_ownershipFailed)
                {
                    return true;
                }
                if (_ownedSessionId.HasValue)
                {
                    if (!_reportedConnected && !_logoffStarted)
                    {
                        _reportedConnected = true;
                        sessionToReport = _ownedSessionId.Value;
                    }
                }
                else
                {
                    if (_candidateSessionId.HasValue
                        && _candidateSessionId.Value != sessionId)
                    {
                        _ownershipFailed = true;
                        ownershipError =
                            "RDP 登录完成后的 Child Session 与连接期间观察值不一致。";
                    }
                    else
                    {
                        _candidateSessionId = sessionId;
                        _ownedSessionId = sessionId;
                        _ownedSessionReady.Set();
                        if (!_logoffStarted)
                        {
                            _reportedConnected = true;
                            sessionToReport = sessionId;
                        }
                    }
                }
            }

            if (ownershipError != null)
            {
                Send(
                    "rdp-failed\townership\t0\t0\t"
                    + Encode(ownershipError));
                return false;
            }
            if (sessionToReport.HasValue)
            {
                Send("rdp-connected\t" + sessionToReport.Value);
                if (!_showRequested && Visible)
                {
                    try
                    {
                        BeginInvoke(new Action(delegate
                        {
                            if (!_showRequested && !_logoffStarted)
                            {
                                SetDesktopVisible(false);
                            }
                        }));
                    }
                    catch (InvalidOperationException)
                    {
                    }
                }
            }
            return true;
        }

        private bool HasReportedConnected()
        {
            lock (_sessionLock)
            {
                return _reportedConnected;
            }
        }

        private void OnRdpConnectionFailed(
            object sender,
            RdpFailureEventArgs eventArgs)
        {
            if (_logoffStarted)
            {
                return;
            }
            _loginCompleted = false;
            Interlocked.Increment(ref _connectionGeneration);
            if (!HasReportedConnected()
                && eventArgs.Stage == "connect"
                && _connectionRetryCount < InitialConnectionRetryCount)
            {
                _connectionRetryCount++;
                int delaySeconds = 1 << (_connectionRetryCount - 1);
                _retryAtUtc = DateTime.UtcNow.AddSeconds(delaySeconds);
                Send(
                    "rdp-retrying\t"
                    + _connectionRetryCount
                    + "\t"
                    + delaySeconds
                    + "\t"
                    + eventArgs.Stage
                    + "\t"
                    + eventArgs.ErrorCode
                    + "\t"
                    + eventArgs.ExtendedErrorCode
                    + "\t"
                    + Encode(eventArgs.Description));
                return;
            }

            lock (_sessionLock)
            {
                _reportedConnected = false;
            }
            Send(
                "rdp-failed\t"
                + eventArgs.Stage
                + "\t"
                + eventArgs.ErrorCode
                + "\t"
                + eventArgs.ExtendedErrorCode
                + "\t"
                + Encode(eventArgs.Description));
        }

        private void ReadCommands()
        {
            try
            {
                string line;
                while ((line = _reader.ReadLine()) != null)
                {
                    string command = line.Trim();
                    if (command.Length == 0)
                    {
                        continue;
                    }
                    if (command == "logoff" || command == "shutdown")
                    {
                        LogoffAndExitFromWorker();
                        return;
                    }
                    DispatchUiCommand(command);
                }
            }
            catch (IOException)
            {
            }
            catch (ObjectDisposedException)
            {
            }
            finally
            {
                LogoffAndExitFromWorker();
            }
        }

        private void DispatchUiCommand(string command)
        {
            if (!IsSupportedUiCommand(command))
            {
                return;
            }
            lock (_uiCommandLock)
            {
                if (_logoffStarted)
                {
                    return;
                }
                if (command == "show" || command == "hide")
                {
                    _showRequested = command == "show";
                }
                if (!IsHandleCreated)
                {
                    _pendingUiCommands.Enqueue(command);
                    return;
                }
            }
            try
            {
                BeginInvoke(new Action(delegate
                {
                    if (!_logoffStarted)
                    {
                        ExecuteCommand(command);
                    }
                }));
            }
            catch (InvalidOperationException)
            {
                if (!IsDisposed && !_logoffStarted)
                {
                    lock (_uiCommandLock)
                    {
                        _pendingUiCommands.Enqueue(command);
                    }
                }
            }
        }

        private static bool IsSupportedUiCommand(string command)
        {
            if (command == "show" || command == "hide")
            {
                return true;
            }
            string[] parts = command.Split(new char[] { '\t' });
            if (parts.Length == 2 && parts[0] == "theme")
            {
                return parts[1] == "dark" || parts[1] == "light";
            }
            if (parts.Length == 3 && parts[0] == "tool-visible")
            {
                bool knownTool = parts[1] == "mute" || parts[1] == "input";
                bool knownState = parts[2] == "0" || parts[2] == "1";
                return knownTool && knownState;
            }
            if (parts.Length == 6 && parts[0] == "ui-text")
            {
                return true;
            }
            return false;
        }

        private void FlushPendingUiCommands()
        {
            Queue<string> commands = new Queue<string>();
            lock (_uiCommandLock)
            {
                while (_pendingUiCommands.Count != 0)
                {
                    commands.Enqueue(_pendingUiCommands.Dequeue());
                }
            }
            while (commands.Count != 0 && !_logoffStarted)
            {
                ExecuteCommand(commands.Dequeue());
            }
        }

        private void LogoffAndExitFromWorker()
        {
            lock (_logoffLock)
            {
                if (_logoffStarted)
                {
                    return;
                }
                _logoffStarted = true;
            }
            Interlocked.Increment(ref _connectionGeneration);
            if (!RestoreAudioBeforeExit())
            {
                Send("rdp-diagnostic\taudio-restore\tfailed");
            }
            _ownedSessionReady.Wait(TimeSpan.FromSeconds(2));
            if (!IsHandleCreated)
            {
                _activeXDisconnectSucceeded = true;
                _activeXDisconnectCompleted.Set();
            }
            try
            {
                if (IsHandleCreated)
                {
                    BeginInvoke(new Action(delegate
                    {
                        try
                        {
                            _retryAtUtc = null;
                            _statusTimer.Stop();
                            _activeXDisconnectSucceeded =
                                _rdpHost.DisconnectSession();
                        }
                        catch (Exception exception)
                        {
                            SendError("停止 RDP ActiveX 失败", exception);
                        }
                        finally
                        {
                            _activeXDisconnectCompleted.Set();
                        }
                    }));
                }
            }
            catch (InvalidOperationException)
            {
            }
            bool activeXDisconnected = _activeXDisconnectCompleted.Wait(
                TimeSpan.FromSeconds(2))
                && _activeXDisconnectSucceeded;

            uint? ownedSessionId;
            lock (_sessionLock)
            {
                ownedSessionId = _ownedSessionId;
            }

            bool loggedOff = activeXDisconnected;
            if (!activeXDisconnected)
            {
                Send("error\t" + Encode(
                    "RDP ActiveX 未确认已停止，拒绝报告 Child Session 注销完成。"));
            }
            uint currentSessionId;
            bool childSessionRead = NativeMethods.WTSGetChildSessionId(
                out currentSessionId);
            int childSessionReadError = childSessionRead
                ? 0
                : Marshal.GetLastWin32Error();
            if (ownedSessionId.HasValue)
            {
                if (childSessionRead
                    && currentSessionId == ownedSessionId.Value)
                {
                    if (!NativeMethods.WTSLogoffSession(
                        IntPtr.Zero,
                        ownedSessionId.Value,
                        false))
                    {
                        int error = Marshal.GetLastWin32Error();
                        Send("error\t" + Encode(
                            "注销 Child Session 失败（Win32 错误 "
                            + error
                            + "）"));
                        loggedOff = false;
                    }
                }
                else if (childSessionRead
                    && currentSessionId != NativeMethods.NoChildSessionId)
                {
                    Send("error\t" + Encode(
                        "当前 Child Session 已不属于 AALC，拒绝注销。"));
                    loggedOff = false;
                }
                else if (!childSessionRead
                    && childSessionReadError != NativeMethods.ErrorNotFound)
                {
                    Send("error\t" + Encode(
                        "读取 Child Session 失败（Win32 错误 "
                        + childSessionReadError
                        + "）"));
                    loggedOff = false;
                }
            }
            else if (childSessionRead
                && currentSessionId != NativeMethods.NoChildSessionId)
            {
                Send("error\t" + Encode(
                    "RDP 宿主尚未确认 Child Session 所有权，拒绝注销。"));
                loggedOff = false;
            }
            else if (!childSessionRead
                && childSessionReadError != NativeMethods.ErrorNotFound)
            {
                Send("error\t" + Encode(
                    "读取 Child Session 失败（Win32 错误 "
                    + childSessionReadError
                    + "）"));
                loggedOff = false;
            }

            if (loggedOff)
            {
                Send("logged-off");
            }
            Environment.Exit(loggedOff ? 0 : 2);
        }

        private bool RestoreAudioBeforeExit()
        {
            _audioRestoreCompleted.Reset();
            _audioRestoreSucceeded = false;
            if (_audioSessionController == null)
            {
                // 构造尚未走到音频初始化，没有任何静音是本进程设置的。
                return true;
            }
            if (!IsHandleCreated)
            {
                return _audioSessionController.SetMuted(false);
            }
            try
            {
                BeginInvoke(new Action(delegate
                {
                    try
                    {
                        _audioRestoreSucceeded =
                            _audioSessionController.SetMuted(false);
                    }
                    finally
                    {
                        _audioRestoreCompleted.Set();
                    }
                }));
            }
            catch (InvalidOperationException)
            {
                return false;
            }
            return _audioRestoreCompleted.Wait(
                TimeSpan.FromSeconds(2))
                && _audioRestoreSucceeded;
        }

        private void ExecuteCommand(string command)
        {
            if (_logoffStarted)
            {
                return;
            }
            if (command == "show")
            {
                SetDesktopVisible(true);
            }
            else if (command == "hide")
            {
                SetDesktopVisible(false);
                return;
            }

            string[] parts = command.Split(new char[] { '\t' });
            if (parts.Length == 2 && parts[0] == "theme")
            {
                ApplyTheme(parts[1] == "dark");
            }
            else if (parts.Length == 3 && parts[0] == "tool-visible")
            {
                SetToolVisible(parts[1], parts[2] == "1");
            }
            else if (parts.Length == 6 && parts[0] == "ui-text")
            {
                string windowTitle;
                string muteText;
                string inputText;
                string connectingText;
                string disconnectedText;
                if (TryDecode(parts[1], out windowTitle)
                    && TryDecode(parts[2], out muteText)
                    && TryDecode(parts[3], out inputText)
                    && TryDecode(parts[4], out connectingText)
                    && TryDecode(parts[5], out disconnectedText))
                {
                    Text = windowTitle;
                    SetToolButtonText(_muteButton, muteText);
                    SetToolButtonText(_inputButton, inputText);
                    _connectingText = connectingText;
                    _disconnectedText = disconnectedText;
                    _rdpHost.UpdateStatusTexts(
                        connectingText,
                        disconnectedText);
                    _toolbar.PerformLayout();
                }
            }
        }

        private void OnFormClosing(object sender, FormClosingEventArgs eventArgs)
        {
            if (eventArgs.CloseReason == CloseReason.WindowsShutDown)
            {
                return;
            }
            eventArgs.Cancel = true;
            SetDesktopVisible(false);
        }

        private void SendError(string operation, Exception exception)
        {
            Exception actual = exception.GetBaseException();
            Send("error\t" + Encode(operation + "：" + actual.Message));
        }

        private static string Encode(string value)
        {
            return Convert.ToBase64String(Encoding.UTF8.GetBytes(value ?? ""));
        }

        private static bool TryDecode(string value, out string decoded)
        {
            try
            {
                decoded = Encoding.UTF8.GetString(
                    Convert.FromBase64String(value));
                return true;
            }
            catch (FormatException)
            {
                decoded = "";
                return false;
            }
        }

        private void Send(string message)
        {
            lock (_writeLock)
            {
                try
                {
                    _writer.WriteLine(message);
                }
                catch (IOException)
                {
                }
                catch (ObjectDisposedException)
                {
                }
            }
        }
    }

    internal static class Program
    {
        private static string Argument(string[] args, string name, string fallback)
        {
            for (int index = 0; index + 1 < args.Length; index++)
            {
                if (string.Equals(args[index], name, StringComparison.Ordinal))
                {
                    return args[index + 1];
                }
            }
            return fallback;
        }

        [STAThread]
        private static int Main(string[] args)
        {
            string pipeName = Argument(args, "--pipe-name", "");
            int desktopWidth;
            int desktopHeight;
            int rdpPort;
            bool showOnStart;
            bool darkTheme;
            string windowTitle = Argument(args, "--window-title", "AALC 桌面分身");
            string visibleTools = Argument(
                args,
                "--visible-tools",
                "mute,input");
            string muteText = Argument(args, "--mute-text", "关闭声音");
            string inputText = Argument(args, "--input-text", "关闭输入");
            string connectingText = Argument(
                args,
                "--connecting-text",
                "正在创建 AALC 桌面分身...");
            string disconnectedText = Argument(
                args,
                "--disconnected-text",
                "AALC 桌面分身已断开");
            string startProgram = Argument(args, "--start-program", "");
            string startWorkDir = Argument(args, "--start-workdir", "");
            if (pipeName.Length == 0
                || !int.TryParse(Argument(args, "--width", "1920"), out desktopWidth)
                || !int.TryParse(Argument(args, "--height", "1080"), out desktopHeight)
                || !int.TryParse(Argument(args, "--rdp-port", "3389"), out rdpPort)
                || !bool.TryParse(Argument(args, "--show", "true"), out showOnStart)
                || !bool.TryParse(Argument(args, "--dark", "false"), out darkTheme))
            {
                return 2;
            }

            try
            {
                using (NamedPipeClientStream pipe = new NamedPipeClientStream(
                    ".",
                    pipeName,
                    PipeDirection.InOut,
                    PipeOptions.Asynchronous))
                {
                    pipe.Connect(10000);
                    Application.EnableVisualStyles();
                    Application.SetCompatibleTextRenderingDefault(false);
                    Application.Run(new HostForm(
                        pipe,
                        desktopWidth,
                        desktopHeight,
                        rdpPort,
                        showOnStart,
                        windowTitle,
                        connectingText,
                        disconnectedText,
                        startProgram,
                        startWorkDir,
                        darkTheme,
                        visibleTools,
                        muteText,
                        inputText));
                }
                return 0;
            }
            catch (Exception exception)
            {
                // 构造期失败（管道超时、mstscax 未注册、ActiveX 创建失败等）
                // 会在 root 侧表现为"宿主意外退出（exit=1）"，若此处不落盘，
                // 首发环境故障将完全无法诊断。与 child 的 crash capture 对应。
                try
                {
                    string baseDir = Path.Combine(
                        Environment.GetFolderPath(
                            Environment.SpecialFolder.LocalApplicationData),
                        "AALC",
                        "desktop-clone");
                    Directory.CreateDirectory(baseDir);
                    string crashFile = Path.Combine(
                        baseDir,
                        "host-startup-error.txt");
                    File.AppendAllText(
                        crashFile,
                        "\n===== " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                        + " =====\n"
                        + "commandline: " + Environment.CommandLine + "\n"
                        + exception.ToString() + "\n");
                }
                catch
                {
                }
                return 1;
            }
        }
    }
}
