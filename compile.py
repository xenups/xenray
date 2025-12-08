"""
اسکریپت نهایی Nuitka: حذف آرگومان آیکون برای حل مشکل ناسازگاری محیط.
پس از این کامپایل، آیکون باید به صورت دستی اضافه شود.
"""
import subprocess
import sys
import os
import shutil
import platform

if platform.system() != "Windows":
    print("Nuitka configuration is currently optimized only for Windows.")
    sys.exit(1)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

def main():
    print("=" * 60)
    print("Building XenRay with Nuitka (Ignoring Icon for Build Stability)...")
    print("=" * 60)
    
    main_script = "src/main.py"
    output_dir = "nuitka_dist"

    # --- ۱. پاکسازی ---
    shutil.rmtree(output_dir, ignore_errors=True)
    
    # --- ۲. ساخت دستور Nuitka ---
    # آرگومان --windows-icon-resources را به طور کامل حذف می کنیم
    cmd = [
        sys.executable, "-m", "nuitka",
        
        # --- عمومی و خروجی ---
        f"--output-dir={output_dir}",
        "--standalone",          
        "--remove-output",       
        "--follow-imports",      
        f"--output-filename=XenRay",
        
        # --- تنظیمات ویندوز و پلاگین‌ها (مهم: برای Flet) ---
        "--windows-disable-console", 
        
        # آرگومان پلاگین را در یک جای مطمئن و اولیه قرار می دهیم
        
        # --- داده‌ها و بهینه‌سازی ---
        "--include-data-dir=assets=assets",
        "--include-data-dir=bin=bin",       
        "--lto=yes",                 
        "--onefile",
        
        # --- اسکریپت اصلی ---
        main_script,
    ] 
    
    print("\nRunning Nuitka (This may take several minutes)...")
    
    try:
        # اجرای دستور
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as e:
        print("\n" + "=" * 60)
        print("BUILD FAILED!")
        print("خطای کامپایل Nuitka. لطفاً خروجی کامل را بررسی کنید.")
        print("=" * 60)
        sys.exit(1)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("NUITKA BUILD SUCCESSFUL (Icon needs manual insertion)!")
        final_exe_path = os.path.join(PROJECT_ROOT, output_dir, "XenRay.exe")
        print(f"Executable: {final_exe_path}")
        print("=" * 60)

if __name__ == "__main__":
    main()