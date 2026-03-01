import subprocess
import sys
import time
import os

def main():
    print("==================================================")
    print(" 🛡️  AEGIS System — Unified Boot Sequence")
    print("==================================================")
    
    if not os.path.exists(".env"):
        print("⚠️  Warning: .env file not found! Please run 'python setup_env.py' first.")
        time.sleep(2)
        
    try:
        print("▶ [1/2] Booting Telegram Sentinel Bot...")
        bot_proc = subprocess.Popen([sys.executable, "-m", "backend.bot"])
        
        # Give bot a tiny head start so logs are less interleaved
        time.sleep(1)
        
        print("▶ [2/2] Booting Flask Crisis Dashboard...")
        app_proc = subprocess.Popen([sys.executable, "-m", "backend.app"])
        
        print("\n✅ All systems online. Press CTRL+C to safely shut down everything.\n")
        
        # Keep script alive to hold terminals open
        bot_proc.wait()
        app_proc.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Shutting down AEGIS servers gracefully...")
        bot_proc.terminate()
        app_proc.terminate()
        bot_proc.wait()
        app_proc.wait()
        print("Shutdown complete.")
        sys.exit(0)

if __name__ == "__main__":
    main()
