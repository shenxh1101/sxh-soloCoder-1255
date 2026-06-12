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


class JsonErrorArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        self._json_mode = False
        self._command_name = kwargs.pop("command_name", None)
        super().__init__(*args, **kwargs)

    def set_json_mode(self, enabled: bool, command: str = None):
        self._json_mode = enabled
        self._command_name = command

    def error(self, message):
        if self._json_mode:
            param = self._extract_param_from_error(message)
            output_error_json(
                f"参数错误: {message}",
                "argument_error",
                {
                    "command": self._command_name or "unknown",
                    "invalid_param": param,
                    "message": message
                }
            )
        else:
            super().error(message)

    def _extract_param_from_error(self, message: str) -> Optional[str]:
        if "argument" in message:
            parts = message.split("argument")
            if len(parts) > 1:
                param_part = parts[1].strip().split(":")[0].strip()
                return param_part.strip("'\"")
        return None


DEFAULT_SERVERS = [
    {
        "id": "bj-telecom",
        "name": "测速网-北京电信",
        "region": "华北",
        "city": "北京",
        "isp": "中国电信",
        "tags": ["电信", "国内", "北方"],
        "weight": 10,
        "disabled": False,
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
        "weight": 10,
        "disabled": False,
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
        "weight": 10,
        "disabled": False,
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
        "weight": 5,
        "disabled": False,
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
        "weight": 3,
        "disabled": False,
        "download_url": "https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png",
        "download_size_param": None,
        "default_download_size": 0,
        "upload_url": None,
        "latency_url": "https://www.gstatic.com/generate_204"
    }
]


def output_error_json(message: str, error_type: str = "error", details: Optional[Dict] = None) -> None:
    error_result = {
        "success": False,
        "error": error_type,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    if details:
        error_result["details"] = details
    print(json.dumps(error_result, ensure_ascii=False, indent=2))
    sys.exit(1)


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

    return {
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


def get_active_servers(servers: List[Dict]) -> List[Dict]:
    return [s for s in servers if not s.get("disabled", False)]


def filter_servers_by_tags(servers: List[Dict], tags: Optional[List[str]]) -> Tuple[List[Dict], bool]:
    if not tags:
        return servers, True
    filtered = [s for s in servers if any(t in s.get("tags", []) for t in tags)]
    return filtered, len(filtered) > 0


def select_best_server(servers: List[Dict], tags: Optional[List[str]] = None) -> Tuple[Dict, List[Dict], bool]:
    active = get_active_servers(servers)
    tag_matched = True

    if tags:
        active, tag_matched = filter_servers_by_tags(active, tags)
        if not tag_matched:
            return None, [], False

    if not active:
        return None, [], tag_matched

    candidates = []
    for server in active:
        latency_url = extract_latency_url(server)
        latency_result = measure_latency(latency_url, count=2, timeout=5)
        weight = server.get("weight", 10)
        effective_latency = latency_result["avg_ms"] if latency_result["success"] else float('inf')
        weighted_score = effective_latency / (weight / 10) if effective_latency != float('inf') else float('inf')
        candidates.append({
            "server": server,
            "weight": weight,
            "latency": effective_latency,
            "weighted_score": weighted_score,
            "latency_result": latency_result
        })

    valid_candidates = [c for c in candidates if c["latency"] != float('inf')]
    if not valid_candidates:
        best = active[0]
        selection_reason = [{
            "server_id": c["server"]["id"],
            "server_name": c["server"]["name"],
            "weight": c["weight"],
            "latency_ms": c["latency_result"]["avg_ms"],
            "weighted_score": None,
            "success": c["latency_result"]["success"],
            "errors": c["latency_result"]["errors"]
        } for c in candidates]
        return best, selection_reason, tag_matched

    valid_candidates.sort(key=lambda x: x["weighted_score"])
    best = valid_candidates[0]["server"]
    selection_reason = [{
        "server_id": c["server"]["id"],
        "server_name": c["server"]["name"],
        "weight": c["weight"],
        "latency_ms": c["latency_result"]["avg_ms"],
        "weighted_score": round(c["weighted_score"], 2) if c["weighted_score"] != float('inf') else None,
        "success": c["latency_result"]["success"],
        "errors": c["latency_result"]["errors"]
    } for c in candidates]
    return best, selection_reason, tag_matched


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


def check_alert_rules(result: Dict, alert_rules: Dict) -> Dict:
    if not alert_rules:
        return {"triggered": False, "rules_triggered": []}

    triggered_rules = []
    download_threshold = alert_rules.get("download_min_mbps")
    latency_threshold = alert_rules.get("latency_max_ms")
    fail_count_threshold = alert_rules.get("consecutive_fail")

    if download_threshold is not None and result["download"]["success"]:
        if result["download"]["speed_mbps"] < download_threshold:
            triggered_rules.append({
                "rule": "download_below_threshold",
                "threshold_mbps": download_threshold,
                "actual_mbps": result["download"]["speed_mbps"],
                "message": f"下载速度 {result['download']['speed_mbps']:.2f} Mbps 低于阈值 {download_threshold} Mbps"
            })

    if latency_threshold is not None and result["latency"]["success"]:
        if result["latency"]["avg_ms"] > latency_threshold:
            triggered_rules.append({
                "rule": "latency_above_threshold",
                "threshold_ms": latency_threshold,
                "actual_ms": result["latency"]["avg_ms"],
                "message": f"延迟 {result['latency']['avg_ms']:.2f} ms 超过阈值 {latency_threshold} ms"
            })

    if fail_count_threshold is not None:
        consecutive_fails = alert_rules.get("_consecutive_fail_count")
        if consecutive_fails is None:
            consecutive_fails = 0
            if not result["test_success"]:
                consecutive_fails = 1
                if alert_rules.get("_recent_results"):
                    for prev in reversed(alert_rules["_recent_results"]):
                        if not prev.get("test_success", True):
                            consecutive_fails += 1
                        else:
                            break
        if consecutive_fails >= fail_count_threshold:
            triggered_rules.append({
                "rule": "consecutive_failures",
                "threshold_count": fail_count_threshold,
                "actual_count": consecutive_fails,
                "message": f"连续测试失败 {consecutive_fails} 次，达到阈值 {fail_count_threshold} 次"
            })

    return {
        "triggered": len(triggered_rules) > 0,
        "rules_triggered": triggered_rules
    }


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
              selection_method: str = "default", tag_matched: bool = True) -> Dict:
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
            "tag_matched": tag_matched,
            "reason": selection_reason or []
        },
        "server": {
            "id": server.get("id"),
            "name": server["name"],
            "region": server.get("region"),
            "city": server.get("city"),
            "isp": server.get("isp"),
            "tags": server.get("tags", []),
            "weight": server.get("weight", 10),
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
        },
        "alert": {
            "triggered": False,
            "rules_triggered": []
        }
    }

    return result


def append_to_jsonl(filepath: str, result: Dict) -> None:
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def load_state(filepath: str) -> Dict:
    if not os.path.exists(filepath):
        return {
            "last_success_time": None,
            "consecutive_failures": 0,
            "total_tests": 0,
            "total_success": 0,
            "total_failed": 0,
            "recent_alerts": [],
            "recent_results": []
        }
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "last_success_time": None,
            "consecutive_failures": 0,
            "total_tests": 0,
            "total_success": 0,
            "total_failed": 0,
            "recent_alerts": [],
            "recent_results": []
        }


def save_state(filepath: str, state: Dict) -> None:
    try:
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存状态文件失败: {e}", file=sys.stderr)


def update_state_with_result(state: Dict, result: Dict, max_recent: int = 10) -> Dict:
    state["total_tests"] = state.get("total_tests", 0) + 1
    if result.get("test_success"):
        state["total_success"] = state.get("total_success", 0) + 1
        state["consecutive_failures"] = 0
        state["last_success_time"] = result.get("timestamp")
    else:
        state["total_failed"] = state.get("total_failed", 0) + 1
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1

    recent = state.get("recent_results", [])
    recent.append(result)
    state["recent_results"] = recent[-max_recent:]

    if result.get("alert", {}).get("triggered"):
        alerts = state.get("recent_alerts", [])
        alerts.append({
            "timestamp": result.get("timestamp"),
            "rules": result["alert"]["rules_triggered"]
        })
        state["recent_alerts"] = alerts[-max_recent:]

    return state


def load_custom_servers(filepath: str) -> Tuple[List[Dict], Optional[str]]:
    if not os.path.exists(filepath):
        return [], f"服务器配置文件不存在: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [], f"服务器配置文件JSON格式错误: {e}"
    except Exception as e:
        return [], f"读取服务器配置文件失败: {e}"
    if isinstance(data, list):
        return data, None
    return data.get("servers", []), None


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
        except (ValueError, TypeError, AttributeError):
            continue
    return filtered


def filter_by_time_window(results: List[Dict], start_hours_ago: int, end_hours_ago: int) -> List[Dict]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=start_hours_ago)
    end = now - timedelta(hours=end_hours_ago)
    filtered = []
    for r in results:
        try:
            ts_str = r.get("timestamp")
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            ts = datetime.fromisoformat(ts_str)
            if start <= ts <= end:
                filtered.append(r)
        except (ValueError, TypeError, AttributeError):
            continue
    return filtered


def filter_baseline_window(results: List[Dict], days: int = 7, target_hour: Optional[int] = None) -> List[Dict]:
    if target_hour is None:
        target_hour = datetime.now(timezone.utc).hour
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    filtered = []
    for r in results:
        try:
            ts_str = r.get("timestamp")
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            ts = datetime.fromisoformat(ts_str)
            if ts >= start and ts.hour == target_hour:
                filtered.append(r)
        except (ValueError, TypeError, AttributeError):
            continue
    return filtered


def compute_baseline(values: List[float]) -> Dict:
    if not values:
        return {
            "count": 0,
            "mean": 0.0,
            "stddev": 0.0,
            "min": 0.0,
            "max": 0.0,
            "normal_low": 0.0,
            "normal_high": 0.0
        }
    mean_val = statistics.mean(values)
    stddev_val = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "count": len(values),
        "mean": round(mean_val, 2),
        "stddev": round(stddev_val, 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "normal_low": round(mean_val - 2 * stddev_val, 2),
        "normal_high": round(mean_val + 2 * stddev_val, 2)
    }


def classify_anomaly(value: float, baseline: Dict, is_higher_bad: bool = False) -> Dict:
    if baseline["count"] == 0:
        return {"level": "unknown", "deviation_percent": 0.0, "within_normal_range": False}

    mean_val = baseline["mean"]
    stddev_val = baseline["stddev"]

    if mean_val == 0:
        deviation_pct = 0.0 if value == 0 else None
    else:
        deviation_pct = round(((value - mean_val) / mean_val) * 100, 2)

    normal_low = baseline["normal_low"]
    normal_high = baseline["normal_high"]
    within = normal_low <= value <= normal_high

    if stddev_val == 0:
        level = "normal" if value == mean_val else "mild"
    else:
        z_score = abs((value - mean_val) / stddev_val)
        if z_score < 1:
            level = "normal"
        elif z_score < 2:
            level = "mild"
        elif z_score < 3:
            level = "severe"
        else:
            level = "critical"

    if is_higher_bad and value > mean_val:
        pass
    elif not is_higher_bad and value < mean_val:
        pass
    else:
        if level == "severe":
            level = "mild"
        elif level == "critical":
            level = "severe"

    return {
        "level": level,
        "deviation_percent": deviation_pct,
        "within_normal_range": within,
        "z_score": round(abs((value - mean_val) / stddev_val), 2) if stddev_val > 0 else None
    }


def compute_summary(results: List[Dict]) -> Dict:
    if not results:
        return {
            "count": 0,
            "download": {"avg_mbps": 0.0, "min_mbps": 0.0, "max_mbps": 0.0, "median_mbps": 0.0},
            "upload": {"avg_mbps": 0.0, "min_mbps": 0.0, "max_mbps": 0.0, "median_mbps": 0.0},
            "latency": {"avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "median_ms": 0.0},
            "success_rate": 0.0,
            "quality_distribution": {}
        }

    download_speeds = [r["download"]["speed_mbps"] for r in results if r.get("download", {}).get("success", False) and r["download"]["speed_mbps"] > 0]
    upload_speeds = [r["upload"]["speed_mbps"] for r in results if r.get("upload", {}).get("success", False) and r["upload"]["speed_mbps"] > 0]
    latencies = [r["latency"]["avg_ms"] for r in results if r.get("latency", {}).get("success", False) and r["latency"]["avg_ms"] > 0]

    quality_counts: Dict[str, int] = {}
    for r in results:
        q = r.get("quality_evaluation", {}).get("quality", "未知")
        quality_counts[q] = quality_counts.get(q, 0) + 1

    success_count = sum(1 for r in results if r.get("test_success", False))

    return {
        "count": len(results),
        "download": {
            "avg_mbps": round(statistics.mean(download_speeds), 2) if download_speeds else 0.0,
            "min_mbps": round(min(download_speeds), 2) if download_speeds else 0.0,
            "max_mbps": round(max(download_speeds), 2) if download_speeds else 0.0,
            "median_mbps": round(statistics.median(download_speeds), 2) if download_speeds else 0.0
        },
        "upload": {
            "avg_mbps": round(statistics.mean(upload_speeds), 2) if upload_speeds else 0.0,
            "min_mbps": round(min(upload_speeds), 2) if upload_speeds else 0.0,
            "max_mbps": round(max(upload_speeds), 2) if upload_speeds else 0.0,
            "median_mbps": round(statistics.median(upload_speeds), 2) if upload_speeds else 0.0
        },
        "latency": {
            "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "min_ms": round(min(latencies), 2) if latencies else 0.0,
            "max_ms": round(max(latencies), 2) if latencies else 0.0,
            "median_ms": round(statistics.median(latencies), 2) if latencies else 0.0
        },
        "success_rate": round(success_count / len(results) * 100, 1) if results else 0.0,
        "quality_distribution": quality_counts
    }


def calc_change(current: float, previous: float) -> Dict:
    if previous == 0:
        if current == 0:
            return {"change": 0.0, "percentage": 0.0, "direction": "unchanged"}
        return {"change": round(current, 2), "percentage": None, "direction": "increased"}
    change = current - previous
    percentage = round((change / previous) * 100, 2)
    direction = "increased" if change > 0 else ("decreased" if change < 0 else "unchanged")
    return {"change": round(change, 2), "percentage": percentage, "direction": direction}


def compare_quality_distributions(current_qd: Dict, previous_qd: Dict) -> Dict:
    all_qualities = set(list(current_qd.keys()) + list(previous_qd.keys()))
    comparison = {}
    for q in all_qualities:
        curr = current_qd.get(q, 0)
        prev = previous_qd.get(q, 0)
        comparison[q] = {
            "current": curr,
            "previous": prev,
            "change": curr - prev
        }
    return comparison


def analyze_results(results: List[Dict]) -> Dict:
    if not results:
        return {
            "total_tests": 0,
            "time_range": None,
            "summary": compute_summary([]),
            "server_distribution": {}
        }

    summary = compute_summary(results)

    server_counts: Dict[str, int] = {}
    for r in results:
        s = r.get("server", {}).get("name", "未知")
        server_counts[s] = server_counts.get(s, 0) + 1

    server_distribution = {k: {"count": v, "percentage": round(v / len(results) * 100, 1)} for k, v in server_counts.items()}

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

    trend_data = []
    for r in results:
        trend_data.append({
            "timestamp": r.get("timestamp"),
            "local_time": r.get("local_time"),
            "download_mbps": r.get("download", {}).get("speed_mbps", 0),
            "upload_mbps": r.get("upload", {}).get("speed_mbps", 0),
            "latency_ms": r.get("latency", {}).get("avg_ms", 0),
            "quality": r.get("quality_evaluation", {}).get("quality", ""),
            "success": r.get("test_success", False),
            "alert": r.get("alert", {}).get("triggered", False)
        })

    return {
        "total_tests": len(results),
        "time_range": time_range,
        "summary": summary,
        "server_distribution": server_distribution,
        "trend": trend_data
    }


def cmd_baseline(args):
    try:
        results = read_jsonl(args.input)
        if not results:
            output_error_json("JSONL文件为空或不存在", "no_data")

        target_hour = getattr(args, "hour", None)
        if target_hour is None:
            target_hour = datetime.now(timezone.utc).hour

        baseline_days = getattr(args, "baseline_days", 7)
        compare_hours = getattr(args, "hours", 1)

        baseline_results = filter_baseline_window(results, days=baseline_days, target_hour=target_hour)
        current_results = filter_by_time_range(results, compare_hours)

        if not baseline_results:
            output_error_json(f"最近 {baseline_days} 天 {target_hour} 点没有足够的基线数据", "no_baseline_data", {
                "baseline_days": baseline_days,
                "target_hour": target_hour,
                "baseline_count": 0
            })

        dl_baseline_vals = [r["download"]["speed_mbps"] for r in baseline_results if r.get("download", {}).get("success", False) and r["download"]["speed_mbps"] > 0]
        ul_baseline_vals = [r["upload"]["speed_mbps"] for r in baseline_results if r.get("upload", {}).get("success", False) and r["upload"]["speed_mbps"] > 0]
        lat_baseline_vals = [r["latency"]["avg_ms"] for r in baseline_results if r.get("latency", {}).get("success", False) and r["latency"]["avg_ms"] > 0]

        dl_baseline = compute_baseline(dl_baseline_vals)
        ul_baseline = compute_baseline(ul_baseline_vals)
        lat_baseline = compute_baseline(lat_baseline_vals)

        current_summary = compute_summary(current_results)

        dl_current = current_summary["download"]["avg_mbps"]
        ul_current = current_summary["upload"]["avg_mbps"]
        lat_current = current_summary["latency"]["avg_ms"]

        dl_anomaly = classify_anomaly(dl_current, dl_baseline, is_higher_bad=False)
        ul_anomaly = classify_anomaly(ul_current, ul_baseline, is_higher_bad=False)
        lat_anomaly = classify_anomaly(lat_current, lat_baseline, is_higher_bad=True)

        overall_level = "normal"
        levels = ["normal", "mild", "severe", "critical"]
        for a in [dl_anomaly, ul_anomaly, lat_anomaly]:
            if a["level"] != "unknown" and levels.index(a["level"]) > levels.index(overall_level):
                overall_level = a["level"]

        baseline_result = {
            "baseline_config": {
                "baseline_days": baseline_days,
                "target_hour": target_hour,
                "compare_hours": compare_hours
            },
            "baseline": {
                "sample_count": len(baseline_results),
                "download": dl_baseline,
                "upload": ul_baseline,
                "latency": lat_baseline
            },
            "current": {
                "sample_count": len(current_results),
                "download_avg_mbps": dl_current,
                "upload_avg_mbps": ul_current,
                "latency_avg_ms": lat_current
            },
            "anomaly": {
                "overall_level": overall_level,
                "download": dl_anomaly,
                "upload": ul_anomaly,
                "latency": lat_anomaly
            }
        }

        fmt = getattr(args, "fmt", "full")
        output = _format_output(baseline_result, fmt)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        output_error_json(f"基线分析失败: {e}", "baseline_error")


def cmd_analyze(args):
    try:
        results = read_jsonl(args.input)
        filtered = filter_by_time_range(results, args.hours)
        analysis = analyze_results(filtered)
        fmt = getattr(args, "fmt", "full")
        output = _format_output(analysis, fmt)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        output_error_json(f"分析失败: {e}", "analyze_error")


def resolve_servers(args) -> Tuple[List[Dict], Optional[str]]:
    servers = DEFAULT_SERVERS.copy()
    if args.servers_file:
        custom_servers, load_error = load_custom_servers(args.servers_file)
        if load_error:
            return [], load_error
        if custom_servers:
            servers = custom_servers
    return servers, None


def resolve_server_selection(args, servers) -> Tuple[Optional[Dict], Optional[List[Dict]], str, bool, Optional[str]]:
    selected_server = None
    selection_reason = None
    selection_method = "default"
    tag_matched = True
    error_msg = None

    if getattr(args, "download_url", None):
        size_param = None
        parsed = urlparse(args.download_url)
        query_params = parse_qs(parsed.query)
        if "size" in query_params:
            size_param = "size"
        elif "bytes" in query_params:
            size_param = "bytes"
        selected_server = {
            "id": "custom",
            "name": getattr(args, "server_name", "Custom"),
            "region": None,
            "city": None,
            "isp": None,
            "tags": ["自定义"],
            "weight": 10,
            "disabled": False,
            "download_url": args.download_url,
            "download_size_param": size_param,
            "default_download_size": getattr(args, "download_size", None) or 25,
            "upload_url": getattr(args, "upload_url", None),
            "latency_url": getattr(args, "latency_url", None)
        }
        selection_method = "manual_url"
    elif getattr(args, "auto_select", False):
        if not getattr(args, "json", False):
            print("正在自动选择最近的服务器...", file=sys.stderr)
        tags = getattr(args, "tags", None)
        selected_server, selection_reason, tag_matched = select_best_server(servers, tags=tags)
        if not tag_matched:
            error_msg = f"标签 {tags} 没有匹配到任何活跃服务器"
        elif selected_server is None:
            error_msg = "没有可用的活跃服务器"
        selection_method = "auto_select"
        if not getattr(args, "json", False) and selected_server:
            print(f"已选择服务器: {selected_server['name']} (延迟: {selection_reason[0]['latency_ms']:.2f} ms, 权重: {selected_server.get('weight', 10)})", file=sys.stderr)
    else:
        tags = getattr(args, "tags", None)
        active = get_active_servers(servers)
        if tags:
            filtered, tag_matched = filter_servers_by_tags(active, tags)
            if not tag_matched:
                error_msg = f"标签 {tags} 没有匹配到任何活跃服务器"
                selected_server = None
            else:
                selected_server = filtered[0]
        else:
            if active:
                selected_server = active[0]
            else:
                error_msg = "没有可用的活跃服务器"
        selection_method = "default"

    return selected_server, selection_reason, selection_method, tag_matched, error_msg


def cmd_test(args):
    try:
        servers, load_error = resolve_servers(args)
        if load_error:
            output_error_json(load_error, "config_error")

        selected_server, selection_reason, selection_method, tag_matched, selection_error = resolve_server_selection(args, servers)
        if selection_error or selected_server is None:
            output_error_json(selection_error or "无法选择测试服务器", "server_selection_error", {
                "tag_matched": tag_matched,
                "tags_requested": getattr(args, "tags", None)
            })

        state_file = getattr(args, "state_file", None)
        state = load_state(state_file) if state_file else None

        if not getattr(args, "json", False):
            print(f"测试服务器: {selected_server['name']}", file=sys.stderr)
            if selected_server.get("region"):
                print(f"地区: {selected_server.get('region')} - {selected_server.get('city', '')}", file=sys.stderr)
            if selected_server.get("isp"):
                print(f"运营商: {selected_server.get('isp')}", file=sys.stderr)
            if selected_server.get("tags"):
                print(f"标签: {', '.join(selected_server.get('tags', []))}", file=sys.stderr)
            if selected_server.get("weight"):
                print(f"权重: {selected_server.get('weight', 10)}", file=sys.stderr)
            print(f"下载地址: {build_download_url(selected_server, getattr(args, 'download_size', None))}", file=sys.stderr)
            if selected_server.get("upload_url") and not getattr(args, "skip_upload", False):
                print(f"上传地址: {selected_server.get('upload_url')}", file=sys.stderr)
            if state_file and state:
                print(f"状态文件: {state_file}", file=sys.stderr)
                print(f"历史测试: {state.get('total_tests', 0)} 次, 连续失败: {state.get('consecutive_failures', 0)} 次", file=sys.stderr)
            print("=" * 60, file=sys.stderr)

        alert_rules = {}
        if getattr(args, "alert_download_min", None) is not None:
            alert_rules["download_min_mbps"] = args.alert_download_min
        if getattr(args, "alert_latency_max", None) is not None:
            alert_rules["latency_max_ms"] = args.alert_latency_max
        if getattr(args, "alert_consecutive_fail", None) is not None:
            alert_rules["consecutive_fail"] = args.alert_consecutive_fail
        alert_rules["_recent_results"] = state.get("recent_results", []) if state else []

        while True:
            result = run_test(
                selected_server,
                upload_size_mb=getattr(args, "upload_size", 10),
                download_size_mb=getattr(args, "download_size", None),
                skip_upload=getattr(args, "skip_upload", False),
                selection_reason=selection_reason,
                selection_method=selection_method,
                tag_matched=tag_matched
            )

            if alert_rules:
                consecutive_fail_count = state.get("consecutive_failures", 0) if state else 0
                if not result["test_success"]:
                    consecutive_fail_count += 1
                else:
                    consecutive_fail_count = 0
                alert_rules["_consecutive_fail_count"] = consecutive_fail_count
                alert_result = check_alert_rules(result, alert_rules)
                result["alert"] = alert_result
                if alert_result["triggered"]:
                    if not getattr(args, "json", False):
                        for rule in alert_result["rules_triggered"]:
                            print(f"⚠ 告警: {rule['message']}", file=sys.stderr)

            if state is not None:
                state = update_state_with_result(state, result)
                if state_file:
                    save_state(state_file, state)
                result["state_snapshot"] = {
                    "total_tests": state.get("total_tests", 0),
                    "total_success": state.get("total_success", 0),
                    "total_failed": state.get("total_failed", 0),
                    "consecutive_failures": state.get("consecutive_failures", 0),
                    "last_success_time": state.get("last_success_time")
                }
            else:
                result["state_snapshot"] = None

            if args.output:
                append_to_jsonl(args.output, result)
                if not getattr(args, "json", False):
                    print(f"结果已追加到: {args.output}", file=sys.stderr)

            if getattr(args, "webhook", None):
                success = send_to_webhook(args.webhook, result)
                if not getattr(args, "json", False):
                    if success:
                        print("Webhook 推送成功", file=sys.stderr)
                    else:
                        print("Webhook 推送失败", file=sys.stderr)

            if getattr(args, "json", False):
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("=" * 60, file=sys.stderr)
                print(f"测试时间: {result['local_time']}", file=sys.stderr)
                print(f"测试状态: {'成功' if result['test_success'] else '部分失败'}", file=sys.stderr)
                if not tag_matched:
                    print(f"⚠ 标签未匹配: 请求的标签 {getattr(args, 'tags', None)} 没有匹配到服务器", file=sys.stderr)
                print(f"下载大小: {result['test_config']['download_size_mb']} MB", file=sys.stderr)
                download_status = f" (失败: {result['download'].get('error', '')})" if not result['download']['success'] else ""
                print(f"下载速度: {result['download']['speed_mbps']:.2f} Mbps{download_status}", file=sys.stderr)
                if not getattr(args, "skip_upload", False):
                    print(f"上传大小: {result['test_config']['upload_size_mb']} MB", file=sys.stderr)
                    upload_status = f" (失败: {result['upload'].get('error', '')})" if not result['upload']['success'] else ""
                    print(f"上传速度: {result['upload']['speed_mbps']:.2f} Mbps{upload_status}", file=sys.stderr)
                print(f"延迟: {result['latency']['avg_ms']:.2f} ms (min: {result['latency']['min_ms']:.2f}, max: {result['latency']['max_ms']:.2f}, 丢包: {result['latency']['packet_loss']}%)", file=sys.stderr)
                if not result['latency']['success']:
                    print(f"延迟测试错误: {', '.join(result['latency']['errors'])}", file=sys.stderr)
                print(f"网络质量: {result['quality_evaluation']['quality']}", file=sys.stderr)
                print(f"建议: {result['quality_evaluation']['suggestion']}", file=sys.stderr)
                if result['alert']['triggered']:
                    print(f"告警状态: 已触发 ({len(result['alert']['rules_triggered'])} 条规则)", file=sys.stderr)
                    for rule in result['alert']['rules_triggered']:
                        print(f"  → {rule['message']}", file=sys.stderr)
                if result.get("state_snapshot"):
                    ss = result["state_snapshot"]
                    print(f"累计状态: 共 {ss['total_tests']} 次, 成功 {ss['total_success']} 次, 连续失败 {ss['consecutive_failures']} 次", file=sys.stderr)

            if not getattr(args, "continuous", False):
                break

            print(f"\n等待 {getattr(args, 'interval', 600)} 秒后进行下一次测试... (Ctrl+C 停止)", file=sys.stderr)
            try:
                time.sleep(getattr(args, "interval", 600))
            except KeyboardInterrupt:
                print("\n测试已停止", file=sys.stderr)
                break
    except KeyboardInterrupt:
        print("\n测试已中断", file=sys.stderr)
    except Exception as e:
        output_error_json(f"测试执行失败: {e}", "execution_error")


def add_test_arguments(parser):
    parser.add_argument("--download-url", type=str, help="指定下载测试文件URL")
    parser.add_argument("--upload-url", type=str, help="指定上传测试URL")
    parser.add_argument("--latency-url", type=str, help="指定延迟测试URL")
    parser.add_argument("--server-name", type=str, default="Custom", help="指定服务器名称")
    parser.add_argument("--download-size", type=int, help="下载测试文件大小(MB)，默认使用服务器配置")
    parser.add_argument("--upload-size", type=int, default=10, help="上传测试文件大小(MB)，默认10MB")
    parser.add_argument("--skip-upload", action="store_true", help="跳过上传测试")
    parser.add_argument("--auto-select", action="store_true", help="自动选择最近的服务器")
    parser.add_argument("--servers-file", type=str, help="自定义服务器列表JSON文件路径")
    parser.add_argument("--tags", type=str, nargs="*", help="按标签筛选服务器，如: 电信 国内")
    parser.add_argument("--continuous", action="store_true", help="启用连续测试模式")
    parser.add_argument("--interval", type=int, default=600, help="连续测试间隔(秒)，默认600秒(10分钟)")
    parser.add_argument("--output", type=str, help="JSONL输出文件路径，用于保存连续测试结果")
    parser.add_argument("--webhook", type=str, help="测试结果Webhook推送地址")
    parser.add_argument("--json", action="store_true", help="仅输出JSON格式结果")
    parser.add_argument("--state-file", type=str, help="状态文件路径，用于记录累计测试状态，程序重启后可恢复")
    parser.add_argument("--alert-download-min", type=float, help="告警：下载速度低于此值(Mbps)触发")
    parser.add_argument("--alert-latency-max", type=float, help="告警：延迟高于此值(ms)触发")
    parser.add_argument("--alert-consecutive-fail", type=int, help="告警：连续失败达到此次数触发")


def _detect_json_mode() -> bool:
    return "--json" in sys.argv[1:]


def _detect_subcommand() -> Optional[str]:
    subcommands = {"test", "analyze", "compare", "baseline"}
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            return arg if arg in subcommands else None
    return None


def _format_output(data: Dict, fmt: str) -> Dict:
    if fmt == "full":
        return data
    if fmt == "summary":
        return _extract_summary(data)
    return data


def _extract_summary(data: Dict) -> Dict:
    if "summary" in data and "total_tests" in data:
        summary = data.get("summary", {})
        server_dist = data.get("server_distribution", {})
        worst_server = None
        worst_pct = 0
        for name, info in server_dist.items():
            if info.get("percentage", 0) > worst_pct:
                worst_pct = info["percentage"]
                worst_server = name
        return {
            "total_tests": data.get("total_tests", 0),
            "success_rate": summary.get("success_rate", 0.0),
            "download_avg_mbps": summary.get("download", {}).get("avg_mbps", 0.0),
            "download_min_mbps": summary.get("download", {}).get("min_mbps", 0.0),
            "upload_avg_mbps": summary.get("upload", {}).get("avg_mbps", 0.0),
            "latency_avg_ms": summary.get("latency", {}).get("avg_ms", 0.0),
            "latency_max_ms": summary.get("latency", {}).get("max_ms", 0.0),
            "alert_count": data.get("alert_count", 0) if "alert_count" in data else None,
            "worst_server": worst_server,
            "time_range": data.get("time_range")
        }
    if "changes" in data and "current_period" in data:
        alerts = data.get("alerts", [])
        return {
            "hours": data.get("comparison_config", {}).get("hours", 0),
            "current": {
                "download_avg_mbps": data.get("current_period", {}).get("download", {}).get("avg_mbps", 0.0),
                "upload_avg_mbps": data.get("current_period", {}).get("upload", {}).get("avg_mbps", 0.0),
                "latency_avg_ms": data.get("current_period", {}).get("latency", {}).get("avg_ms", 0.0),
                "success_rate": data.get("current_period", {}).get("success_rate", 0.0)
            },
            "changes": {
                "download_speed": data.get("changes", {}).get("download_speed", {}),
                "upload_speed": data.get("changes", {}).get("upload_speed", {}),
                "latency": data.get("changes", {}).get("latency", {}),
                "success_rate": data.get("changes", {}).get("success_rate", {})
            },
            "alert_count": len(alerts),
            "alerts": alerts
        }
    if "anomaly" in data and "baseline" in data:
        return {
            "baseline_days": data.get("baseline_config", {}).get("baseline_days", 0),
            "target_hour": data.get("baseline_config", {}).get("target_hour", 0),
            "baseline_sample_count": data.get("baseline", {}).get("sample_count", 0),
            "current_sample_count": data.get("current", {}).get("sample_count", 0),
            "overall_anomaly_level": data.get("anomaly", {}).get("overall_level", "unknown"),
            "download": {
                "baseline_mean": data.get("baseline", {}).get("download", {}).get("mean", 0.0),
                "current": data.get("current", {}).get("download_avg_mbps", 0.0),
                "anomaly_level": data.get("anomaly", {}).get("download", {}).get("level", "unknown"),
                "deviation_percent": data.get("anomaly", {}).get("download", {}).get("deviation_percent", 0.0)
            },
            "latency": {
                "baseline_mean": data.get("baseline", {}).get("latency", {}).get("mean", 0.0),
                "current": data.get("current", {}).get("latency_avg_ms", 0.0),
                "anomaly_level": data.get("anomaly", {}).get("latency", {}).get("level", "unknown"),
                "deviation_percent": data.get("anomaly", {}).get("latency", {}).get("deviation_percent", 0.0)
            }
        }
    return data


def main():
    json_mode = _detect_json_mode()
    subcmd = _detect_subcommand()

    parser = JsonErrorArgumentParser(description="网速测试工具 - 输出结构化JSON数据")
    parser.set_json_mode(json_mode, subcmd)
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    test_parser = subparsers.add_parser("test", help="执行网速测试")
    test_parser.set_json_mode(json_mode, "test")
    add_test_arguments(test_parser)

    analyze_parser = subparsers.add_parser("analyze", help="分析历史JSONL数据")
    analyze_parser.set_json_mode(json_mode, "analyze")
    analyze_parser.add_argument("--input", type=str, required=True, help="JSONL历史数据文件路径")
    analyze_parser.add_argument("--hours", type=int, default=0, help="统计最近N小时的数据，0表示全部数据")
    analyze_parser.add_argument("--format", dest="fmt", choices=["full", "summary"], default="full", help="输出格式: full(完整) 或 summary(精简)")

    compare_parser = subparsers.add_parser("compare", help="对比两个时段的网络质量变化")
    compare_parser.set_json_mode(json_mode, "compare")
    compare_parser.add_argument("--input", type=str, required=True, help="JSONL历史数据文件路径")
    compare_parser.add_argument("--hours", type=int, default=1, help="对比时段长度(小时)，默认1小时(即最近1h vs 前1h)")
    compare_parser.add_argument("--format", dest="fmt", choices=["full", "summary"], default="full", help="输出格式: full(完整) 或 summary(精简)")

    baseline_parser = subparsers.add_parser("baseline", help="基于历史基线检测异常")
    baseline_parser.set_json_mode(json_mode, "baseline")
    baseline_parser.add_argument("--input", type=str, required=True, help="JSONL历史数据文件路径")
    baseline_parser.add_argument("--baseline-days", type=int, default=7, help="基线数据天数，默认7天")
    baseline_parser.add_argument("--hour", type=int, help="目标小时(0-23)，默认当前小时")
    baseline_parser.add_argument("--hours", type=int, default=1, help="待检测时段长度(小时)，默认1小时")
    baseline_parser.add_argument("--format", dest="fmt", choices=["full", "summary"], default="full", help="输出格式: full(完整) 或 summary(精简)")

    default_parser = JsonErrorArgumentParser(description="网速测试工具 - 输出结构化JSON数据", add_help=False)
    default_parser.set_json_mode(json_mode, "test")
    default_parser.add_argument("command", nargs="?", default=None)
    add_test_arguments(default_parser)

    if subcmd:
        args = parser.parse_args()
        if args.command == "analyze":
            cmd_analyze(args)
        elif args.command == "compare":
            cmd_compare(args)
        elif args.command == "baseline":
            cmd_baseline(args)
        else:
            cmd_test(args)
    else:
        default_args = default_parser.parse_args(sys.argv[1:])
        default_args.command = "test"
        cmd_test(default_args)


def cmd_compare(args):
    try:
        results = read_jsonl(args.input)
        if not results:
            output_error_json("JSONL文件为空或不存在", "no_data")

        current_results = filter_by_time_window(results, args.hours, 0)
        previous_results = filter_by_time_window(results, args.hours * 2, args.hours)

        current_summary = compute_summary(current_results)
        previous_summary = compute_summary(previous_results)

        comparison = {
            "comparison_config": {
                "current_period": f"最近 {args.hours} 小时",
                "previous_period": f"前 {args.hours} 小时",
                "hours": args.hours
            },
            "current_period": current_summary,
            "previous_period": previous_summary,
            "changes": {
                "download_speed": calc_change(
                    current_summary["download"]["avg_mbps"],
                    previous_summary["download"]["avg_mbps"]
                ),
                "upload_speed": calc_change(
                    current_summary["upload"]["avg_mbps"],
                    previous_summary["upload"]["avg_mbps"]
                ),
                "latency": calc_change(
                    current_summary["latency"]["avg_ms"],
                    previous_summary["latency"]["avg_ms"]
                ),
                "success_rate": calc_change(
                    current_summary["success_rate"],
                    previous_summary["success_rate"]
                )
            },
            "quality_change": compare_quality_distributions(
                current_summary["quality_distribution"],
                previous_summary["quality_distribution"]
            )
        }

        alerts = []
        dl_change = comparison["changes"]["download_speed"]
        lat_change = comparison["changes"]["latency"]
        if dl_change["direction"] == "decreased" and dl_change["percentage"] is not None and dl_change["percentage"] < -30:
            alerts.append(f"下载速度下降 {abs(dl_change['percentage'])}%")
        if lat_change["direction"] == "increased" and lat_change["percentage"] is not None and lat_change["percentage"] > 50:
            alerts.append(f"延迟上升 {lat_change['percentage']}%")
        if current_summary["success_rate"] < 80:
            alerts.append(f"当前时段成功率仅 {current_summary['success_rate']}%")

        comparison["alerts"] = alerts

        fmt = getattr(args, "fmt", "full")
        output = _format_output(comparison, fmt)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as e:
        output_error_json(f"对比分析失败: {e}", "compare_error")


if __name__ == "__main__":
    main()
