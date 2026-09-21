using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Facebook Reels Auto Bot 2 (Thai Drama)")]
[assembly: AssemblyProduct("Facebook Reels Auto Bot 2 (Thai Drama)")]
[assembly: AssemblyDescription("Facebook Reels Auto Upload - Thai Drama Edition")]
[assembly: AssemblyVersion("2.0.0.0")]
[assembly: AssemblyFileVersion("2.0.0.0")]

namespace ReelsAutoBotLauncher
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            try
            {
                string exeDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                string scriptPath = Path.Combine(exeDir, "app_gui.py");
                string appDir = exeDir;

                // Fallback location if running directly from Desktop or another folder
                if (!File.Exists(scriptPath))
                {
                    string hardcodedDir = @"G:\PG\Page Reel uplaod 2";
                    if (File.Exists(Path.Combine(hardcodedDir, "app_gui.py")))
                    {
                        scriptPath = Path.Combine(hardcodedDir, "app_gui.py");
                        appDir = hardcodedDir;
                    }
                }

                if (!File.Exists(scriptPath))
                {
                    MessageBox.Show(
                        "ไม่พบไฟล์ app_gui.py!\nกรุณาตรวจสอบว่าโปรแกรมอยู่ในโฟลเดอร์: " + appDir,
                        "Facebook Reels Auto Bot - Error",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return;
                }

                string pythonPath = FindPythonExecutable();
                if (string.IsNullOrEmpty(pythonPath))
                {
                    MessageBox.Show(
                        "ไม่พบ Python (pythonw.exe) ในเครื่อง!\nกรุณาติดตั้ง Python หรือเพิ่มเข้า PATH.",
                        "Facebook Reels Auto Bot - Error",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return;
                }

                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = pythonPath;
                psi.Arguments = "\"" + scriptPath + "\"";
                psi.WorkingDirectory = appDir;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                psi.WindowStyle = ProcessWindowStyle.Normal;

                Process p = Process.Start(psi);
                if (p != null)
                {
                    if (p.WaitForExit(1500) && p.ExitCode != 0)
                    {
                        MessageBox.Show(
                            "เกิดข้อผิดพลาดในการเปิดโปรแกรม (Exit Code: " + p.ExitCode + ")\n" +
                            "กรุณาตรวจสอบ หรือ ลองเปิดผ่าน START_BOT.bat เพื่อดูข้อผิดพลาด.",
                            "Facebook Reels Auto Bot - Error",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error
                        );
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "เกิดข้อผิดพลาดในการเปิดโปรแกรม:\n" + ex.Message,
                    "Facebook Reels Auto Bot - Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        static string FindPythonExecutable()
        {
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            
            string[] candidates = new string[]
            {
                Path.Combine(localAppData, @"Python\bin\pythonw.exe"),
                Path.Combine(localAppData, @"Python\pythoncore-3.14-64\pythonw.exe"),
                @"C:\Users\kee_n\AppData\Local\Python\bin\pythonw.exe",
                @"C:\Users\kee_n\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe",
                Path.Combine(localAppData, @"Programs\Python\Python312\pythonw.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python311\pythonw.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python310\pythonw.exe"),
                @"C:\Program Files\Python312\pythonw.exe",
                @"C:\Program Files\Python311\pythonw.exe",
                Path.Combine(localAppData, @"Python\bin\python.exe"),
                Path.Combine(localAppData, @"Python\pythoncore-3.14-64\python.exe")
            };

            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate))
                {
                    return candidate;
                }
            }

            // Check PATH environment variable
            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
            string[] paths = pathEnv.Split(Path.PathSeparator);
            foreach (string p in paths)
            {
                if (string.IsNullOrWhiteSpace(p)) continue;
                string checkW = Path.Combine(p.Trim(), "pythonw.exe");
                if (File.Exists(checkW)) return checkW;
            }

            foreach (string p in paths)
            {
                if (string.IsNullOrWhiteSpace(p)) continue;
                string checkPy = Path.Combine(p.Trim(), "python.exe");
                if (File.Exists(checkPy)) return checkPy;
            }

            return null;
        }
    }
}
