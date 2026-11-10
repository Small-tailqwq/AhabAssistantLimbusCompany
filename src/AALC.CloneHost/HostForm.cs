using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace AALC.CloneHost
{
    internal sealed class HostForm : Form
    {
        private const int InitialConnectionRetryCount = 3;
        private readonly RdpHost _rdpHost;
        private readonly Panel _viewerPanel;
        private readonly HostToolbar _toolbar;
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
        private readonly ManualResetEventSlim _rdpDisconnected =
            new ManualResetEventSlim(false);
        private readonly ManualResetEventSlim _audioRestoreCompleted =
            new ManualResetEventSlim(false);
        private readonly int _desktopWidth;
        private readonly int _desktopHeight;
        private readonly int _rdpPort;
        private volatile bool _showRequested;
        private readonly string _connectingText;
        private readonly string _disconnectedText;
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
        private bool _userMuted;
        private bool _inputBlocked;
        private bool _audioFailureReported;
        private bool _audioReady;
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
            bool showOnStart)
        {
            _desktopWidth = desktopWidth;
            _desktopHeight = desktopHeight;
            _rdpPort = rdpPort;
            _showRequested = showOnStart;
            _connectingText = "正在创建桌面分身…";
            _disconnectedText = "桌面分身已断开";
            _reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, true);
            _writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true);
            _writer.AutoFlush = true;
            Send("hello\trdp-host\t1");
            Send("rdp-diagnostic\thost-bootstrap\tpipe-ready");

            Text = "AAALC 桌面分身";
            Width = 1280;
            Height = 780;
            MinimumSize = new Size(640, 420);
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;
            BackColor = HostPalette.SurfaceWindow;
            ForeColor = HostPalette.TextPrimary;
            Font = HostPalette.BodyFont;
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
            _rdpHost.Disconnected += delegate { _rdpDisconnected.Set(); };
            _viewerPanel = new Panel();
            _viewerPanel.BackColor = HostPalette.SurfaceInset;
            _viewerPanel.Dock = DockStyle.Fill;
            _viewerPanel.Controls.Add(_rdpHost);
            _viewerPanel.ClientSizeChanged += delegate { LayoutRdpHost(); };

            _toolbar = new HostToolbar();
            _toolbar.MuteClicked += delegate { SetUserMuted(!_userMuted); };
            _toolbar.InputClicked += delegate { SetInputBlocked(!_inputBlocked); };

            Controls.Add(_viewerPanel);
            Controls.Add(_toolbar);
            LayoutRdpHost();
            Send("rdp-diagnostic\thost-bootstrap\tactivex-added");

            _audioSessionController = new AudioSessionController();
            // 注意：这里不要碰 WASAPI。清理遗留静音被推迟到 RDP 登录完成之后
            // （OnRdpLoginCompleted），因为在 mstscax 建立自己的音频渲染流之前
            // 就创建本进程的音频会话，可能干扰它打开输出设备。
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
            readerThread.Name = "AAALC Clone Host Commands";
            readerThread.Start();
            Send("rdp-diagnostic\thost-bootstrap\tform-ready");
        }

        // 隐藏启动时窗口仍要走一次显示流程，不能抢走主桌面的焦点。
        protected override bool ShowWithoutActivation
        {
            get { return _initialDisplaySuppressed; }
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

        private void ApplyTitleBarTheme()
        {
            if (!IsHandleCreated)
            {
                return;
            }
            // 深色标题栏全系统可用；标题栏底色只有 Windows 11 支持，旧系统保留深色默认值。
            int enabled = 1;
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
                SetTitleBarColor(NativeMethods.DwmCaptionColor, HostPalette.SurfaceWindow);
                SetTitleBarColor(NativeMethods.DwmBorderColor, HostPalette.BorderSubtle);
                SetTitleBarColor(NativeMethods.DwmTextColor, HostPalette.TextPrimary);
            }
            catch (DllNotFoundException)
            {
            }
            catch (EntryPointNotFoundException)
            {
            }
        }

        private void SetTitleBarColor(int attribute, Color color)
        {
            int colorRef = ColorTranslator.ToWin32(color);
            NativeMethods.DwmSetWindowAttribute(Handle, attribute, ref colorRef, sizeof(int));
        }

        private void SetUserMuted(bool muted)
        {
            _userMuted = muted;
            _toolbar.Muted = muted;
            ApplyEffectiveMute();
            SendToolState("mute", muted);
        }

        private void ApplyEffectiveMute(bool refreshEndpoint = false)
        {
            if (!_audioReady)
            {
                return;
            }
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
            _toolbar.InputBlocked = blocked;
            ApplyInputBlocked();
            SendToolState("input", blocked);
        }

        private void ApplyInputBlocked()
        {
            if (_inputBlocked)
            {
                _toolbar.TakeFocus();
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
            discoveryThread.Name = "AAALC Child Session Discovery";
            discoveryThread.Start();
            _rdpHost.ConnectToChildSession(
                _desktopWidth,
                _desktopHeight,
                _rdpPort,
                _connectingText,
                _disconnectedText);
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
            _audioReady = true;
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
                confirmationThread.Name = "AAALC Child Session Confirmation";
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
            if (parts.Length == 3 && parts[0] == "tool-set")
            {
                bool knownTool = parts[1] == "mute" || parts[1] == "input";
                bool knownState = parts[2] == "0" || parts[2] == "1";
                return knownTool && knownState;
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
            _ownedSessionReady.Wait(TimeSpan.FromSeconds(2));
            if (!IsHandleCreated)
            {
                _activeXDisconnectSucceeded = true;
                _activeXDisconnectCompleted.Set();
                _rdpDisconnected.Set();
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
                            bool alreadyDisconnected = _rdpHost.ConnectedState == 0;
                            _rdpDisconnected.Reset();
                            _activeXDisconnectSucceeded =
                                _rdpHost.DisconnectSession();
                            if (_activeXDisconnectSucceeded && alreadyDisconnected)
                            {
                                _rdpDisconnected.Set();
                            }
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
                && _activeXDisconnectSucceeded
                && _rdpDisconnected.Wait(TimeSpan.FromSeconds(1));

            if (activeXDisconnected)
            {
                // 断开后仍可能有已缓冲的远端音频，等渲染流停止再恢复音量。
                Thread.Sleep(1500);
                if (!RestoreAudioBeforeExit())
                {
                    Send("rdp-diagnostic\taudio-restore\tfailed");
                }
            }

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
            if (parts.Length == 3 && parts[0] == "tool-set")
            {
                bool enabled = parts[2] == "1";
                if (parts[1] == "mute")
                {
                    SetUserMuted(enabled);
                }
                else
                {
                    SetInputBlocked(enabled);
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
}
