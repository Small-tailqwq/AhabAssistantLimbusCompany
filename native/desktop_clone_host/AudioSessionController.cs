using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;

namespace AALC.DesktopCloneHost
{
    internal enum AudioDataFlow
    {
        Render = 0,
        Capture = 1,
        All = 2
    }

    internal enum AudioEndpointRole
    {
        Console = 0,
        Multimedia = 1,
        Communications = 2
    }

    [ComImport]
    [Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    internal sealed class MMDeviceEnumeratorComObject
    {
    }

    [ComImport]
    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IMMDeviceEnumerator
    {
        [PreserveSig]
        int EnumAudioEndpoints(
            AudioDataFlow dataFlow,
            uint stateMask,
            out IMMDeviceCollection devices);

        [PreserveSig]
        int GetDefaultAudioEndpoint(
            AudioDataFlow dataFlow,
            AudioEndpointRole role,
            out IMMDevice endpoint);

        [PreserveSig]
        int GetDevice(
            [MarshalAs(UnmanagedType.LPWStr)] string id,
            out IMMDevice device);

        [PreserveSig]
        int RegisterEndpointNotificationCallback(IntPtr client);

        [PreserveSig]
        int UnregisterEndpointNotificationCallback(IntPtr client);
    }

    [ComImport]
    // 取自 SDK mmdeviceapi.h。曾误写为 ...-C0A5BC2B2A17，QueryInterface 直接
    // 返回 E_NOINTERFACE，导致端点枚举整体失败、静音功能完全不工作。
    [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IMMDeviceCollection
    {
        [PreserveSig]
        int GetCount(out uint count);

        [PreserveSig]
        int Item(uint index, out IMMDevice device);
    }

    [ComImport]
    [Guid("D666063F-1587-4E43-81F1-B948E807363F")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IMMDevice
    {
        [PreserveSig]
        int Activate(
            ref Guid interfaceId,
            uint classContext,
            IntPtr activationParameters,
            [MarshalAs(UnmanagedType.IUnknown)] out object interfacePointer);

        [PreserveSig]
        int OpenPropertyStore(uint storageAccess, out IntPtr properties);

        [PreserveSig]
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);

        [PreserveSig]
        int GetState(out uint state);
    }

    [ComImport]
    [Guid("BFA971F1-4D5E-40BB-935E-967039BFBEE4")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IAudioSessionManager
    {
        [PreserveSig]
        int GetAudioSessionControl(
            ref Guid audioSessionGuid,
            uint streamFlags,
            out IntPtr sessionControl);

        [PreserveSig]
        int GetSimpleAudioVolume(
            ref Guid audioSessionGuid,
            uint streamFlags,
            out ISimpleAudioVolume audioVolume);
    }

    [ComImport]
    [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface ISimpleAudioVolume
    {
        [PreserveSig]
        int SetMasterVolume(float level, ref Guid eventContext);

        [PreserveSig]
        int GetMasterVolume(out float level);

        [PreserveSig]
        int SetMute(
            [MarshalAs(UnmanagedType.Bool)] bool muted,
            ref Guid eventContext);

        [PreserveSig]
        int GetMute([MarshalAs(UnmanagedType.Bool)] out bool muted);
    }

    internal sealed class AudioSessionController : IDisposable
    {
        private const uint ClassContextAll = 23;
        private const uint DeviceStateActive = 1;
        private static readonly Guid SessionManagerInterfaceId =
            new Guid("BFA971F1-4D5E-40BB-935E-967039BFBEE4");
        private static readonly Guid EventContext =
            new Guid("2EFB3194-0918-4C2A-9D7D-6348B2AF54DC");

        private sealed class EndpointSession
        {
            internal EndpointSession(string deviceId)
            {
                DeviceId = deviceId;
            }

            internal string DeviceId { get; private set; }
            internal bool OriginalMuted { get; set; }
            internal IMMDevice Device { get; set; }
            internal IAudioSessionManager SessionManager { get; set; }
            internal ISimpleAudioVolume Volume { get; set; }

            internal void ReleaseInterfaces()
            {
                ReleaseComObject(Volume);
                ReleaseComObject(SessionManager);
                ReleaseComObject(Device);
                Volume = null;
                SessionManager = null;
                Device = null;
            }
        }

        private readonly Dictionary<string, EndpointSession> _mutedEndpoints =
            new Dictionary<string, EndpointSession>(
                StringComparer.OrdinalIgnoreCase);
        private IMMDeviceEnumerator _enumerator;

        /// <summary>最近一次失败的端点与 HRESULT，用于宿主诊断上报。</summary>
        internal string LastError { get; private set; }

        /// <summary>当前记录在案、由本进程静音的端点数量。</summary>
        internal int TrackedEndpointCount
        {
            get { return _mutedEndpoints.Count; }
        }

        private static string Shorten(string deviceId)
        {
            if (string.IsNullOrEmpty(deviceId) || deviceId.Length <= 24)
            {
                return deviceId;
            }
            return "..." + deviceId.Substring(deviceId.Length - 21);
        }

        internal bool SetMuted(bool muted)
        {
            LastError = null;
            return muted
                ? MuteActiveEndpoints()
                : RestoreMutedEndpoints();
        }

        internal bool RefreshMuted(bool muted)
        {
            return SetMuted(muted);
        }

        /// <summary>
        /// 清除上一次运行崩溃遗留的静音，且只清除本程序设置过的端点。
        /// </summary>
        /// <remarks>
        /// Windows 按应用身份持久化混音器里的静音状态，所以上次异常退出留下的
        /// 静音会带进本次进程的会话。但无条件清空会同时抹掉用户自己在混音器里
        /// 对分身宿主设的静音，因此以落盘标记记录"哪些端点是我们静音的"，
        /// 启动时只恢复这些端点。没有标记就不碰任何设置。
        /// </remarks>
        internal bool ClearStaleMutes()
        {
            // 标记里记录的端点是上次异常退出时确定被我们静音的，优先精确清理。
            List<string> ownedIds = ReadOwnershipMarker();
            bool clearedAll = true;
            foreach (string deviceId in ownedIds)
            {
                if (!ClearEndpointMuteById(deviceId))
                {
                    clearedAll = false;
                }
            }
            if (clearedAll)
            {
                DeleteOwnershipMarker();
            }

            // 无论有没有标记，都要保证本进程自己的会话是未静音的。
            //
            // GetSimpleAudioVolume(Guid.Empty) 取到的始终是"本进程"的音频会话，
            // 所以这里只会动分身宿主自己在混音器里的那一项，不碰任何别的程序。
            // Windows 会把每应用静音持久化到注册表：早期版本静音后没恢复就退出，
            // 会让之后每个宿主进程都继承 mute=true，表现为"分身永远没有声音，
            // 重启也没用"。启动时应用的意图状态必然是未静音（_userMuted 默认
            // false），所以这里无条件清一次，也是历史遗留静音的唯一出口。
            return ClearOwnSessionMutes() && clearedAll;
        }

        private bool ClearOwnSessionMutes()
        {
            // 只处理默认端点。遗留静音（marker 机制出现之前留下的）实际只可能
            // 落在默认端点上，其余端点由 marker 精确覆盖。遍历全部端点会在每个
            // 设备上都创建一个本进程的音频会话，让分身宿主凭空出现在十几个设备
            // 的音量合成器里。
            IMMDevice device = null;
            try
            {
                EnsureEnumerator();
                int result = _enumerator.GetDefaultAudioEndpoint(
                    AudioDataFlow.Render,
                    AudioEndpointRole.Console,
                    out device);
                ThrowIfFailed(result);
                SetEndpointMuteUntracked(device, false);
                return true;
            }
            catch (Exception exception)
            {
                LastError = "startup-unmute: " + exception.Message;
                ReleaseEnumerator();
                return false;
            }
            finally
            {
                ReleaseComObject(device);
            }
        }

        private bool ClearEndpointMuteById(string deviceId)
        {
            for (int attempt = 0; attempt < 2; attempt++)
            {
                IMMDevice device = null;
                try
                {
                    EnsureEnumerator();
                    int result = _enumerator.GetDevice(deviceId, out device);
                    ThrowIfFailed(result);
                    SetEndpointMuteUntracked(device, false);
                    return true;
                }
                catch
                {
                    ReleaseEnumerator();
                    if (attempt != 0)
                    {
                        // 端点可能已被拔出；标记随之作废，不视为失败。
                        return true;
                    }
                }
                finally
                {
                    ReleaseComObject(device);
                }
            }
            return false;
        }

        private static string GetOwnershipMarkerPath()
        {
            string root = Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData);
            return Path.Combine(
                root,
                "AALC",
                "desktop_clone_host_muted.marker");
        }

        private static List<string> ReadOwnershipMarker()
        {
            List<string> ids = new List<string>();
            try
            {
                string path = GetOwnershipMarkerPath();
                if (!File.Exists(path))
                {
                    return ids;
                }
                foreach (string line in File.ReadAllLines(path))
                {
                    string deviceId = line.Trim();
                    if (deviceId.Length != 0)
                    {
                        ids.Add(deviceId);
                    }
                }
            }
            catch
            {
                // 标记只是尽力而为的崩溃恢复线索，读不到就当作没有遗留静音。
                ids.Clear();
            }
            return ids;
        }

        private void WriteOwnershipMarker()
        {
            try
            {
                string path = GetOwnershipMarkerPath();
                if (_mutedEndpoints.Count == 0)
                {
                    DeleteOwnershipMarker();
                    return;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                string[] ids = new string[_mutedEndpoints.Count];
                _mutedEndpoints.Keys.CopyTo(ids, 0);
                File.WriteAllLines(path, ids);
            }
            catch
            {
                // 写不进标记不影响本次运行的静音与恢复，只会丢失崩溃恢复能力。
            }
        }

        private static void DeleteOwnershipMarker()
        {
            try
            {
                string path = GetOwnershipMarkerPath();
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
            catch
            {
            }
        }

        private bool MuteActiveEndpoints()
        {
            for (int attempt = 0; attempt < 2; attempt++)
            {
                IMMDeviceCollection devices = null;
                try
                {
                    EnsureEnumerator();
                    int result = _enumerator.EnumAudioEndpoints(
                        AudioDataFlow.Render,
                        DeviceStateActive,
                        out devices);
                    ThrowIfFailed(result);
                    uint count;
                    result = devices.GetCount(out count);
                    ThrowIfFailed(result);
                    bool mutedAll = true;
                    for (uint index = 0; index < count; index++)
                    {
                        IMMDevice device;
                        result = devices.Item(index, out device);
                        ThrowIfFailed(result);
                        if (!MuteEndpoint(device))
                        {
                            mutedAll = false;
                        }
                    }
                    // 先落盘再返回：崩溃窗口应尽量落在"标记已写"这一侧，
                    // 宁可多清一次已恢复的端点，也不要漏掉真正遗留的静音。
                    WriteOwnershipMarker();
                    return mutedAll;
                }
                catch
                {
                    ReleaseEnumerator();
                    if (attempt != 0)
                    {
                        return false;
                    }
                }
                finally
                {
                    ReleaseComObject(devices);
                }
            }
            return false;
        }

        private bool MuteEndpoint(IMMDevice device)
        {
            EndpointSession session = null;
            string deviceId = null;
            bool createdHere = false;
            try
            {
                int result = device.GetId(out deviceId);
                ThrowIfFailed(result);
                if (!_mutedEndpoints.TryGetValue(
                    deviceId,
                    out session))
                {
                    session = new EndpointSession(deviceId);
                    AttachVolume(session, device);
                    device = null;
                    bool originalMuted;
                    result = session.Volume.GetMute(out originalMuted);
                    ThrowIfFailed(result);
                    session.OriginalMuted = originalMuted;
                    _mutedEndpoints.Add(deviceId, session);
                    createdHere = true;
                }
                else if (session.Volume == null)
                {
                    AttachVolume(session, device);
                    device = null;
                }

                Guid eventContext = EventContext;
                result = session.Volume.SetMute(true, ref eventContext);
                ThrowIfFailed(result);
                return true;
            }
            catch (Exception exception)
            {
                LastError = deviceId == null
                    ? exception.Message
                    : Shorten(deviceId) + ": " + exception.Message;
                if (session != null)
                {
                    session.ReleaseInterfaces();
                    // 只回滚本次新建的记录。一旦某个端点曾被成功静音，它的
                    // 记录就是唯一的恢复依据；这里删掉会让它永久保持静音，
                    // 正好表现为"关掉静音也不恢复声音"。
                    if (createdHere && deviceId != null)
                    {
                        _mutedEndpoints.Remove(deviceId);
                    }
                }
                return false;
            }
            finally
            {
                ReleaseComObject(device);
            }
        }

        private bool RestoreMutedEndpoints()
        {
            bool restoredAll = true;
            List<string> restoredIds = new List<string>();
            foreach (
                KeyValuePair<string, EndpointSession> entry
                in _mutedEndpoints)
            {
                EndpointSession session = entry.Value;
                bool restored = false;
                for (int attempt = 0; attempt < 2 && !restored; attempt++)
                {
                    try
                    {
                        EnsureVolume(session);
                        Guid eventContext = EventContext;
                        int result = session.Volume.SetMute(
                            session.OriginalMuted,
                            ref eventContext);
                        ThrowIfFailed(result);
                        restored = true;
                    }
                    catch (Exception exception)
                    {
                        LastError = "restore " + Shorten(entry.Key)
                            + ": " + exception.Message;
                        session.ReleaseInterfaces();
                        ReleaseEnumerator();
                    }
                }
                if (restored)
                {
                    restoredIds.Add(entry.Key);
                }
                else
                {
                    restoredAll = false;
                }
            }
            foreach (string deviceId in restoredIds)
            {
                EndpointSession session = _mutedEndpoints[deviceId];
                _mutedEndpoints.Remove(deviceId);
                session.ReleaseInterfaces();
            }
            if (restoredIds.Count != 0)
            {
                WriteOwnershipMarker();
            }
            return restoredAll;
        }

        private void EnsureEnumerator()
        {
            if (_enumerator != null)
            {
                return;
            }
            _enumerator = (IMMDeviceEnumerator)(object)
                new MMDeviceEnumeratorComObject();
        }

        private void EnsureVolume(EndpointSession session)
        {
            if (session.Volume != null)
            {
                return;
            }
            EnsureEnumerator();
            IMMDevice device;
            int result = _enumerator.GetDevice(
                session.DeviceId,
                out device);
            ThrowIfFailed(result);
            AttachVolume(session, device);
        }

        private static void AttachVolume(
            EndpointSession session,
            IMMDevice device)
        {
            // 重连接口前必须先释放旧的：静音失败时轮询每 500ms 会重走这里，
            // 直接覆盖会持续泄漏 COM 引用，最终把音频接口调用拖垮。
            session.ReleaseInterfaces();
            session.Device = device;
            object managerObject;
            Guid interfaceId = SessionManagerInterfaceId;
            int result = session.Device.Activate(
                ref interfaceId,
                ClassContextAll,
                IntPtr.Zero,
                out managerObject);
            ThrowIfFailed(result);
            session.SessionManager =
                (IAudioSessionManager)managerObject;

            Guid defaultSession = Guid.Empty;
            ISimpleAudioVolume volume;
            result = session.SessionManager.GetSimpleAudioVolume(
                ref defaultSession,
                0,
                out volume);
            session.Volume = volume;
            ThrowIfFailed(result);
        }

        private static void SetEndpointMuteUntracked(
            IMMDevice device,
            bool muted)
        {
            IAudioSessionManager sessionManager = null;
            ISimpleAudioVolume volume = null;
            try
            {
                object managerObject;
                Guid interfaceId = SessionManagerInterfaceId;
                int result = device.Activate(
                    ref interfaceId,
                    ClassContextAll,
                    IntPtr.Zero,
                    out managerObject);
                ThrowIfFailed(result);
                sessionManager =
                    (IAudioSessionManager)managerObject;
                Guid defaultSession = Guid.Empty;
                result = sessionManager.GetSimpleAudioVolume(
                    ref defaultSession,
                    0,
                    out volume);
                ThrowIfFailed(result);
                Guid eventContext = EventContext;
                result = volume.SetMute(muted, ref eventContext);
                ThrowIfFailed(result);
            }
            finally
            {
                ReleaseComObject(volume);
                ReleaseComObject(sessionManager);
            }
        }

        private static void ThrowIfFailed(int result)
        {
            if (result < 0)
            {
                Marshal.ThrowExceptionForHR(result);
            }
        }

        public void Dispose()
        {
            RestoreMutedEndpoints();
            foreach (EndpointSession session in _mutedEndpoints.Values)
            {
                session.ReleaseInterfaces();
            }
            _mutedEndpoints.Clear();
            ReleaseEnumerator();
        }

        private void ReleaseEnumerator()
        {
            ReleaseComObject(_enumerator);
            _enumerator = null;
        }

        private static void ReleaseComObject(object value)
        {
            if (value != null && Marshal.IsComObject(value))
            {
                Marshal.FinalReleaseComObject(value);
            }
        }
    }
}
