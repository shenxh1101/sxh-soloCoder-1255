#!/usr/bin/env python3
import argparse
import json
import time
import os
import sys
import statistics
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests


DEFAULT_SERVERS = [
    {
        "id": "bj-telecom",
        "name": "测速网-北京电信",
        "region": "华北",
        "city": "北京",
        "isp": "中国电信",
        "tags": ["电信", "国内", "北方"],
        "download_url": "http://speedtest1.bjtelecom.net:8080/download",
        "download_size_param": "size",
        "default_download_size": 25,
        "upload_url": "http://speedtest1.bjtelecom.net:8080/upload",
        "latency_url": "http://speedtest1.bjtelecom.net:8080/ping"
    },
    {
        "id": "sh-unicom",
        "name": "测速网-上海联通",
        "region": "华东",
        "city": "上海",
        "isp": "中国联通",
        "tags": ["联通", "国内", "南方"],
        "download_url": "http://speedtest2.shunicom.net:8080/download",
        "download_size_param": "size",
        "default_download_size": 25,
        "upload_url": "http://speedtest2.shunicom.net:8080/upload",
        "latency_url": "http://speedtest2.shunicom.net:8080/ping"
    },
    {
        "id": "gz-telecom",
        "name": "测速网-广州电信",
        "region": "华南",
        "city": "广州",
        "isp": "中国电信",
        "tags": ["电信", "国内", "南方"],
        "download_url": "http://speedtest3.guangzhou.gd.cn:8080/download",
        "download_size_param": "size",
        "default_download_size": 25,
        "upload_url": "http://speedtest3.guangzhou.gd.cn:8080/upload",
        "latency_url": "http://speedtest3.guangzhou.gd.cn:8080/ping"
    },
    {
        "id": "cloudflare",
        "name": "Cloudflare Global",
        "region": "全球",
        "city": "Anycast",
        "isp": "Cloudflare",
        "tags": ["海外", "CDN", "全球"],
        "download_url": "https://speed.cloudflare.com/__down",
        "download_size_param": "bytes",
        "default_download_size": 25,
        "upload_url": "https://speed.cloudflare.com/__up",
        "latency_url": "https://speed.cloudflare.com/cdn-cgi/trace"
    },
    {
        "id": "google",
        "name": "Google",
        "region": "全球",
        "city": "Anycast",
        "isp": "Google",
        "tags": ["海外", "全球"],
        "download_url": "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",
        "download_size_param": None,
        "default_download_size": 0,
        "upload_url": None,
        "latency_url": "https://www.gstatic.com/generate_204"
    }
]


def build_download_url(server: Dict, size_mb: Optional[int] = None) -> str:
    base_url = server["download_url"]
    size_param = server.get("download_size_param")
    default_size = server.get("default_download_size", 25)
    actual_size = size_mb if size_mb is not None else default_size

    if not size_param or actual_size <= 0:
        return base_url

    size_bytes = actual_size * 1024 * 1024
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)
    query_params[size_param] = [str(size_bytes)]
    new_query = urlencode({k: v[0] if len(v) == 1 else v for k, v in query_params.items()})
    return urlunparse(parsed._replace(query=new_query))


def extract_latency_url(server: Dict) -> str:
    if server.get("latency_url"):
        return server["latency_url"]
    parsed = urlparse(server["download_url"])
    return urlunparse(parsed._replace(path="/", query=""))


def measure_latency(url: str, count: int = 5, timeout: int = 10) -> Dict:
    latencies = []
    errors = []
    for i in range(count):
        try:
            start = time.perf_counter()
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            elapsed = (time.perf_counter() - start) * 1000
            if response.status_code >= 400:
                errors.append(f"HTTP {response.status_code}")
            else:
                latencies.append(elapsed)
        except Exception as e:
            errors.append(str(e))
        if i < count - 1:
                time.sleep(0.1)

    result = {
        "success": len(latencies) > 0,
        "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "min_ms": round(min(latencies), 2) if latencies else 0.0,
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
        "samples": [round(x, 2) for x in latencies],
        "packet_loss": round((1 - len(latencies) / count) * 100, 1) if count > 0 else 100.0,
        "errors": errors,
        "success_count": len(latencies),
        "total_count": count
    }
    return result


def measure_download_speed(url: str, timeout: int = 60) -> Dict:
    start = time.perf_counter()
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        if response.status_code >= 400:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "speed_mbps": 0.0,
                "bytes_transferred": 0,
                "duration_seconds": 0.0
            }
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                total_bytes += len(chunk)
        elapsed = time.perf_counter() - start
        if elapsed <= 0:
            return {
                "success": True,
                "speed_mbps": 0.0,
                "bytes_transferred": total_bytes,
                "duration_seconds": 0.0
            }
        speed_mbps = (total_bytes * 8) / (elapsed * 1_000_000)
        return {
            "success": True,
            "speed_mbps": round(speed_mbps, 2),
            "bytes_transferred": total_bytes,
            "duration_seconds": round(elapsed, 2)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "speed_mbps": 0.0,
            "bytes_transferred": 0,
            "duration_seconds": 0.0
        }


def measure_upload_speed(url: str, data_size_mb: int = 10, timeout: int = 60) -> Dict:
    if not url:
        return {
            "success": False,
            "error": "未配置上传地址",
            "speed_mbps": 0.0,
            "bytes_transferred": 0,
            "duration_seconds": 0.0
        }
    data_size = data_size_mb * 1024 * 1024
    data = os.urandom(data_size)
    start = time.perf_counter()
    try:
        response = requests.post(url, data=data, timeout=timeout)
        elapsed = time.perf_counter() - start
        if response.status_code >= 400:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "speed_mbps": 0.0,
                "bytes_transferred": 0,
                "duration_seconds": 0.0
            }
        if elapsed <= 0:
            return {
                "success": True,
                "speed_mbps": 0.0,
                "bytes_transferred": data_size,
                "duration_seconds": 0.0
            }
        speed_mbps = (data_size * 8) / (elapsed * 1_000_000)
        return {
            "success": True,
            "speed_mbps": round(speed_mbps, 2),
            "bytes_transferred": data_size,
            "duration_seconds": round(elapsed, 2)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "speed_mbps": 0.0,
            "bytes_transferred": 0,
            "duration_seconds": 0.0
        }


def filter_servers_by_tags(servers: List[Dict], tags: List[str]) -> List[Dict]:
    if not tags:
        return servers
    return [s for s in servers if any(t in s.get("tags", []) for t in tags)]


def select_best_server(servers: List[Dict], tags: Optional[List[str]] = None) -> Tuple[Dict, List[Dict]]:
    filtered = filter_servers_by_tags(servers, tags)
    if not filtered:
        filtered = servers

    candidates = []
    for server in filtered:
        latency_url = extract_latency_url(server)
        latency_result = measure_latency(latency_url, count=2, timeout=5)
        candidates.append({
            "server": server,
            "latency": latency_result["avg_ms"] if latency_result["success"] else float('inf'),
            "latency_result": latency_result
        })

    valid_candidates = [c for c in candidates if c["latency"] != float('inf')]
    if not valid_candidates:
        best = filtered[0]
        selection_reason = [{
            "server_id": s["server"]["id"],
            "server_name": s["server"]["name"],
            "latency_ms": s["latency_result"]["avg_ms"],
            "success": s["latency_result"]["success"],
            "errors": s["latency_result"]["errors"]
        } for s in candidates]
        return best, selection_reason

    valid_candidates.sort(key=lambda x: x["latency"])
    best = valid_candidates[0]["server"]
    selection_reason = [{
        "server_id": c["server"]["id"],
        "server_name": c["server"]["name"],
        "latency_ms": c["latency_result"]["avg_ms"],
        "success": c["latency_result"]["success"],
        "errors": c["latency_result"]["errors"]
    } for c in candidates]
    return best, selection_reason


def evaluate_network_quality(download_mbps: float, upload_mbps: float, latency_ms: float,
                           download_ok: bool, upload_ok: bool, latency_ok: bool) -> Tuple[str, str]:
    score = 0
    issues = []

    if not download_ok:
        issues.append("下载测试失败")
    if not upload_ok:
        issues.append("上传测试失败")
    if not latency_ok:
        issues.append("延迟测试失败")

    if download_ok and download_mbps >= 100:
        score += 3
    elif download_ok and download_mbps >= 50:
        score += 2
    elif download_ok and download_mbps >= 10:
        score += 1

    if upload_ok and upload_mbps >= 50:
        score += 3
    elif upload_ok and upload_mbps >= 20:
        score += 2
    elif upload_ok and upload_mbps >= 5:
        score += 1

    if latency_ok and latency_ms <= 30:
        score += 3
    elif latency_ok and latency_ms <= 80:
        score += 2
    elif latency_ok and latency_ms <= 150:
        score += 1

    if issues:
        quality = "测试未完全成功"
        suggestion = "部分测试项目失败，" + "、".join(issues) + "，建议检查网络连接或更换测试服务器。"
        return quality, suggestion

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

    extra = []
    if download_ok and download_mbps < 5:
        extra.append("下载速度较慢，可能影响文件下载和视频观看体验")
    if upload_ok and upload_mbps < 3:
        extra.append("上传速度较慢，视频会议和文件上传可能受影响")
    if latency_ok and latency_ms > 100:
        extra.append("延迟较高，在线游戏和实时视频通话体验较差")

    if extra:
        suggestion += " " + "；".join(extra) + "。"

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


def run_test(server: Dict, upload_size_mb: int = 10, download_size_mb: Optional[int] = None,
              skip_upload: bool = False, selection_reason: Optional[List[Dict]] = None,
              selection_method: str = "default") -> Dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    local_time = datetime.now().isoformat()

    actual_download_size = download_size_mb if download_size_mb is not None else server.get("default_download_size", 25)
    download_url = build_download_url(server, download_size_mb)
    latency_url = extract_latency_url(server)

    print(f"正在测试延迟 (目标: {latency_url})...", file=sys.stderr)
    latency_result = measure_latency(latency_url)

    print(f"正在测试下载速度 (文件: {download_url})...", file=sys.stderr)
    download_result = measure_download_speed(download_url)

    upload_result = {
        "success": False, "error": "已跳过", "speed_mbps": 0.0,
        "bytes_transferred": 0, "duration_seconds": 0.0
    }
    if not skip_upload and server.get("upload_url"):
        print(f"正在测试上传速度...", file=sys.stderr)
        upload_result = measure_upload_speed(server["upload_url"], data_size_mb=upload_size_mb)

    quality, suggestion = evaluate_network_quality(
        download_result["speed_mbps"],
        upload_result["speed_mbps"],
        latency_result["avg_ms"],
        download_result["success"],
        upload_result["success"] if not skip_upload else True,
        latency_result["success"]
    )

    all_ok = download_result["success"] and (skip_upload or upload_result["success"]) and latency_result["success"]

    result = {
        "timestamp": timestamp,
        "local_time": local_time,
        "test_success": all_ok,
        "server_selection": {
            "method": selection_method,
            "selected_server_id": server.get("id"),
            "selected_server_name": server["name"],
            "reason": selection_reason or []
        },
        "server": {
            "id": server.get("id"),
            "name": server["name"],
            "region": server.get("region"),
            "city": server.get("city"),
            "isp": server.get("isp"),
            "tags": server.get("tags", []),
            "download_url": download_url,
            "upload_url": server.get("upload_url"),
            "latency_url": latency_url
        },
        "test_config": {
            "download_size_mb": actual_download_size,
            "upload_size_mb": upload_size_mb if not skip_upload else 0,
            "skip_upload": skip_upload
        },
        "download": download_result,
        "upload": upload_result,
        "latency": latency_result,
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
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("servers", [])


def read_jsonl(filepath: str) -> List[Dict]:
    results = []
    if not os.path.exists(filepath):
        return results
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results


def filter_by_time_range(results: List[Dict], hours: int) -> List[Dict]:
    if hours <= 0:
        return results
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered = []
    for r in results:
        try:
            ts_str = r.get("timestamp")
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            ts = datetime.fromisoformat(ts_str)
            if ts >= cutoff:
                filtered.append(r)
        except (ValueError, TypeError):
            continue
    return filtered


def analyze_results(results: List[Dict]) -> Dict:
    if not results:
        return {
            "total_tests": 0,
            "time_range": None,
            "summary": {},
            "quality_distribution": {},
            "server_distribution": {}
        }

    download_speeds = [r["download"]["speed_mbps"] for r in results if r.get("download", {}).get("success", False) and r["download"]["speed_mbps"] > 0]
    upload_speeds = [r["upload"]["speed_mbps"] for r in results if r.get("upload", {}).get("success", False) and r["upload"]["speed_mbps"] > 0]
    latencies = [r["latency"]["avg_ms"] for r in results if r.get("latency", {}).get("success", False) and r["latency"]["avg_ms"] > 0]

    quality_counts: Dict[str, int] = {}
    for r in results:
        q = r.get("quality_evaluation", {}).get("quality", "未知")
        quality_counts[q] = quality_counts.get(q, 0) + 1

    server_counts: Dict[str, int] = {}
    for r in results:
        s = r.get("server", {}).get("name", "未知")
        server_counts[s] = server_counts.get(s, 0) + 1

    success_count = sum(1 for r in results if r.get("test_success", False))

    timestamps = []
    for r in results:
        try:
            ts_str = r.get("timestamp")
            if ts_str and ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            timestamps.append(datetime.fromisoformat(ts_str))
        except (ValueError, TypeError):
            continue

    time_range = None
    if timestamps:
        time_range = {
            "start": min(timestamps).isoformat(),
            "end": max(timestamps).isoformat(),
            "duration_hours": round((max(timestamps) - min(timestamps)).total_seconds() / 3600, 2)
        }

    summary = {
        "download": {
            "count": len(download_speeds),
            "avg_mbps": round(statistics.mean(download_speeds), 2) if download_speeds else 0.0,
            "min_mbps": round(min(download_speeds), 2) if download_speeds else 0.0,
            "max_mbps": round(max(download_speeds), 2) if download_speeds else 0.0,
            "median_mbps": round(statistics.median(download_speeds), 2) if download_speeds else 0.0
        },
        "upload": {
            "count": len(upload_speeds),
            "avg_mbps": round(statistics.mean(upload_speeds), 2) if upload_speeds else 0.0,
            "min_mbps": round(min(upload_speeds), 2) if upload_speeds else 0.0,
            "max_mbps": round(max(upload_speeds), 2) if upload_speeds else 0.0,
            "median_mbps": round(statistics.median(upload_speeds), 2) if upload_speeds else 0.0
        },
        "latency": {
            "count": len(latencies),
            "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "min_ms": round(min(latencies), 2) if latencies else 0.0,
            "max_ms": round(max(latencies), 2) if latencies else 0.0,
            "median_ms": round(statistics.median(latencies), 2) if latencies else 0.0
        },
        "success_rate": round(success_count / len(results) * 100, 1) if results else 0.0
    }

    quality_distribution = {k: {"count": v, "percentage": round(v / len(results) * 100, 1)} for k, v in quality_counts.items()}
    server_distribution = {k: {"count": v, "percentage": round(v / len(results) * 100, 1)} for k, v in server_counts.items()}

    trend_data = []
    for r in results:
        trend_data.append({
            "timestamp": r.get("timestamp"),
            "local_time": r.get("local_time"),
            "download_mbps": r.get("download", {}).get("speed_mbps", 0),
            "upload_mbps": r.get("upload", {}).get("speed_mbps", 0),
            "latency_ms": r.get("latency", {}).get("avg_ms", 0),
            "quality": r.get("quality_evaluation", {}).get("quality", ""),
            "success": r.get("test_success", False)
        })

    return {
        "total_tests": len(results),
        "time_range": time_range,
        "summary": summary,
        "quality_distribution": quality_distribution,
        "server_distribution": server_distribution,
        "trend": trend_data
    }


def cmd_analyze(args):
    results = read_jsonl(args.input)
    filtered = filter_by_time_range(results, args.hours)
    analysis = analyze_results(filtered)
    print(json.dumps(analysis, ensure_ascii=False, indent=2))


def cmd_test(args):
    servers = DEFAULT_SERVERS.copy()
    if args.servers_file:
        custom_servers = load_custom_servers(args.servers_file)
        if custom_servers:
            servers = custom_servers

    selected_server = None
    selection_reason = None
    selection_method = "default"

    if args.download_url:
        size_param = None
        parsed = urlparse(args.download_url)
        query_params = parse_qs(parsed.query)
        if "size" in query_params:
            size_param = "size"
        elif "bytes" in query_params:
            size_param = "bytes"
        selected_server = {
            "id": "custom",
            "name": args.server_name,
            "region": None,
            "city": None,
            "isp": None,
            "tags": ["自定义"],
            "download_url": args.download_url,
            "download_size_param": size_param,
            "default_download_size": args.download_size if args.download_size else 25,
            "upload_url": args.upload_url,
            "latency_url": args.latency_url
        }
        selection_method = "manual_url"
    elif args.auto_select:
        if not args.json:
            print("正在自动选择最近的服务器...", file=sys.stderr)
        selected_server, selection_reason = select_best_server(servers, tags=args.tags)
        selection_method = "auto_select"
        if not args.json:
            print(f"已选择服务器: {selected_server['name']} (延迟: {selection_reason[0]['latency_ms']:.2f} ms)", file=sys.stderr)
    else:
        filtered = filter_servers_by_tags(servers, args.tags)
        if filtered:
            selected_server = filtered[0]
        else:
            selected_server = servers[0]
        selection_method = "default"

    if not args.json:
        print(f"测试服务器: {selected_server['name']}", file=sys.stderr)
        if selected_server.get("region"):
            print(f"地区: {selected_server.get('region')} - {selected_server.get('city', '')}", file=sys.stderr)
        if selected_server.get("isp"):
            print(f"运营商: {selected_server.get('isp')}", file=sys.stderr)
        if selected_server.get("tags"):
            print(f"标签: {', '.join(selected_server.get('tags', []))}", file=sys.stderr)
        print(f"下载地址: {build_download_url(selected_server, args.download_size)}", file=sys.stderr)
        if selected_server.get("upload_url") and not args.skip_upload:
            print(f"上传地址: {selected_server.get('upload_url')}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

    while True:
        result = run_test(
            selected_server,
            upload_size_mb=args.upload_size,
            download_size_mb=args.download_size,
            skip_upload=args.skip_upload,
            selection_reason=selection_reason,
            selection_method=selection_method
        )

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
            print(f"测试状态: {'成功' if result['test_success'] else '部分失败'}", file=sys.stderr)
            print(f"下载大小: {result['test_config']['download_size_mb']} MB", file=sys.stderr)
            download_status = f" (失败: {result['download'].get('error', '')})" if not result['download']['success'] else ""
            print(f"下载速度: {result['download']['speed_mbps']:.2f} Mbps{download_status}", file=sys.stderr)
            if not args.skip_upload:
                print(f"上传大小: {result['test_config']['upload_size_mb']} MB", file=sys.stderr)
                upload_status = f" (失败: {result['upload'].get('error', '')})" if not result['upload']['success'] else ""
                print(f"上传速度: {result['upload']['speed_mbps']:.2f} Mbps{upload_status}", file=sys.stderr)
            print(f"延迟: {result['latency']['avg_ms']:.2f} ms (min: {result['latency']['min_ms']:.2f}, max: {result['latency']['max_ms']:.2f}, 丢包: {result['latency']['packet_loss']}%)", file=sys.stderr)
            if not result['latency']['success']:
                print(f"延迟测试错误: {', '.join(result['latency']['errors'])}", file=sys.stderr)
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


def main():
    parser = argparse.ArgumentParser(description="网速测试工具 - 输出结构化JSON数据")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    test_parser = subparsers.add_parser("test", help="执行网速测试")
    test_parser.add_argument("--download-url", type=str, help="指定下载测试文件URL")
    test_parser.add_argument("--upload-url", type=str, help="指定上传测试URL")
    test_parser.add_argument("--latency-url", type=str, help="指定延迟测试URL")
    test_parser.add_argument("--server-name", type=str, default="Custom", help="指定服务器名称")
    test_parser.add_argument("--download-size", type=int, help="下载测试文件大小(MB)，默认使用服务器配置")
    test_parser.add_argument("--upload-size", type=int, default=10, help="上传测试文件大小(MB)，默认10MB")
    test_parser.add_argument("--skip-upload", action="store_true", help="跳过上传测试")
    test_parser.add_argument("--auto-select", action="store_true", help="自动选择最近的服务器")
    test_parser.add_argument("--servers-file", type=str, help="自定义服务器列表JSON文件路径")
    test_parser.add_argument("--tags", type=str, nargs="*", help="按标签筛选服务器，如: 电信 国内")
    test_parser.add_argument("--continuous", action="store_true", help="启用连续测试模式")
    test_parser.add_argument("--interval", type=int, default=600, help="连续测试间隔(秒)，默认600秒(10分钟)")
    test_parser.add_argument("--output", type=str, help="JSONL输出文件路径，用于保存连续测试结果")
    test_parser.add_argument("--webhook", type=str, help="测试结果Webhook推送地址")
    test_parser.add_argument("--json", action="store_true", help="仅输出JSON格式结果")

    analyze_parser = subparsers.add_parser("analyze", help="分析历史JSONL数据")
    analyze_parser.add_argument("--input", type=str, required=True, help="JSONL历史数据文件路径")
    analyze_parser.add_argument("--hours", type=int, default=0, help="统计最近N小时的数据，0表示全部数据")

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "test" or args.command is None:
        cmd_test(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
