import json
import re
from urllib.parse import urlparse

import pybase64
import base64
import requests
import binascii
import os
import random
from datetime import timezone
from datetime import datetime, timedelta

# Define a fixed timeout for HTTP requests
REQUEST_TIMEOUT = 3  # seconds

# Default subscription title for main config file
DEFAULT_SUBSCRIPTION_TITLE = "🆓 GitHub | Barry-far 🔥"

MAX_HOURS_OLD = 6  # Maximum hours old to consider a file as updated


def check_github_file_update_time(source_url, max_hours_old=MAX_HOURS_OLD):
    """
    Check if a GitHub file was updated within the specified time period.
    
    Args:
        source_url (str): The GitHub raw file URL
        max_hours_old (int): Maximum hours old to consider the file as updated (default: 12)
    
    Returns:
        tuple: (is_updated, last_commit_datetime)
            - is_updated (bool): True if file was updated within max_hours_old
            - last_commit_datetime (datetime): The datetime of the last commit, or datetime.min if error
    """
    try:
        # Parse GitHub link to extract owner, repo, and file_path
        url_parts = source_url.split("/")
        if len(url_parts) < 6:
            return False, datetime.min.replace(tzinfo=timezone.utc)

        repo_owner, repo_name = url_parts[3], url_parts[4]

        # Remove 'master', 'main', or 'refs/heads/main' from file_path if present
        file_path_parts = url_parts[5:]
        if file_path_parts and file_path_parts[0] in ["master", "main"]:
            file_path_parts = file_path_parts[1:]
        elif len(file_path_parts) >= 3 and file_path_parts[:3] == ["refs", "heads", "main"]:
            file_path_parts = file_path_parts[3:]
        file_path = "/".join(file_path_parts)

        # Check if the link is updated within the specified time period
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

            # Check if file is updated within the specified hours
            time_diff = datetime.now(timezone.utc) - last_commit_datetime
            is_updated = time_diff <= timedelta(hours=max_hours_old)

            return is_updated, last_commit_datetime
        else:
            return False, datetime.min.replace(tzinfo=timezone.utc)

    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        print(f"Error checking GitHub API for {source_url}: {e}")
        return False, datetime.min.replace(tzinfo=timezone.utc)


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


def split_concatenated_configs(content):
    """
    Split content that may have concatenated configs without newlines.
    Handles cases like: base64_config}ss://config or vmess://config}vless://config
    
    Args:
        content (str): The content that may contain concatenated configs
        
    Returns:
        str: Content with proper newlines between configs
    """
    # Define protocol patterns that indicate the start of a new config
    protocol_patterns = [
        r'(vmess://)',
        r'(vless://)',
        r'(trojan://)',
        r'(ss://)',
        r'(ssr://)',
        r'(hy2://)',
        r'(hysteria2://)',
        r'(tuic://)',
        r'(warp://)'
    ]
    
    # Also split on closing braces followed by protocols (for base64 vmess configs)
    # Pattern: }vmess:// or }ss:// etc.
    combined_pattern = r'(\}(?=' + '|'.join([p.strip(r'()') for p in protocol_patterns]) + r'))'
    
    # First, add newlines after closing braces that precede protocols
    content = re.sub(combined_pattern, r'}\n', content)
    
    # Then add newlines before protocols if they're not already on a new line
    for pattern in protocol_patterns:
        # Only add newline if the protocol is not at the start of a line
        content = re.sub(r'([^\n])' + pattern, r'\1\n\2', content)
    
    return content


# Function to decode base64-encoded links with a timeout (返回带时间戳的数据)
def fetch_and_decode_base64_sources(base64_source_urls):
    decoded_sources_with_timestamp = []
    for source_url in base64_source_urls:
        try:
            # Check if the file is updated within the last MAX_HOURS_OLD hours
            is_updated, last_commit_datetime = check_github_file_update_time(source_url, max_hours_old=MAX_HOURS_OLD)
            if not is_updated:
                print(f"Skipping outdated source: {source_url}")
                continue

            # Fetch and decode the link content
            content_response = requests.get(source_url, timeout=REQUEST_TIMEOUT)
            content_response.raise_for_status()
            encoded_content = content_response.content
            decoded_content = decode_base64_content(encoded_content)
            
            # Split concatenated configs
            decoded_content = split_concatenated_configs(decoded_content)
            
            decoded_sources_with_timestamp.append((last_commit_datetime, decoded_content))

        except requests.RequestException as e:
            print(f"Error processing base64 source {source_url}: {e}")
            continue

    return decoded_sources_with_timestamp


# Function to decode directory links with a timeout (返回带时间戳的数据)
def fetch_plain_text_sources(plain_text_source_urls):
    decoded_sources_with_timestamp = []
    for source_url in plain_text_source_urls:
        try:
            last_commit_datetime = datetime.min.replace(tzinfo=timezone.utc)

            # Check if this is a GitHub URL and validate update time
            if "githubusercontent.com" in source_url:
                is_updated, last_commit_datetime = check_github_file_update_time(source_url,
                                                                                 max_hours_old=MAX_HOURS_OLD)
                if not is_updated:
                    print(f"Skipping outdated source: {source_url}")
                    continue

            content_response = requests.get(source_url, timeout=REQUEST_TIMEOUT)
            content_response.raise_for_status()
            plain_text_content = content_response.text
            
            # Split concatenated configs
            plain_text_content = split_concatenated_configs(plain_text_content)
            
            decoded_sources_with_timestamp.append((last_commit_datetime, plain_text_content))

        except requests.RequestException as e:
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


def load_sources_from_json(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("base64_encoded_sources", []), data.get("plain_text_sources", [])


def create_subscription_header(subscription_title):
    """
    Create a custom subscription header with the given title.
    
    Args:
        subscription_title (str): The title for the subscription
        
    Returns:
        str: Formatted subscription header
    """
    encoded_subscription_title = base64.b64encode(subscription_title.encode()).decode()
    return f"""#profile-title: base64:{encoded_subscription_title}
#profile-update-interval: 1
#subscription-userinfo: upload=29; download=12; total=10737418240000000; expire=2546249531
#support-url: https://github.com/barry-far/V2ray-config
#profile-web-page-url: https://github.com/barry-far/V2ray-config
"""


def create_split_subscription_files(unique_configs, output_folder, base64_folder, max_configs_per_file=500):
    """
    Split configs into multiple subscription files and create their base64 versions.
    
    Args:
        unique_configs (list): List of unique configuration lines
        output_folder (str): Path to the main output folder
        base64_folder (str): Path to the base64 output folder
        max_configs_per_file (int): Maximum number of configs per file (default: 500)
        
    Returns:
        int: Number of split files created
    """
    print("Creating split subscription files...")

    # 只处理配置行，不包含文件头
    config_lines_with_newlines = []
    for config in unique_configs:
        config_lines_with_newlines.append(config + "\n")

    total_config_lines = len(config_lines_with_newlines)
    total_split_files = (total_config_lines + max_configs_per_file - 1) // max_configs_per_file
    print(f"Splitting into {total_split_files} files with max {max_configs_per_file} configs each")

    for file_index in range(total_split_files):
        subscription_title = f"🆓 Git:barry-far | Sub{file_index + 1} 🔥"
        custom_subscription_header = create_subscription_header(subscription_title)

        # Create regular text file
        split_config_file = os.path.join(output_folder, f"Sub{file_index + 1}.txt")
        with open(split_config_file, "w", encoding="utf-8") as f:
            f.write(custom_subscription_header)
            start_line_index = file_index * max_configs_per_file
            end_line_index = min((file_index + 1) * max_configs_per_file, total_config_lines)
            # 使用配置行列表而不是从文件读取
            for config_line in config_lines_with_newlines[start_line_index:end_line_index]:
                f.write(config_line)
        print(f"Created: Sub{file_index + 1}.txt")

        # Create base64 version
        with open(split_config_file, "r", encoding="utf-8") as input_file:
            split_config_content = input_file.read()

        base64_output_filename = os.path.join(base64_folder, f"Sub{file_index + 1}_base64.txt")
        with open(base64_output_filename, "w", encoding="utf-8") as output_file:
            encoded_split_config = base64.b64encode(split_config_content.encode()).decode()
            output_file.write(encoded_split_config)
        print(f"Created: Sub{file_index + 1}_base64.txt")

    return total_split_files


# Main function to process links and write output files
def main():
    output_folder, base64_folder = create_output_directories()

    # Prepare output file paths
    output_filename = os.path.join(output_folder, "All_Configs_Sub.txt")
    main_base64_filename = os.path.join(output_folder, "All_Configs_base64_Sub.txt")

    print("Starting to fetch and process configs...")

    supported_protocols = ["vmess", "vless", "trojan", "ss", "ssr", "hy2", "tuic", "warp://"]

    # 从 JSON 文件读取源列表
    sources_json_path = os.path.join(os.path.dirname(__file__), "sources.json")
    base64_encoded_sources, plain_text_sources = load_sources_from_json(sources_json_path)

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
    
    # 打乱顺序
    random.shuffle(unique_configs)

    # Write merged configs to output file
    print("Writing main config file...")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(create_subscription_header(DEFAULT_SUBSCRIPTION_TITLE))
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

    # Split configs using the new method
    total_split_files = create_split_subscription_files(unique_configs, output_folder, base64_folder)

    print(f"\nProcess completed successfully!")
    print(f"Total configs processed: {len(unique_configs)}")
    print(f"Files created:")
    print(f"  - All_Configs_Sub.txt")
    print(f"  - All_Configs_base64_Sub.txt")
    print(f"  - {total_split_files} split files (Sub1.txt to Sub{total_split_files}.txt)")
    print(f"  - {total_split_files} base64 split files (Sub1_base64.txt to Sub{total_split_files}_base64.txt)")


if __name__ == "__main__":
    main()