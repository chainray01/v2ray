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
REQUEST_TIMEOUT = 15  # seconds

# Define the fixed text for the initial configuration
DEFAULT_SUBSCRIPTION_HEADER = """#profile-title: base64:8J+GkyBHaXRodWIgfCBCYXJyeS1mYXIg8J+ltw==
#profile-update-interval: 1
#subscription-userinfo: upload=29; download=12; total=10737418240000000; expire=2546249531
#support-url: https://github.com/barry-far/V2ray-config
#profile-web-page-url: https://github.com/barry-far/V2ray-config
"""


# Base64 decoding function
def decode_base64_content(encoded_data):
    decoded_content = ""
    for encoding in ["utf-8", "iso-8859-1"]:
        try:
            decoded_content = pybase64.b64decode(encoded_data + b"=" * (-len(encoded_data) % 4)).decode(encoding)
            break
        except (UnicodeDecodeError, binascii.Error):
            pass
    return decoded_content


# Function to decode base64-encoded links with a timeout (返回带时间戳的数据)
def fetch_and_decode_base64_sources(base64_source_urls):
    decoded_sources_with_timestamp = []
    for source_url in base64_source_urls:
        try:
            # Parse GitHub link to extract owner, repo, and file_path
            url_parts = source_url.split("/")
            repo_owner, repo_name = url_parts[3], url_parts[4]
            # Remove 'master', 'main', or 'refs/heads/main' from file_path if present
            file_path_parts = url_parts[5:]
            if file_path_parts and file_path_parts[0] in ["master", "main"]:
                file_path_parts = file_path_parts[1:]
            elif file_path_parts[:3] == ["refs", "heads", "main"]:
                file_path_parts = file_path_parts[3:]
            file_path = "/".join(file_path_parts)

            # Check if the link is updated within the last 48 hours
            github_api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
            api_params = {"path": file_path, "page": 1, "per_page": 1}
            request_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/vnd.github.v3+json"
            }
            api_response = requests.get(github_api_url, params=api_params, headers=request_headers,
                                        timeout=REQUEST_TIMEOUT)
            api_response.raise_for_status()
            commit_data = api_response.json()

            if isinstance(commit_data, list) and len(commit_data) > 0:
                last_commit_time = commit_data[0]["commit"]["committer"]["date"]
                last_commit_datetime = datetime.strptime(last_commit_time, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - last_commit_datetime > timedelta(hours=12):
                    print(f"Skipping outdated source: {source_url}")
                    continue

                # Fetch and decode the link content
                content_response = requests.get(source_url, timeout=REQUEST_TIMEOUT)
                content_response.raise_for_status()
                encoded_content = content_response.content
                decoded_content = decode_base64_content(encoded_content)
                decoded_sources_with_timestamp.append((last_commit_datetime, decoded_content))
        except (requests.RequestException, KeyError, IndexError) as e:
            print(f"Error processing base64 source {source_url}: {e}")
            continue

    return decoded_sources_with_timestamp


# Function to decode directory links with a timeout (返回带时间戳的数据)
def fetch_plain_text_sources(plain_text_source_urls):
    decoded_sources_with_timestamp = []
    for source_url in plain_text_source_urls:
        try:
            last_commit_datetime = datetime.min.replace(tzinfo=timezone.utc)
            # Parse GitHub link to extract owner, repo, and file_path
            url_parts = source_url.split("/")
            if "githubusercontent.com" in source_url and len(url_parts) > 5:
                repo_owner, repo_name = url_parts[3], url_parts[4]
                file_path_parts = url_parts[5:]
                if file_path_parts and file_path_parts[0] in ["master", "main"]:
                    file_path_parts = file_path_parts[1:]
                elif file_path_parts[:3] == ["refs", "heads", "main"]:
                    file_path_parts = file_path_parts[3:]
                file_path = "/".join(file_path_parts)

                # Check if the link is updated within the last 24 hours
                github_api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits"
                api_params = {"path": file_path, "page": 1, "per_page": 1}
                request_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept": "application/vnd.github.v3+json"
                }
                api_response = requests.get(github_api_url, params=api_params, headers=request_headers,
                                            timeout=REQUEST_TIMEOUT)
                api_response.raise_for_status()
                commit_data = api_response.json()
                if isinstance(commit_data, list) and len(commit_data) > 0:
                    last_commit_time = commit_data[0]["commit"]["committer"]["date"]
                    last_commit_datetime = datetime.strptime(last_commit_time, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - last_commit_datetime > timedelta(hours=12):
                        print(f"Skipping outdated source: {source_url}")
                        continue

            content_response = requests.get(source_url, timeout=REQUEST_TIMEOUT)
            plain_text_content = content_response.text
            decoded_sources_with_timestamp.append((last_commit_datetime, plain_text_content))
        except (requests.RequestException, KeyError, IndexError) as e:
            print(f"Error processing plain text source {source_url}: {e}")
            continue

    return decoded_sources_with_timestamp


# Filter function to select lines based on specified protocols and remove duplicates (only for config lines)
def filter_and_deduplicate_configs(source_contents, supported_protocols):
    filtered_configs = []
    seen = set()  # 存放去重 key（host:port 或整行）

    header_keywords = {
        "#profile-title",
        "#profile-update-interval",
        "#subscription-userinfo",
        "#support-url",
        "#profile-web-page-url",
    }

    def extract_host_port_from_config(config_line):
        """提取 host:port 用于去重"""
        try:
            # vmess:// 特殊处理（base64 JSON）
            if config_line.startswith("vmess://"):
                vmess_part = config_line[8:].strip()
                padded = vmess_part + "=" * (-len(vmess_part) % 4)
                vmess_json = base64.b64decode(padded).decode("utf-8")
                vmess_obj = json.loads(vmess_json)
                if vmess_obj.get("add") and vmess_obj.get("port"):
                    return f"{vmess_obj['add']}:{vmess_obj['port']}"

            # 通用协议
            if config_line.startswith(
                ("ss://", "ssr://", "vless://", "trojan://", "hysteria2://", "hy2://", "tuic://")
            ):
                parsed = urlparse(config_line)
                if parsed.hostname and parsed.port:
                    return f"{parsed.hostname}:{parsed.port}"

            # 正则兜底 @host:port
            m = re.search(r"@([\w\.\-]+):(\d+)", config_line)
            if m:
                return f"{m.group(1)}:{m.group(2)}"

            return None
        except Exception:
            return None

    # 逐条数据处理
    for content in source_contents:
        if not content.strip():
            continue

        for line in map(str.strip, content.splitlines()):
            if not line:
                continue

            # header 行处理
            if line.startswith("#"):
                if any(k in line for k in header_keywords):
                    continue  # 跳过重复 header 行
                filtered_configs.append(line)
                continue

            # 协议行处理
            if any(proto in line for proto in supported_protocols):
                # 先尝试 host:port，否则 fallback 到整行
                key = extract_host_port_from_config(line) or line
                if key not in seen:
                    seen.add(key)
                    filtered_configs.append(line)

    return filtered_configs



# Create necessary directories if they don't exist
def create_output_directories():
    output_folder = os.path.join(os.path.dirname(__file__), "..", "data")
    base64_folder = os.path.join(output_folder, "Base64")

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    if not os.path.exists(base64_folder):
        os.makedirs(base64_folder)

    return output_folder, base64_folder


# Main function to process links and write output files
def main():
    output_folder, base64_folder = create_output_directories()

    # Prepare output file paths
    output_filename = os.path.join(output_folder, "All_Configs_Sub.txt")
    main_base64_filename = os.path.join(output_folder, "All_Configs_base64_Sub.txt")

    print("Starting to fetch and process configs...")

    supported_protocols = ["vmess", "vless", "trojan", "ss", "ssr", "hy2", "tuic", "warp://"]
    base64_encoded_sources = [
        "https://raw.githubusercontent.com/ALIILAPRO/v2rayNG-Config/main/sub.txt",
        "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray",
        "https://raw.githubusercontent.com/ts-sf/fly/main/v2",
        "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2",
        "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/super-sub.txt",
        "https://raw.githubusercontent.com/yebekhe/vpn-fail/refs/heads/main/sub-link",
        "https://raw.githubusercontent.com/Surfboardv2ray/TGParse/main/splitted/mixed"
    ]
    plain_text_sources = [
        "https://raw.githubusercontent.com/itsyebekhe/PSG/main/lite/subscriptions/xray/normal/mix",
        "https://raw.githubusercontent.com/HosseinKoofi/GO_V2rayCollector/main/mixed_iran.txt",
        "https://raw.githubusercontent.com/arshiacomplus/v2rayExtractor/refs/heads/main/mix/sub.html",
        "https://raw.githubusercontent.com/Rayan-Config/C-Sub/refs/heads/main/configs/proxy.txt",
        "https://raw.githubusercontent.com/4n0nymou3/multi-proxy-config-fetcher/refs/heads/main/configs/proxy_configs.txt",
        "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Eternity.txt",
        "https://raw.githubusercontent.com/SoliSpirit/v2ray-configs/refs/heads/main/all_configs.txt",
        "https://raw.githubusercontent.com/crackbest/V2ray-Config/refs/heads/main/config.txt",
        "https://raw.githubusercontent.com/MahsaNetConfigTopic/config/refs/heads/main/xray_final.txt"
    ]

    print("Fetching base64 encoded configs...")
    base64_sources_with_time = fetch_and_decode_base64_sources(base64_encoded_sources)
    print(f"Successfully fetched {len(base64_sources_with_time)} base64 sources")

    print("Fetching direct text configs...")
    plain_text_sources_with_time = fetch_plain_text_sources(plain_text_sources)
    print(f"Successfully fetched {len(plain_text_sources_with_time)} plain text sources")

    print("Combining and sorting configs by timestamp...")
    # 合并所有带时间戳的数据
    all_sources_with_time = base64_sources_with_time + plain_text_sources_with_time
    # 按时间戳降序排序（最新的在前）
    all_sources_with_time.sort(key=lambda x: x[0], reverse=True)
    # 提取排序后的数据内容
    all_source_contents = [content for (_, content) in all_sources_with_time]

    print("Filtering and deduplicating configs...")
    unique_configs = filter_and_deduplicate_configs(all_source_contents, supported_protocols)
    print(f"Found {len(unique_configs)} unique configs after filtering")
    if len(unique_configs) < 1:
        print("No configs found. Exiting...")
        return

    # Write merged configs to output file
    print("Writing main config file...")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(DEFAULT_SUBSCRIPTION_HEADER)
        for config in unique_configs:
            f.write(config + "\n")
    print(f"Main config file created: {output_filename}")

    # Create base64 version of the main file
    print("Creating base64 version...")
    with open(output_filename, "r", encoding="utf-8") as f:
        main_config_content = f.read()

    with open(main_base64_filename, "w", encoding="utf-8") as f:
        encoded_main_config = base64.b64encode(main_config_content.encode()).decode()
        f.write(encoded_main_config)
    print(f"Base64 config file created: {main_base64_filename}")

    # Split merged configs into smaller files (no more than 500 configs per file)
    print("Creating split subscription files...")

    # 只处理配置行，不包含文件头
    config_lines_with_newlines = []
    for config in unique_configs:
        config_lines_with_newlines.append(config + "\n")

    total_config_lines = len(config_lines_with_newlines)
    max_configs_per_file = 500
    total_split_files = (total_config_lines + max_configs_per_file - 1) // max_configs_per_file
    print(f"Splitting into {total_split_files} files with max {max_configs_per_file} configs each")

    for file_index in range(total_split_files):
        subscription_title = f"🆓 Git:barry-far | Sub{file_index + 1} 🔥"
        encoded_subscription_title = base64.b64encode(subscription_title.encode()).decode()
        custom_subscription_header = f"""#profile-title: base64:{encoded_subscription_title}
#profile-update-interval: 1
#subscription-userinfo: upload=29; download=12; total=10737418240000000; expire=2546249531
#support-url: https://github.com/barry-far/V2ray-config
#profile-web-page-url: https://github.com/barry-far/V2ray-config
"""

        split_config_file = os.path.join(output_folder, f"Sub{file_index + 1}.txt")
        with open(split_config_file, "w", encoding="utf-8") as f:
            f.write(custom_subscription_header)
            start_line_index = file_index * max_configs_per_file
            end_line_index = min((file_index + 1) * max_configs_per_file, total_config_lines)
            # 使用配置行列表而不是从文件读取
            for config_line in config_lines_with_newlines[start_line_index:end_line_index]:
                f.write(config_line)
        print(f"Created: Sub{file_index + 1}.txt")

        with open(split_config_file, "r", encoding="utf-8") as input_file:
            split_config_content = input_file.read()

        base64_output_filename = os.path.join(base64_folder, f"Sub{file_index + 1}_base64.txt")
        with open(base64_output_filename, "w", encoding="utf-8") as output_file:
            encoded_split_config = base64.b64encode(split_config_content.encode()).decode()
            output_file.write(encoded_split_config)
        print(f"Created: Sub{file_index + 1}_base64.txt")

    print(f"\nProcess completed successfully!")
    print(f"Total configs processed: {len(unique_configs)}")
    print(f"Files created:")
    print(f"  - All_Configs_Sub.txt")
    print(f"  - All_Configs_base64_Sub.txt")
    print(f"  - {total_split_files} split files (Sub1.txt to Sub{total_split_files}.txt)")
    print(f"  - {total_split_files} base64 split files (Sub1_base64.txt to Sub{total_split_files}_base64.txt)")


if __name__ == "__main__":
    main()