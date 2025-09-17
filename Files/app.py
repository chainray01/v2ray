import json
import re
from urllib.parse import urlparse

import pybase64
import base64
import requests
import binascii
import os
from datetime import timezone
from datetime import datetime, timedelta

# Define a fixed timeout for HTTP requests
TIMEOUT = 15  # seconds

# Define the fixed text for the initial configuration
fixed_text = """#profile-title: base64:8J+GkyBHaXRodWIgfCBCYXJyeS1mYXIg8J+ltw==
#profile-update-interval: 1
#subscription-userinfo: upload=29; download=12; total=10737418240000000; expire=2546249531
#support-url: https://github.com/barry-far/V2ray-config
#profile-web-page-url: https://github.com/barry-far/V2ray-config
"""


# Base64 decoding function
def decode_base64(encoded):
    decoded = ""
    for encoding in ["utf-8", "iso-8859-1"]:
        try:
            decoded = pybase64.b64decode(encoded + b"=" * (-len(encoded) % 4)).decode(encoding)
            break
        except (UnicodeDecodeError, binascii.Error):
            pass
    return decoded


# Function to decode base64-encoded links with a timeout (返回带时间戳的数据)
def decode_b64_links(links):
    decoded_data_with_time = []
    for link in links:
        try:
            # Parse GitHub link to extract owner, repo, and file_path
            parts = link.split("/")
            owner, repo = parts[3], parts[4]
            # Remove 'master', 'main', or 'refs/heads/main' from file_path if present
            file_path_parts = parts[5:]
            if file_path_parts and file_path_parts[0] in ["master", "main"]:
                file_path_parts = file_path_parts[1:]
            elif file_path_parts[:3] == ["refs", "heads", "main"]:
                file_path_parts = file_path_parts[3:]
            file_path = "/".join(file_path_parts)

            # Check if the link is updated within the last 48 hours
            url = f"https://api.github.com/repos/{owner}/{repo}/commits"
            params = {"path": file_path, "page": 1, "per_page": 1}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/vnd.github.v3+json"
            }
            res = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            res.raise_for_status()
            data = res.json()

            if isinstance(data, list) and len(data) > 0:
                commit_time = data[0]["commit"]["committer"]["date"]
                commit_datetime = datetime.strptime(commit_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - commit_datetime > timedelta(hours=48):
                    print(f"Skipping outdated link: {link}")
                    continue

                # Fetch and decode the link content
                response = requests.get(link, timeout=TIMEOUT)
                response.raise_for_status()
                encoded_bytes = response.content
                decoded_text = decode_base64(encoded_bytes)
                decoded_data_with_time.append((commit_datetime, decoded_text))
        except (requests.RequestException, KeyError, IndexError) as e:
            print(f"Error processing link {link}: {e}")
            continue

    # 返回带时间戳的数据供全局排序
    return decoded_data_with_time


# Function to decode directory links with a timeout (返回带时间戳的数据)
def decode_links(dir_links):
    decoded_dir_links_with_time = []
    for link in dir_links:
        try:
            commit_datetime = datetime.min.replace(tzinfo=timezone.utc)
            # Parse GitHub link to extract owner, repo, and file_path
            parts = link.split("/")
            if "githubusercontent.com" in link and len(parts) > 5:
                owner, repo = parts[3], parts[4]
                file_path_parts = parts[5:]
                if file_path_parts and file_path_parts[0] in ["master", "main"]:
                    file_path_parts = file_path_parts[1:]
                elif file_path_parts[:3] == ["refs", "heads", "main"]:
                    file_path_parts = file_path_parts[3:]
                file_path = "/".join(file_path_parts)

                # Check if the link is updated within the last 48 hours
                url = f"https://api.github.com/repos/{owner}/{repo}/commits"
                params = {"path": file_path, "page": 1, "per_page": 1}
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept": "application/vnd.github.v3+json"
                }
                res = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
                res.raise_for_status()
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    commit_time = data[0]["commit"]["committer"]["date"]
                    commit_datetime = datetime.strptime(commit_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - commit_datetime > timedelta(hours=24):
                        print(f"Skipping outdated link: {link}")
                        continue

            response = requests.get(link, timeout=TIMEOUT)
            decoded_text = response.text
            decoded_dir_links_with_time.append((commit_datetime, decoded_text))
        except (requests.RequestException, KeyError, IndexError) as e:
            print(f"Error processing dir link {link}: {e}")
            continue

    # 返回带时间戳的数据供全局排序
    return decoded_dir_links_with_time


# Filter function to select lines based on specified protocols and remove duplicates (only for config lines)
def filter_for_protocols(data, protocols):
    filtered_data = []
    seen_configs = set()
    seen_hosts = set()
    header_lines = {"#profile-title", "#profile-update-interval", "#subscription-userinfo", "#support-url",
                    "#profile-web-page-url"}

    def extract_host_port(line):
        try:
            # vmess:// 特殊处理（base64 JSON）
            if line.startswith("vmess://"):
                raw = line[8:].strip()
                try:
                    padded = raw + "=" * (-len(raw) % 4)  # 补齐 base64
                    decoded_json = base64.b64decode(padded).decode("utf-8")
                    obj = json.loads(decoded_json)
                    host = obj.get("add")
                    port = obj.get("port")
                    if host and port:
                        return f"{host}:{port}"
                except Exception:
                    return None

            # 通用协议（ss, vless, trojan, hysteria2, tuic, hy2...）
            if line.startswith(("ss://", "ssr://", "vless://", "trojan://", "hysteria2://", "hy2://", "tuic://")):
                parsed = urlparse(line)
                if parsed.hostname and parsed.port:
                    return f"{parsed.hostname}:{parsed.port}"

            # 兜底正则匹配 @host:port
            match = re.search(r'@([\w\.\-]+):(\d+)', line)
            if match:
                return f"{match.group(1)}:{match.group(2)}"
            return None
        except Exception:
            return None

    # 逐条数据处理
    for content in data:
        if content and content.strip():
            lines = content.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    # 跳过重复 header 行
                    if any(header in line for header in header_lines):
                        continue
                    filtered_data.append(line)
                elif any(protocol in line for protocol in protocols):
                    host_port = extract_host_port(line)
                    if host_port:
                        if host_port in seen_hosts:
                            continue  # 已存在，跳过
                        seen_hosts.add(host_port)
                    if line not in seen_configs:
                        filtered_data.append(line)
                        seen_configs.add(line)
    return filtered_data


# Create necessary directories if they don't exist
def ensure_directories_exist():
    output_folder = os.path.join(os.path.dirname(__file__), "..", "data")
    base64_folder = os.path.join(output_folder, "Base64")

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    if not os.path.exists(base64_folder):
        os.makedirs(base64_folder)

    return output_folder, base64_folder


# Main function to process links and write output files
def main():
    output_folder, base64_folder = ensure_directories_exist()  # Ensure directories are created

    # Prepare output file paths
    output_filename = os.path.join(output_folder, "All_Configs_Sub.txt")
    main_base64_filename = os.path.join(output_folder, "All_Configs_base64_Sub.txt")

    print("Starting to fetch and process configs...")

    protocols = ["vmess", "vless", "trojan", "ss", "ssr", "hy2", "tuic", "warp://"]
    base64_links = [
        "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/sub.txt",
        "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray",
        "https://raw.githubusercontent.com/ts-sf/fly/main/v2",
        "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2",
        "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/super-sub.txt",
        "https://raw.githubusercontent.com/yebekhe/vpn-fail/refs/heads/main/sub-link",
        "https://raw.githubusercontent.com/Surfboardv2ray/TGParse/main/splitted/mixed"
    ]
    dir_links = [
        "https://raw.githubusercontent.com/itsyebekhe/PSG/main/lite/subscriptions/xray/normal/mix",
        "https://raw.githubusercontent.com/HosseinKoofi/GO_V2rayCollector/main/mixed_iran.txt",
        "https://raw.githubusercontent.com/arshiacomplus/v2rayExtractor/refs/heads/main/mix/sub.html",
        "https://raw.githubusercontent.com/Rayan-Config/C-Sub/refs/heads/main/configs/proxy.txt",
        "https://raw.githubusercontent.com/4n0nymou3/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt",
        "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity.txt",
        "https://raw.githubusercontent.com/SoliSpirit/v2ray-configs/refs/heads/main/Protocols/ss.txt",
        "https://raw.githubusercontent.com/SoliSpirit/v2ray-configs/refs/heads/main/Protocols/vmess.txt",
        "https://raw.githubusercontent.com/MahsaNetConfigTopic/config/refs/heads/main/xray_final.txt"
    ]

    print("Fetching base64 encoded configs...")
    decoded_links_with_time = decode_b64_links(base64_links)
    print(f"Decoded {len(decoded_links_with_time)} base64 sources")

    print("Fetching direct text configs...")
    decoded_dir_links_with_time = decode_links(dir_links)
    print(f"Decoded {len(decoded_dir_links_with_time)} direct text sources")

    print("Combining and sorting configs by time...")
    # 合并所有带时间戳的数据
    all_data_with_time = decoded_links_with_time + decoded_dir_links_with_time
    # 按时间戳降序排序（最新的在前）
    all_data_with_time.sort(key=lambda x: x[0], reverse=True)
    # 提取排序后的数据内容
    combined_data = [data for (_, data) in all_data_with_time]

    print("Filtering configs...")
    merged_configs = filter_for_protocols(combined_data, protocols)
    print(f"Found {len(merged_configs)} unique configs after filtering")
    if len(merged_configs) < 1:
        print("No configs found. Exiting...")
        return

    # Write merged configs to output file
    print("Writing main config file...")
    output_filename = os.path.join(output_folder, "All_Configs_Sub.txt")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(fixed_text)
        for config in merged_configs:
            f.write(config + "\n")
    print(f"Main config file created: {output_filename}")

    # Create base64 version of the main file
    print("Creating base64 version...")
    with open(output_filename, "r", encoding="utf-8") as f:
        main_config_data = f.read()

    main_base64_filename = os.path.join(output_folder, "All_Configs_base64_Sub.txt")
    with open(main_base64_filename, "w", encoding="utf-8") as f:
        encoded_main_config = base64.b64encode(main_config_data.encode()).decode()
        f.write(encoded_main_config)
    print(f"Base64 config file created: {main_base64_filename}")

    # Split merged configs into smaller files (no more than 500 configs per file)
    print("Creating split files...")
    with open(output_filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    num_lines = len(lines)
    max_lines_per_file = 500
    num_files = (num_lines + max_lines_per_file - 1) // max_lines_per_file
    print(f"Splitting into {num_files} files with max {max_lines_per_file} lines each")

    for i in range(num_files):
        profile_title = f"🆓 Git:barry-far | Sub{i + 1} 🔥"
        encoded_title = base64.b64encode(profile_title.encode()).decode()
        custom_fixed_text = f"""#profile-title: base64:{encoded_title}
#profile-update-interval: 1
#subscription-userinfo: upload=29; download=12; total=10737418240000000; expire=2546249531
#support-url: https://github.com/barry-far/V2ray-config
#profile-web-page-url: https://github.com/barry-far/V2ray-config
"""

        input_filename = os.path.join(output_folder, f"Sub{i + 1}.txt")
        with open(input_filename, "w", encoding="utf-8") as f:
            f.write(custom_fixed_text)
            start_index = i * max_lines_per_file
            end_index = min((i + 1) * max_lines_per_file, num_lines)
            for line in lines[start_index:end_index]:
                f.write(line)
        print(f"Created: Sub{i + 1}.txt")

        with open(input_filename, "r", encoding="utf-8") as input_file:
            config_data = input_file.read()

        base64_output_filename = os.path.join(base64_folder, f"Sub{i + 1}_base64.txt")
        with open(base64_output_filename, "w", encoding="utf-8") as output_file:
            encoded_config = base64.b64encode(config_data.encode()).decode()
            output_file.write(encoded_config)
        print(f"Created: Sub{i + 1}_base64.txt")

    print(f"\nProcess completed successfully!")
    print(f"Total configs processed: {len(merged_configs)}")
    print(f"Files created:")
    print(f"  - All_Configs_Sub.txt")
    print(f"  - All_Configs_base64_Sub.txt")
    print(f"  - {num_files} split files (Sub1.txt to Sub{num_files}.txt)")
    print(f"  - {num_files} base64 split files (Sub1_base64.txt to Sub{num_files}_base64.txt)")


if __name__ == "__main__":
    main()
