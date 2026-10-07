#!/usr/bin/env python3
"""
vision_bridge.py : 비전 검사 엔진 ↔ ai_factory PdM 시스템(vision_link) 연결

  위치 : ~/ai_factory/vision/vision_bridge.py  (vision_link.py 와 같은 폴더)
  엔진 : yolo_engine/ (C++). 다른 엔진(예: PatchCore)도 같은 @@EVENT 형식만 출력하면 연결 가능

  흐름
    yolo_mfg (부품 감지 트리거 + AI 판정) ──'@@EVENT {json}'──▶ 이 브리지
      ──▶ 클래스 → status 코드 변환 (예: Black → NG_VISION_BLACK)
      ──▶ vision_link.VisionLink.record()  →  SQLite tb_vision_inspection + (NG면) Rust 허브 → 4호기

  안전 규칙
    - 기본은 '그림자(SHADOW) 모드' : vision_link 를 호출하지 않고 화면/CSV 에만 남김
    - --live 를 붙여야 실제로 vision_link.record() 를 호출 (NG 면 실제로 4호기 정지·퇴출!)
    - 4호기 시리얼 포트에는 절대 직접 접근하지 않음 (Rust 허브 단독 소유, vision/README 규칙)

  사용법 (보통은 run_vision_pdm.sh 로 실행)
    cd ~/ai_factory/vision
    python3 vision_bridge.py            # 그림자 모드
    python3 vision_bridge.py --live     # 실제 연동
"""
import argparse
import ctypes
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent                      # ~/ai_factory/vision
DATA = ROOT.parent / "data" / "vision"                      # ~/ai_factory/data/vision
EVENT_PREFIX = "@@EVENT "


_NONFINITE = re.compile(r'(?<=[:\[,])\s*-?(nan|inf|infinity)\b', re.IGNORECASE)


def parse_event(payload):
    """C++ 가 nan/inf 를 그대로 출력해도 JSON 해석이 깨지지 않도록 null 로 바꿔서 해석"""
    return json.loads(_NONFINITE.sub("null", payload))


def num(v, default=0.0):
    """None/문자/nan 이 와도 안전하게 float 로 (판정 경로에서 예외로 브리지가 죽지 않게)"""
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else default
    except (TypeError, ValueError):
        return default


def is_camera_source(cfg_path):
    """설정의 source 가 카메라(숫자 또는 /dev/video*)인지. 카메라는 '입력 끝' 이 곧 장애"""
    try:
        for line in open(cfg_path, encoding="utf-8"):
            m = re.match(r'\s*source\s*:\s*"?([^"#\s]+)', line)
            if m:
                src = m.group(1)
                return src.isdigit() or src.startswith("/dev/video")
    except OSError:
        pass
    return False


def _die_with_parent():
    """브리지(부모)가 어떤 이유로 죽어도 엔진(자식)이 카메라를 잡은 채 남지 않게 (Linux prctl)"""
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, int(signal.SIGTERM), 0, 0, 0)   # PR_SET_PDEATHSIG
    except Exception:
        pass


def load_map(path):
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    m.setdefault("status_map", {})
    m.setdefault("ok_classes", ["good"])
    m.setdefault("uncertain_status", "NG_VISION_UNCERTAIN")
    m.setdefault("ignore_classes", ["empty"])        # 빈 화면 등: 판정 대상 아님 (라인 정지·DB 기록 안 함)
    return m


def to_status(ev, m):
    """C++ 이벤트 → (status, defect_class, confidence) : vision_link 규칙(OK / NG_...)에 맞춤"""
    if ev.get("verdict") == "OK":
        conf = num(ev.get("p_ok"), 1.0) if ev.get("task") == "classify" else 1.0
        return "OK", None, round(conf, 4)
    # verdict 가 OK 가 아니면(누락·이상값 포함) 전부 NG 로 취급 → 판정이 애매할 때 양품으로 흘려보내지 않음
    cls = str(ev.get("defect_class") or ev.get("top1") or "unknown")
    if cls in m["ignore_classes"]:                           # 빈 화면 → 판정 제외
        return "EMPTY", cls.lower(), round(num(ev.get("defect_conf")), 4)
    if cls in m["status_map"]:                               # 정해진 불량 코드
        return m["status_map"][cls], cls.lower(), round(num(ev.get("defect_conf")), 4)
    if cls in m["ok_classes"]:                               # good 이지만 확신 부족 → 불확실 NG
        return m["uncertain_status"], "uncertain", round(1.0 - num(ev.get("p_ok")), 4)
    code = "NG_VISION_" + (re.sub(r"[^A-Z0-9]+", "_", cls.upper()).strip("_") or "UNKNOWN")   # 표에 없는 클래스
    return code, cls.lower(), round(num(ev.get("defect_conf")), 4)


class _Skip(Exception):
    """판정 제외(빈 화면) 이벤트: 기록 파일에만 남김"""


class SeqCounter:
    """part_seq 를 재시작해도 이어지도록 파일에 저장"""
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.value = int(self.path.read_text().strip())
        except Exception:
            self.value = 0

    def next(self):
        self.value += 1
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(str(self.value))
        os.replace(tmp, self.path)
        return self.value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config/pdm_bolt.yaml"), help="엔진 설정 (part_trigger + event_output 필수)")
    ap.add_argument("--map", default=str(ROOT / "status_map.json"), help="클래스→status 코드 표")
    ap.add_argument("--exe", default=str(ROOT / "yolo_engine/build/release/yolo_mfg"), help="검사 엔진 실행 파일")
    ap.add_argument("--live", action="store_true", help="실제 vision_link 호출 (NG 면 4호기 정지·퇴출)")
    ap.add_argument("--vision-path", default=str(ROOT), help="vision_link.py 가 있는 폴더 (기본: 이 파일과 같은 폴더)")
    args = ap.parse_args()

    m = load_map(args.map)
    log_dir = DATA / "bridge"
    log_dir.mkdir(parents=True, exist_ok=True)
    mode = "LIVE" if args.live else "SHADOW"
    seq = SeqCounter(log_dir / f".part_seq_{mode.lower()}")   # 그림자 모드가 실제 번호를 소모하지 않도록 분리

    vl = None
    if args.live:
        vpath = os.path.expanduser(args.vision_path)
        sys.path.insert(0, vpath)
        from vision_link import VisionLink                   # noqa: E402  (README 의 사용법 그대로)
        vl = VisionLink(model_version=m["model_version"])
        print("=" * 70)
        print(f" ⚠ LIVE 모드 : NG 판정 시 vision_link → Rust 허브 → 4호기 정지·퇴출이 실제로 동작합니다")
        print(f"   vision_link 경로 : {vpath}   모델 버전 : {m['model_version']}")
        print("=" * 70)
    else:
        print(f"[브리지] SHADOW 모드 : vision_link 를 호출하지 않습니다 (실제 연동은 --live)")

    shadow_csv = log_dir / f"bridge_{mode.lower()}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(shadow_csv, "w", newline="", encoding="utf-8-sig") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(["bridge_time", "mode", "part_seq", "status", "defect_class", "confidence",
                    "bbox", "inference_ms", "image_path", "cpp_seq", "cpp_ts", "result"])
        print(f"[브리지] 기록 파일 : {shadow_csv}")

        stop = {"flag": False}
        cur = {"proc": None}

        def on_signal(*_):                                    # Ctrl+C, VS Code 중지, kill 모두 같은 처리
            stop["flag"] = True
            p = cur["proc"]
            if p is not None and p.poll() is None:
                p.terminate()                                 # 엔진 출력이 없어 대기 중이어도 즉시 종료

        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)
        camera = is_camera_source(args.config)
        restarts = 0
        while not stop["flag"]:
            cmd = [args.exe, args.config]
            print(f"[브리지] 비전 프로그램 시작 : {' '.join(cmd)}")
            started = time.monotonic()
            input_ended = False
            try:
                proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, bufsize=1, encoding="utf-8", errors="replace",
                                        preexec_fn=_die_with_parent)
            except OSError as e:
                print(f"[브리지] 🛑 비전 프로그램을 실행할 수 없습니다: {e}")
                proc = None
            cur["proc"] = proc
            for line in (proc.stdout if proc else []):
                line = line.rstrip("\n")
                if not line.startswith(EVENT_PREFIX):
                    print(f"  [vision] {line}")
                    if "[종료] 입력 끝" in line:
                        input_ended = True
                    continue
                part, status, dclass, conf, result, ev = None, "", None, None, "", {}
                try:
                    ev = parse_event(line[len(EVENT_PREFIX):])
                    status, dclass, conf = to_status(ev, m)
                    if status == "EMPTY":                     # 부품 번호를 쓰지 않고, 허브·DB 로도 보내지 않음
                        result = "IGNORED"
                        print(f"⏭  [{mode}] 빈 화면 판정 (class={dclass}, conf={conf}) → 판정 제외")
                        raise _Skip()
                    part = seq.next()
                    kw = dict(status=status, defect_class=dclass, confidence=conf, bbox=ev.get("bbox"),
                              inference_ms=num(ev.get("inference_ms"), None), part_seq=part,
                              image_path=ev.get("image") or None)
                    result = "SHADOW"
                    if vl is not None:
                        try:
                            r = vl.record(**kw)
                            result = str(r) if r is not None else "RECORDED"
                        except Exception as e:               # 기록 실패로 비전 검사가 멈추지 않도록
                            result = f"ERROR: {e}"
                            print(f"[브리지] 🛑 vision_link 처리 실패 (part {part}, {status}): {e}")
                    mark = "✅" if status == "OK" else "🚨"
                    print(f"{mark} [{mode}] part {part}: {status}  conf={conf}  class={dclass}  → {result}")
                except _Skip:
                    pass
                except Exception as e:                        # 이벤트 1건 문제로 브리지 전체가 죽지 않게
                    result = f"EVENT_ERROR: {e}"
                    print(f"[브리지] 🛑 이벤트 처리 실패 (이 부품은 판정이 전달되지 않음): {e}\n           원문: {line[:200]}")
                try:
                    w.writerow([datetime.now().isoformat(timespec="milliseconds"), mode, part, status, dclass,
                                conf, json.dumps(ev.get("bbox")), ev.get("inference_ms"), ev.get("image"),
                                ev.get("seq"), ev.get("ts"), result])
                    fcsv.flush()
                except Exception as e:
                    print(f"[브리지] ⚠ CSV 기록 실패: {e}")
                if stop["flag"]:
                    break
            if stop["flag"]:
                if proc and proc.poll() is None:
                    proc.terminate()
                break
            rc = proc.wait() if proc else -1
            if time.monotonic() - started > 60:               # 1분 이상 정상 동작했으면 재시작 대기 초기화
                restarts = 0
            if rc == 0 and not (camera and input_ended):      # 작업자 종료(ESC/q) 또는 사진·영상 입력 끝
                print("[브리지] 비전 프로그램 정상 종료")
                break
            reason = "카메라 영상 끊김" if rc == 0 else f"비정상 종료(코드 {rc})"
            restarts += 1                                     # 카메라 끊김·비정상 종료 → 자동 재시작
            wait = min(30, 3 * restarts)
            print(f"[브리지] 🛑 비전 프로그램 {reason} → {wait}초 후 재시작 ({restarts}회째)")
            for _ in range(wait * 10):
                if stop["flag"]:
                    break
                time.sleep(0.1)
    print("[브리지] 종료")


if __name__ == "__main__":
    main()
