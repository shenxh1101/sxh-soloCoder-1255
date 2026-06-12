#!/usr/bin/env python3
import argparse
import json
import time
import os
import sys
import statistics
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

import requests


DEFAULT_SERVERS = [
    {"name": "测速网-北京", "download_url": "http://speedtest1.bjtelecom.net:8080/download?size=25000000", "upload_url": "http://speedtest1.bjtelecom.net:8080/upload", "latency_url": "http://speedtest1.bjtelecom.net:8080/ping"},
    {"name": "测速网-上海", "download_url": "http://speedtest2.shunicom.net:8080/download?size=25000000", "upload_url": "http://speedtest2.shunicom.net:8080/upload", "latency_url": "http://speedtest2.shunicom.net:8080/ping"},
    {"name": "测速网-广州", "download_url": "http://speedtest3.guangzhou.gd.cn:8080/download?size=25000000", "upload_url": "http://speedtest3.guangzhou.gd.cn:8080/upload", "latency_url": "http://speedtest3.guangzhou.gd.cn:8080/ping"},
    {"name": "Cloudflare", "download_url": "https://speed.cloudflare.com/__down?bytes=25000000", "upload_url": "https://speed.cloudflare.com/__up", "latency_url": "https://speed.cloudflare.com/cdn-cgi/trace"},
    {"name": "Google", "download_url": "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png", "upload_url": None, "latency_url": "https://www.google.com"},
]


def measure_latency(url: str, count: int = 5, timeout: int = 10) -> Tuple[float, float, float, List[float]]:
    latencies = []
    for _ in range(count):
        try:
            start = time.perf_counter()
            requests.get(url, timeout=timeout)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)
        except Exception:
            pass
        time.sleep(0.1)
    
    if not latencies:
        return 0.0, 0.0, 0.0, []
    
    return (
        statistics.mean(latencies),
        min(latencies),
        max(latencies),
        latencies
    )


def measure_download_speed(url: str, timeout: int = 60) -> Tuple[float, int, float]:
    start = time.perf_counter()
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                total_bytes += len(chunk)
        elapsed = time.perf_counter() - start
        if elapsed <= 0:
            return 0.0, total_bytes, 0.0
        speed_mbps = (total_bytes * 8) / (elapsed * 1_000_000)
        return speed_mbps, total_bytes, elapsed
    except Exception as e:
        print(f"下载测试失败: {e}", file=sys.stderr)
        return 0.0, 0, 0.0


def measure_upload_speed(url: str, data_size_mb: int = 10, timeout: int = 60) -> Tuple[float, int, float]:
    if not url:
        return 0.0, 0, 0.0
    
    data_size = data_size_mb * 1024 * 1024
    data = os.urandom(data_size)
    
    start = time.perf_counter()
    try:
        response = requests.post(url, data=data, timeout=timeout)
        elapsed = time.perf_counter() - start
        if elapsed <= 0:
            return 0.0, data_size, 0.0
        speed_mbps = (data_size * 8) / (elapsed * 1_000_000)
        return speed_mbps, data_size, elapsed
    except Exception as e:
        print(f"上传测试失败: {e}", file=sys.stderr)
        return 0.0, 0, 0.0


def select_best_server(servers: List[Dict]) -> Dict:
    best_server = None
    best_latency = float('inf')
    
    for server in servers:
        try:
            latency, _, _, _ = measure_latency(server["latency_url"], count=2, timeout=5)
            if latency > 0 and latency < best_latency:
                best_latency = latency
                best_server = server
        except Exception:
            continue
    
    return best_server or servers[0]


def evaluate_network_quality(download_mbps: float, upload_mbps: float, latency_ms: float) -> Tuple[str, str]:
    score = 0
    
    if download_mbps >= 100:
        score += 3
    elif download_mbps >= 50:
        score += 2
    elif download_mbps >= 10:
        score += 1
    
    if upload_mbps >= 50:
        score += 3
    elif upload_mbps >= 20:
        score += 2
    elif upload_mbps >= 5:
        score += 1
    
    if latency_ms <= 30:
        score += 3
    elif latency_ms <= 80:
        score += 2
    elif latency_ms <= 150:
        score += 1
    
    quality = "网络质量优秀"
    suggestion = "网络状态极佳，适合所有网络活动。"
    
    if score >= 8:
        quality = "网络质量优秀"
        suggestion = "网络状态极佳，流畅支持4K视频、高清视频会议和在线游戏。"
    elif score >= 6:
        quality = "网络质量良好"
        suggestion = "网络状态良好，适合高清视频会议和日常网页浏览。"
    elif score >= 4:
        quality = "网络质量一般"
        suggestion = "网络状态一般，视频会议可能偶尔卡顿，建议关闭其他占用带宽的程序。"
    elif score >= 2:
        quality = "网络质量较差"
        suggestion = "网络质量较差，网页浏览较慢，视频通话可能不流畅，建议检查网络连接或联系运营商。"
    else:
        quality = "网络质量很差"
        suggestion = "网络质量很差，基本网络活动都受影响，请立即检查网络连接。"
    
    if download_mbps < 5:
        suggestion += " 下载速度较慢，可能影响文件下载和视频观看体验。"
    if upload_mbps < 3:
        suggestion += " 上传速度较慢，视频会议和文件上传可能受影响。"
    if latency_ms > 100:
        suggestion += " 延迟较高，在线游戏和实时视频通话体验较差。"
    
    return quality, suggestion.strip()


def send_to_webhook(webhook_url: str, result: Dict, timeout: int = 10) -> bool:
    try:
        response = requests.post(
            webhook_url,
            json=result,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        return 200 <= response.status_code < 300
    except Exception as e:
        print(f"发送到 Webhook 失败: {e}", file=sys.stderr)
        return False


def run_test(server: Dict, upload_size_mb: int = 10, skip_upload: bool = False) -> Dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    local_time = datetime.now().isoformat()
    
    print(f"正在测试延迟...", file=sys.stderr)
    latency_avg, latency_min, latency_max, latencies = measure_latency(server["latency_url"])
    
    print(f"正在测试下载速度...", file=sys.stderr)
    download_mbps, download_bytes, download_time = measure_download_speed(server["download_url"])
    
    upload_mbps, upload_bytes, upload_time = 0.0, 0, 0.0
    if not skip_upload and server["upload_url"]:
        print(f"正在测试上传速度...", file=sys.stderr)
        upload_mbps, upload_bytes, upload_time = measure_upload_speed(server["upload_url"], data_size_mb=upload_size_mb)
    
    quality, suggestion = evaluate_network_quality(download_mbps, upload_mbps, latency_avg)
    
    result = {
        "timestamp": timestamp,
        "local_time": local_time,
        "server": {
            "name": server["name"],
            "download_url": server["download_url"],
            "upload_url": server["upload_url"],
            "latency_url": server["latency_url"]
        },
        "download": {
            "speed_mbps": round(download_mbps, 2),
            "bytes_transferred": download_bytes,
            "duration_seconds": round(download_time, 2)
        },
        "upload": {
            "speed_mbps": round(upload_mbps, 2),
            "bytes_transferred": upload_bytes,
            "duration_seconds": round(upload_time, 2)
        },
        "latency": {
            "avg_ms": round(latency_avg, 2),
            "min_ms": round(latency_min, 2),
            "max_ms": round(latency_max, 2),
            "samples": [round(x, 2) for x in latencies]
        },
        "quality_evaluation": {
            "quality": quality,
            "suggestion": suggestion
        }
    }
    
    return result


def append_to_jsonl(filepath: str, result: Dict) -> None:
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def load_custom_servers(filepath: str) -> List[Dict]:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="网速测试工具 - 输出结构化JSON数据")
    parser.add_argument("--download-url", type=str, help="指定下载测试文件URL")
    parser.add_argument("--upload-url", type=str, help="指定上传测试URL")
    parser.add_argument("--latency-url", type=str, help="指定延迟测试URL")
    parser.add_argument("--server-name", type=str, default="Custom", help="指定服务器名称")
    parser.add_argument("--upload-size", type=int, default=10, help="上传测试文件大小(MB)，默认10MB")
    parser.add_argument("--skip-upload", action="store_true", help="跳过上传测试")
    parser.add_argument("--auto-select", action="store_true", help="自动选择最近的服务器")
    parser.add_argument("--servers-file", type=str, help="自定义服务器列表JSON文件路径")
    parser.add_argument("--continuous", action="store_true", help="启用连续测试模式")
    parser.add_argument("--interval", type=int, default=600, help="连续测试间隔(秒)，默认600秒(10分钟)")
    parser.add_argument("--output", type=str, help="JSONL输出文件路径，用于保存连续测试结果")
    parser.add_argument("--webhook", type=str, help="测试结果Webhook推送地址")
    parser.add_argument("--json", action="store_true", help="仅输出JSON格式结果")
    
    args = parser.parse_args()
    
    servers = DEFAULT_SERVERS.copy()
    if args.servers_file:
        custom_servers = load_custom_servers(args.servers_file)
        if custom_servers:
            servers = custom_servers
    
    selected_server = None
    if args.download_url:
        selected_server = {
            "name": args.server_name,
            "download_url": args.download_url,
            "upload_url": args.upload_url,
            "latency_url": args.latency_url or args.download_url
        }
    elif args.auto_select:
        if not args.json:
            print("正在自动选择最近的服务器...", file=sys.stderr)
        selected_server = select_best_server(servers)
        if not args.json:
            print(f"已选择服务器: {selected_server['name']}", file=sys.stderr)
    else:
        selected_server = servers[0]
    
    if not args.json:
        print(f"测试服务器: {selected_server['name']}", file=sys.stderr)
        print(f"下载地址: {selected_server['download_url']}", file=sys.stderr)
        if selected_server['upload_url'] and not args.skip_upload:
            print(f"上传地址: {selected_server['upload_url']}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
    
    while True:
        result = run_test(selected_server, upload_size_mb=args.upload_size, skip_upload=args.skip_upload)
        
        if args.output:
            append_to_jsonl(args.output, result)
            if not args.json:
                print(f"结果已追加到: {args.output}", file=sys.stderr)
        
        if args.webhook:
            success = send_to_webhook(args.webhook, result)
            if not args.json:
                if success:
                    print("Webhook 推送成功", file=sys.stderr)
                else:
                    print("Webhook 推送失败", file=sys.stderr)
        
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("=" * 60, file=sys.stderr)
            print(f"测试时间: {result['local_time']}", file=sys.stderr)
            print(f"下载速度: {result['download']['speed_mbps']:.2f} Mbps", file=sys.stderr)
            print(f"上传速度: {result['upload']['speed_mbps']:.2f} Mbps", file=sys.stderr)
            print(f"延迟: {result['latency']['avg_ms']:.2f} ms (min: {result['latency']['min_ms']:.2f}, max: {result['latency']['max_ms']:.2f})", file=sys.stderr)
            print(f"网络质量: {result['quality_evaluation']['quality']}", file=sys.stderr)
            print(f"建议: {result['quality_evaluation']['suggestion']}", file=sys.stderr)
        
        if not args.continuous:
            break
        
        print(f"\n等待 {args.interval} 秒后进行下一次测试... (Ctrl+C 停止)", file=sys.stderr)
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n测试已停止", file=sys.stderr)
            break


if __name__ == "__main__":
    main()
