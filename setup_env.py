import os
import shutil

def main():
    env_file = ".env"
    example_file = ".env.example"

    print("🛡️ AEGIS Interactive Environment Setup")
    print("--------------------------------------")

    if not os.path.exists(example_file):
        print("Error: .env.example not found. Please run this script from the project root.")
        return

    if not os.path.exists(env_file):
        print(f"Initializing {env_file} from {example_file}...")
        shutil.copy(example_file, env_file)

    with open(env_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    print("\nPlease provide your API keys. Press Enter to skip and keep the current value.")
    telegram = input("TELEGRAM_BOT_TOKEN: ").strip()
    mistral = input("MISTRAL_API_KEY: ").strip()
    elevenlabs = input("ELEVENLABS_API_KEY (Optional): ").strip()

    new_lines = []
    for line in lines:
        if line.startswith("TELEGRAM_BOT_TOKEN=") and telegram:
            new_lines.append(f"TELEGRAM_BOT_TOKEN={telegram}\n")
        elif line.startswith("MISTRAL_API_KEY=") and mistral:
            new_lines.append(f"MISTRAL_API_KEY={mistral}\n")
        elif line.startswith("ELEVENLABS_API_KEY=") and elevenlabs:
            new_lines.append(f"ELEVENLABS_API_KEY={elevenlabs}\n")
        else:
            new_lines.append(line)

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print("\n✅ Successfully updated .env file. AEGIS is ready to deploy.")

if __name__ == "__main__":
    main()
