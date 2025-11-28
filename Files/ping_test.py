import re
import base64
import asyncio
import aiohttp
import time


class V2RayConfigTester:
    def __init__(self, configs, timeout=2, max_concurrent=100):
        self.configs = configs
        self.protocols = ["vmess", "vless", "trojan", "ss"]
        self.timeout = timeout
        self.max_concurrent = max_concurrent

    def get_protocol(self, config):
        split = config.split("://")
        return split[0] if len(split) > 0 else ""

    def find_ip(self, config):
        try:
            ip_regex = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
            match = re.search(ip_regex, config)
            return match.group(0) if match else ""
        except:
            return ""

    async def ping(self, session, ip):
        url = f"https://{ip}/generate_204"
        start_time = time.time()
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.timeout), ssl=False) as response:
                duration = (time.time() - start_time) * 1000
                return int(duration / 5)
        except asyncio.TimeoutError:
            return None
        except:
            duration = (time.time() - start_time) * 1000
            if duration < self.timeout * 1000:
                return int(duration / 5)
            return None

    async def test(self, session, config):
        protocol = self.get_protocol(config)
        if protocol not in self.protocols:
            return None

        ip = self.find_ip(config)
        if not ip:
            try:
                decoded = base64.b64decode(config.split("://")[1]).decode('utf-8')
                ip = self.find_ip(decoded)
            except:
                pass
            
            if not ip:
                return None

        ping_time = await self.ping(session, ip)
        return ping_time if ping_time is not None else None

    async def test_all(self):
        results = []
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def test_with_semaphore(session, config):
            async with semaphore:
                return await self.test(session, config)
        
        connector = aiohttp.TCPConnector(limit=self.max_concurrent, ttl_dns_cache=300)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [test_with_semaphore(session, config) for config in self.configs]
            
            completed = 0
            for coro in asyncio.as_completed(tasks):
                try:
                    ping_time = await coro
                    if ping_time is not None:
                        results.append((self.configs[completed % len(self.configs)], ping_time))
                    completed += 1
                    if completed % 50 == 0:
                        print(f"Progress: {completed}/{len(self.configs)}")
                except Exception:
                    pass
        
        # 按延迟排序
        results.sort(key=lambda x: x[1])
        return results


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ping_test.py <input_file> [output_file]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 读取配置
    with open(input_file, 'r', encoding='utf-8') as f:
        configs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    print(f"Testing {len(configs)} configs...")
    
    # 测试
    tester = V2RayConfigTester(configs, timeout=2, max_concurrent=100)
    results = asyncio.run(tester.test_all())
    
    print(f"Found {len(results)} working configs")
    
    # 过滤延迟低于500ms的节点
    filtered_results = [(config, ping) for config, ping in results if ping < 500]
    
    print(f"Found {len(filtered_results)} configs with latency < 500ms")
    
    # 输出结果
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            for config, ping in filtered_results:
                f.write(f"{config}\n")
        print(f"Results saved to {output_file}")
    else:
        for config, ping in filtered_results[:10]:
            print(f"{ping}ms - {config[:50]}...")


if __name__ == "__main__":
    main()
