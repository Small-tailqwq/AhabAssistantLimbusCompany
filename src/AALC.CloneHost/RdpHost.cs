using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace AALC.CloneHost
{
    internal static class NativeMethods
    {
        internal const uint NoChildSessionId = 0xFFFFFFFF;
        internal const int ErrorNotFound = 1168;
        internal const int DwmUseImmersiveDarkMode = 20;
        internal const int DwmUseImmersiveDarkModeBefore20H1 = 19;
        internal const int DwmBorderColor = 34;
        internal const int DwmCaptionColor = 35;
        internal const int DwmTextColor = 36;

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
        internal event EventHandler Disconnected;

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
            string disconnectedText)
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
            object ignoreServerMoves = true;
            try
            {
                extendedSettings.set_Property("IgnoreServerGeneratedMouseMoves", ref ignoreServerMoves);
                if (!Convert.ToBoolean(extendedSettings.get_Property("IgnoreServerGeneratedMouseMoves")))
                {
                    throw new InvalidOperationException("RDP ActiveX 未接受鼠标位置隔离设置。");
                }
            }
            catch (COMException exception)
            {
                throw new InvalidOperationException("当前 RDP 控件不支持鼠标位置隔离。", exception);
            }
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
            EventHandler handler = Disconnected;
            if (handler != null)
            {
                handler(this, EventArgs.Empty);
            }
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
}
