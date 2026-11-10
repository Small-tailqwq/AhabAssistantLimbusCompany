using System;
using System.IO;
using System.IO.Pipes;
using System.Windows.Forms;

namespace AALC.CloneHost
{
    /// <summary>
    /// 承载 mstscax ActiveX 的独立宿主。COM、STA 消息循环与音频控制都留在这个进程，
    /// 主程序只通过命名管道收发文本行；连接流程与 native/desktop_clone_host 保持一致。
    /// </summary>
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
            string crashLog = Argument(args, "--crash-log", "");
            int desktopWidth;
            int desktopHeight;
            int rdpPort;
            bool showOnStart;
            if (pipeName.Length == 0
                || !int.TryParse(Argument(args, "--width", "1920"), out desktopWidth)
                || !int.TryParse(Argument(args, "--height", "1080"), out desktopHeight)
                || !int.TryParse(Argument(args, "--rdp-port", "3389"), out rdpPort)
                || !bool.TryParse(Argument(args, "--show", "true"), out showOnStart))
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
                        showOnStart));
                }
                return 0;
            }
            catch (Exception exception)
            {
                // 构造期失败（管道超时、mstscax 未注册、ActiveX 创建失败等）在主程序侧
                // 只表现为宿主退出，这里落盘才能诊断。
                try
                {
                    if (crashLog.Length != 0)
                    {
                        Directory.CreateDirectory(Path.GetDirectoryName(crashLog));
                        File.AppendAllText(
                            crashLog,
                            "\n===== " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                            + " =====\n"
                            + "commandline: " + Environment.CommandLine + "\n"
                            + exception.ToString() + "\n");
                    }
                }
                catch
                {
                }
                return 1;
            }
        }
    }
}
