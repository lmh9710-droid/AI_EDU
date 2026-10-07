//! # Smart Factory Interlock Hub (4호기 컨베이어 안전 인터록)
//!
//! * 4호기 컨베이어 시리얼 포트를 **단독 소유**한다. 다른 프로세스는 이 허브를 통해서만 명령한다.
//! * 입력: Unix 도메인 소켓 (`SF_HUB_SOCK`, 기본 `/tmp/sf_interlock.sock`), JSON 한 줄 요청 / 한 줄 응답
//!   - `DEFECT`    실측 불량 (C++ 미들웨어)    → 라인 정지 후 퇴출 `CMD_DEFECT`
//!   - `PRED_STOP` AI 불량 예측 (Python 엔진)  → 라인 정지 `CMD_STOP`
//!   - `WARN`      위험 경고                    → 경고등 `CMD_WARN` (라인 계속 가동)
//!   - `RESET`     작업자 재가동 (src=OPERATOR 만 허용) → `CMD_RESET`
//!   - `HEARTBEAT` 생존 신호, `STATUS` 상태 조회
//! * 컨베이어 명령은 ID 를 붙여 보내고 ACK 를 300ms 내 받지 못하면 최대 3회 재전송한다.
//! * 워치독: 미들웨어 하트비트가 5초 끊기면 라인 정지(fail-safe), AI/컨베이어 하트비트 단절은 경보.
//! * 모든 실행 이력은 SQLite `tb_interlock_event` 에 기록한다.

use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, ErrorKind, Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const ACK_TIMEOUT: Duration = Duration::from_millis(300);
const MAX_SEND_ATTEMPTS: u32 = 3;
const MIDDLEWARE_WATCHDOG: Duration = Duration::from_secs(5);
const AI_WATCHDOG: Duration = Duration::from_secs(10);
const CONVEYOR_WATCHDOG: Duration = Duration::from_secs(3);

// ------------------------------------------------------------------ 공통 유틸

/// KST(UTC+9) 밀리초 타임스탬프. 외부 크레이트 없이 계산 (C++/Python 과 동일 형식)
fn kst_now() -> String {
    let d = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default();
    let ms = d.as_millis() as i64 + 9 * 3600 * 1000;
    let (secs, milli) = (ms.div_euclid(1000), ms.rem_euclid(1000));
    let (days, sod) = (secs.div_euclid(86400), secs.rem_euclid(86400));
    // civil_from_days (Howard Hinnant)
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + if month <= 2 { 1 } else { 0 };
    format!("{:04}-{:02}-{:02} {:02}:{:02}:{:02}.{:03}",
            year, month, day, sod / 3600, (sod % 3600) / 60, sod % 60, milli)
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).ok().filter(|v| !v.is_empty()).unwrap_or_else(|| default.to_string())
}

fn checksum_ok(line: &str) -> Option<&str> {
    let star = line.rfind('*')?;
    let (body, cs) = (&line[..star], &line[star + 1..]);
    let x = body.bytes().fold(0u8, |a, b| a ^ b);
    (u8::from_str_radix(cs.trim(), 16).ok()? == x).then_some(body)
}

// ------------------------------------------------------------------ 명령/상태 타입

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ConveyorCmd { Stop, Defect, Warn, Reset, Ping }

impl ConveyorCmd {
    fn wire(self) -> &'static str {
        match self {
            ConveyorCmd::Stop => "CMD_STOP",
            ConveyorCmd::Defect => "CMD_DEFECT",
            ConveyorCmd::Warn => "CMD_WARN",
            ConveyorCmd::Reset => "CMD_RESET",
            ConveyorCmd::Ping => "CMD_PING",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum CmdOutcome { Acked(String), Nak(String), NoAck, NoPort }

impl CmdOutcome {
    fn label(&self) -> String {
        match self {
            CmdOutcome::Acked(s) => format!("ACKED({s})"),
            CmdOutcome::Nak(r) => format!("NAK({r})"),
            CmdOutcome::NoAck => "NO_ACK".into(),
            CmdOutcome::NoPort => "NO_PORT".into(),
        }
    }
}

struct CmdRequest { cmd: ConveyorCmd, reply: Sender<(CmdOutcome, u32, f64)> }

#[derive(Default)]
struct HubState {
    line_state: String,            // RUNNING | STOPPING | EJECTING | STOPPED | UNKNOWN
    warn_lamp: bool,
    eject_count: u64,
    conveyor_seen: Option<Instant>,
    mw_heartbeat: Option<Instant>,
    ai_heartbeat: Option<Instant>,
    mw_lost_reported: bool,
    ai_lost_reported: bool,
    conveyor_lost_reported: bool,
    suppressed: u64,
}

#[derive(Deserialize, Debug, Default)]
struct Event {
    #[serde(default)] src: String,
    #[serde(default)] kind: String,
    #[serde(default)] code: String,
    #[serde(default)] value: f64,
    #[serde(default)] detail: String,
}

#[derive(Serialize)]
struct Reply {
    ok: bool,
    result: String,
    line_state: String,
    warn_lamp: bool,
    #[serde(skip_serializing_if = "Option::is_none")] cmd_id: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")] eject_count: Option<u64>,
}

struct LogRow {
    ts: String, source: String, kind: String, code: String, value: f64, detail: String,
    command: Option<String>, cmd_id: Option<u32>, result: String, latency_ms: Option<f64>,
}

// ------------------------------------------------------------------ DB 로거 (전용 스레드)

fn spawn_db_logger(db_path: String) -> Sender<LogRow> {
    let (tx, rx) = mpsc::channel::<LogRow>();
    thread::spawn(move || {
        let conn = loop {
            match rusqlite::Connection::open(&db_path) {
                Ok(c) => break c,
                Err(e) => { eprintln!("❌ [HUB DB] 열기 실패 {db_path}: {e}, 2초 후 재시도"); thread::sleep(Duration::from_secs(2)); }
            }
        };
        let _ = conn.busy_timeout(Duration::from_secs(5));
        let _ = conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             CREATE TABLE IF NOT EXISTS tb_interlock_event (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
               source TEXT, kind TEXT, code TEXT, value REAL, detail TEXT, command TEXT, cmd_id INTEGER, result TEXT, latency_ms REAL);");
        for r in rx {
            if let Err(e) = conn.execute(
                "INSERT INTO tb_interlock_event (timestamp, source, kind, code, value, detail, command, cmd_id, result, latency_ms)
                 VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",
                rusqlite::params![r.ts, r.source, r.kind, r.code, r.value, r.detail, r.command, r.cmd_id, r.result, r.latency_ms],
            ) { eprintln!("❌ [HUB DB] 기록 실패: {e}"); }
        }
    });
    tx
}

// ------------------------------------------------------------------ 컨베이어 I/O (포트 단독 소유 스레드)

struct Pending { id: u32, cmd: ConveyorCmd, attempts: u32, deadline: Instant, started: Instant, reply: Sender<(CmdOutcome, u32, f64)> }

fn spawn_conveyor_io(port_path: String, state: Arc<Mutex<HubState>>, running: Arc<AtomicBool>) -> Sender<CmdRequest> {
    let (tx, rx) = mpsc::channel::<CmdRequest>();
    thread::spawn(move || conveyor_io_loop(port_path, rx, state, running));
    tx
}

fn conveyor_io_loop(port_path: String, rx: Receiver<CmdRequest>, state: Arc<Mutex<HubState>>, running: Arc<AtomicBool>) {
    let mut port: Option<Box<dyn serialport::SerialPort>> = None;
    let mut next_open = Instant::now();
    let mut next_id: u32 = 1;
    let mut pending: Option<Pending> = None;
    let mut line = String::new();
    let mut buf = [0u8; 512];

    while running.load(Ordering::SeqCst) {
        if port.is_none() && Instant::now() >= next_open {
            match serialport::new(&port_path, 115_200).timeout(Duration::from_millis(20)).open() {
                Ok(mut p) => {
                    // 연결 직후 보드 수신 버퍼에 남은 잡음 바이트를 줄바꿈으로 끊어 첫 명령이 오염되지 않게 함
                    let _ = p.write_all(b"\n");
                    println!("🔒 [CONVEYOR LINK] 연결됨 -> {port_path}");
                    port = Some(p); line.clear();
                }
                Err(e) => { eprintln!("❌ [CONVEYOR LINK] 포트 열기 실패 {port_path}: {e} (1초 후 재시도)"); next_open = Instant::now() + Duration::from_secs(1); }
            }
        }

        // 대기 중인 명령이 없으면 새 명령을 꺼내 전송
        if pending.is_none() {
            let wait = if port.is_some() { Duration::from_millis(0) } else { Duration::from_millis(50) };
            if let Ok(req) = rx.recv_timeout(wait) {
                match port.as_mut() {
                    None => { let _ = req.reply.send((CmdOutcome::NoPort, 0, 0.0)); }
                    Some(p) => {
                        let id = next_id; next_id = next_id.wrapping_add(1).max(1);
                        let _ = p.write_all(format!("{},{}\n", req.cmd.wire(), id).as_bytes());
                        let now = Instant::now();
                        pending = Some(Pending { id, cmd: req.cmd, attempts: 1, deadline: now + ACK_TIMEOUT, started: now, reply: req.reply });
                    }
                }
            }
        }

        // 수신 처리
        if let Some(p) = port.as_mut() {
            match p.read(&mut buf) {
                Ok(n) => {
                    for &b in &buf[..n] {
                        if b == b'\n' || b == b'\r' {
                            if !line.is_empty() { handle_conveyor_line(&line, &state, &mut pending); line.clear(); }
                        } else if line.len() < 200 { line.push(b as char); } else { line.clear(); }
                    }
                }
                Err(e) if e.kind() == ErrorKind::TimedOut || e.kind() == ErrorKind::WouldBlock => {}
                Err(e) => {
                    eprintln!("❌ [CONVEYOR LINK] 읽기 오류: {e} → 재연결");
                    port = None; next_open = Instant::now() + Duration::from_millis(500);
                    if let Some(pd) = pending.take() { let _ = pd.reply.send((CmdOutcome::NoPort, pd.id, 0.0)); }
                }
            }
        }

        // ACK 타임아웃 → 같은 ID 로 재전송 (컨베이어는 같은 ID 를 중복 실행하지 않음)
        if let Some(pd) = pending.as_mut() {
            if Instant::now() >= pd.deadline {
                if pd.attempts < MAX_SEND_ATTEMPTS {
                    if let Some(p) = port.as_mut() {
                        let _ = p.write_all(format!("{},{}\n", pd.cmd.wire(), pd.id).as_bytes());
                    }
                    pd.attempts += 1; pd.deadline = Instant::now() + ACK_TIMEOUT;
                    eprintln!("⚠️ [CONVEYOR LINK] {} #{} ACK 없음 → 재전송 {}/{}", pd.cmd.wire(), pd.id, pd.attempts, MAX_SEND_ATTEMPTS);
                } else {
                    let pd = pending.take().unwrap();
                    let _ = pd.reply.send((CmdOutcome::NoAck, pd.id, pd.started.elapsed().as_secs_f64() * 1000.0));
                }
            }
        }
    }
}

fn handle_conveyor_line(line: &str, state: &Arc<Mutex<HubState>>, pending: &mut Option<Pending>) {
    if line.starts_with('#') { println!("📟 [4호기] {line}"); return; }
    let parts: Vec<&str> = line.split(',').collect();
    match parts.first().copied() {
        Some("ACK") | Some("NAK") if parts.len() >= 3 => {
            let id: u32 = parts[1].parse().unwrap_or(0);
            if let Some(pd) = pending.as_ref() {
                if pd.id == id {
                    let latency = pd.started.elapsed().as_secs_f64() * 1000.0;
                    let outcome = if parts[0] == "ACK" {
                        let st = parts.get(3).copied().unwrap_or("UNKNOWN").to_string();
                        state.lock().unwrap().line_state = st.clone();
                        CmdOutcome::Acked(st)
                    } else { CmdOutcome::Nak(parts[2].to_string()) };
                    let pd = pending.take().unwrap();
                    let _ = pd.reply.send((outcome, pd.id, latency));
                }
            }
        }
        Some(_) if line.starts_with("[CONVEYOR],") => {
            if let Some(body) = checksum_ok(line) {
                let f: Vec<&str> = body.split(',').collect();
                if f.len() >= 5 {
                    let mut s = state.lock().unwrap();
                    s.line_state = f[2].to_string();
                    s.warn_lamp = f[3] == "1";
                    s.eject_count = f[4].parse().unwrap_or(s.eject_count);
                    s.conveyor_seen = Some(Instant::now());
                    if s.conveyor_lost_reported { println!("✅ [CONVEYOR LINK] 4호기 상태 보고 복구"); s.conveyor_lost_reported = false; }
                }
            }
        }
        _ => {}
    }
}

// ------------------------------------------------------------------ 정책

struct Hub {
    state: Arc<Mutex<HubState>>,
    conveyor: Mutex<Sender<CmdRequest>>,
    decide: Mutex<()>,              // 판정-실행을 직렬화 (동시 불량 2건 → 퇴출 1회)
    log: Mutex<Sender<LogRow>>,
}

impl Hub {
    fn command(&self, cmd: ConveyorCmd) -> (CmdOutcome, u32, f64) {
        let (rtx, rrx) = mpsc::channel();
        if self.conveyor.lock().unwrap().send(CmdRequest { cmd, reply: rtx }).is_err() {
            return (CmdOutcome::NoPort, 0, 0.0);
        }
        rrx.recv_timeout(Duration::from_secs(3)).unwrap_or((CmdOutcome::NoAck, 0, 0.0))
    }

    fn log(&self, ev: &Event, command: Option<ConveyorCmd>, cmd_id: Option<u32>, result: &str, latency: Option<f64>) {
        let _ = self.log.lock().unwrap().send(LogRow {
            ts: kst_now(), source: ev.src.clone(), kind: ev.kind.clone(), code: ev.code.clone(), value: ev.value,
            detail: ev.detail.clone(), command: command.map(|c| c.wire().to_string()), cmd_id, result: result.to_string(), latency_ms: latency,
        });
    }

    fn snapshot(&self) -> (String, bool, u64) {
        let s = self.state.lock().unwrap();
        (if s.line_state.is_empty() { "UNKNOWN".into() } else { s.line_state.clone() }, s.warn_lamp, s.eject_count)
    }

    fn reply(&self, ok: bool, result: &str, cmd_id: Option<u32>) -> Reply {
        let (line_state, warn_lamp, eject) = self.snapshot();
        Reply { ok, result: result.to_string(), line_state, warn_lamp, cmd_id, eject_count: Some(eject) }
    }

    fn execute(&self, ev: &Event, cmd: ConveyorCmd, icon: &str) -> Reply {
        let (outcome, id, latency) = self.command(cmd);
        let label = outcome.label();
        let ok = matches!(outcome, CmdOutcome::Acked(_));
        if ok {
            println!("{icon} [{}] {} {} = {} → {} #{} {} ({:.0}ms)", kst_now(), ev.src, ev.code, ev.value, cmd.wire(), id, label, latency);
            let mut s = self.state.lock().unwrap();
            match cmd {
                ConveyorCmd::Warn => s.warn_lamp = true,
                ConveyorCmd::Reset => s.warn_lamp = false,
                _ => {}
            }
        } else {
            eprintln!("🛑 [{}] {} {} → {} 실패: {}  ※ 4호기 수동 확인 필요", kst_now(), ev.src, ev.code, cmd.wire(), label);
        }
        self.log(ev, Some(cmd), Some(id), &label, Some(latency));
        self.reply(ok, &label, Some(id))
    }

    fn handle(&self, ev: Event) -> Reply {
        match ev.kind.as_str() {
            "HEARTBEAT" => {
                let mut s = self.state.lock().unwrap();
                let now = Some(Instant::now());
                match ev.src.as_str() {
                    "MIDDLEWARE" => { if s.mw_lost_reported { println!("✅ 미들웨어 하트비트 복구"); } s.mw_heartbeat = now; s.mw_lost_reported = false; }
                    src if src.starts_with("AI") => { if s.ai_lost_reported { println!("✅ AI 엔진 하트비트 복구"); } s.ai_heartbeat = now; s.ai_lost_reported = false; }
                    _ => {}
                }
                drop(s);
                self.reply(true, "ALIVE", None)
            }
            "STATUS" => self.reply(true, "STATUS", None),
            "DEFECT" | "PRED_STOP" | "WARN" | "RESET" => {
                let _g = self.decide.lock().unwrap();
                let (line_state, warn_lamp, _) = self.snapshot();
                let running = line_state == "RUNNING" || line_state == "UNKNOWN";
                match ev.kind.as_str() {
                    "DEFECT" if running => self.execute(&ev, ConveyorCmd::Defect, "🚨"),
                    "PRED_STOP" if running => self.execute(&ev, ConveyorCmd::Stop, "🔮"),
                    "WARN" if !warn_lamp => self.execute(&ev, ConveyorCmd::Warn, "⚠️"),
                    "RESET" if ev.src == "OPERATOR" => self.execute(&ev, ConveyorCmd::Reset, "▶️"),
                    "RESET" => { self.log(&ev, None, None, "REJECTED_NOT_OPERATOR", None); self.reply(false, "REJECTED_NOT_OPERATOR", None) }
                    _ => {   // 이미 정지/경고 중: 중복 실행하지 않음 (집계만)
                        self.state.lock().unwrap().suppressed += 1;
                        self.reply(true, &format!("SUPPRESSED_{line_state}"), None)
                    }
                }
            }
            other => self.reply(false, &format!("UNKNOWN_KIND_{other}"), None),
        }
    }
}

fn watchdog_loop(hub: Arc<Hub>, running: Arc<AtomicBool>) {
    let mut last_summary = Instant::now();
    while running.load(Ordering::SeqCst) {
        thread::sleep(Duration::from_millis(500));
        let (mw_lost, ai_lost, conv_lost) = {
            let mut s = hub.state.lock().unwrap();
            let mw = matches!(s.mw_heartbeat, Some(t) if t.elapsed() > MIDDLEWARE_WATCHDOG) && !s.mw_lost_reported;
            let ai = matches!(s.ai_heartbeat, Some(t) if t.elapsed() > AI_WATCHDOG) && !s.ai_lost_reported;
            let cv = matches!(s.conveyor_seen, Some(t) if t.elapsed() > CONVEYOR_WATCHDOG) && !s.conveyor_lost_reported;
            if mw { s.mw_lost_reported = true; }
            if ai { s.ai_lost_reported = true; }
            if cv { s.conveyor_lost_reported = true; }
            if last_summary.elapsed() > Duration::from_secs(10) && s.suppressed > 0 {
                println!("ℹ️ [HUB] 최근 10초 정지 상태 중 중복 요청 {}건 무시 (라인 {})", s.suppressed, s.line_state);
                s.suppressed = 0;
            }
            if last_summary.elapsed() > Duration::from_secs(10) { last_summary = Instant::now(); }
            (mw, ai, cv)
        };
        if mw_lost {
            let ev = Event { src: "HUB_WATCHDOG".into(), kind: "PRED_STOP".into(), code: "WATCHDOG_MIDDLEWARE_LOST".into(),
                             detail: "middleware heartbeat lost > 5s (fail-safe line stop)".into(), ..Default::default() };
            eprintln!("🛑 [WATCHDOG] 미들웨어 하트비트 5초 단절 → 안전을 위해 라인 정지");
            hub.handle(ev);
        }
        if ai_lost {
            eprintln!("⚠️ [WATCHDOG] AI 엔진 하트비트 10초 단절 (예측 보호 기능 중단, 실측 판정은 유지)");
            hub.log(&Event { src: "HUB_WATCHDOG".into(), kind: "ALERT".into(), code: "WATCHDOG_AI_LOST".into(), ..Default::default() }, None, None, "ALERT", None);
        }
        if conv_lost {
            eprintln!("🛑 [WATCHDOG] 4호기 컨베이어 상태 보고 3초 단절! 현장 확인 필요");
            hub.log(&Event { src: "HUB_WATCHDOG".into(), kind: "ALERT".into(), code: "WATCHDOG_CONVEYOR_LOST".into(), ..Default::default() }, None, None, "ALERT", None);
        }
    }
}

fn serve_client(stream: UnixStream, hub: Arc<Hub>) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(30)));
    let mut writer = match stream.try_clone() { Ok(w) => w, Err(_) => return };
    let reader = BufReader::new(stream);
    for line in reader.lines() {
        let line = match line { Ok(l) => l, Err(_) => break };
        if line.trim().is_empty() { continue; }
        let reply = match serde_json::from_str::<Event>(&line) {
            Ok(ev) => hub.handle(ev),
            Err(e) => Reply { ok: false, result: format!("BAD_JSON: {e}"), line_state: String::new(), warn_lamp: false, cmd_id: None, eject_count: None },
        };
        let mut out = serde_json::to_string(&reply).unwrap_or_else(|_| "{}".into());
        out.push('\n');
        if writer.write_all(out.as_bytes()).is_err() { break; }
    }
}

// ------------------------------------------------------------------ CLI 클라이언트 모드

fn client_mode(sock: &str, args: &[String]) -> i32 {
    let (kind, code) = match args.first().map(|s| s.to_uppercase()).as_deref() {
        Some("RESET") => ("RESET", "OPERATOR_RESET"),
        Some("STATUS") => ("STATUS", "QUERY"),
        Some("STOP") => ("PRED_STOP", "OPERATOR_STOP"),
        _ => { eprintln!("usage: sf-interlock-hub [run] | send <RESET|STOP|STATUS>"); return 2; }
    };
    let mut s = match UnixStream::connect(sock) {
        Ok(s) => s,
        Err(e) => { eprintln!("❌ 허브 연결 실패 ({sock}): {e}  → 허브가 실행 중인지 확인"); return 1; }
    };
    let msg = format!("{{\"src\":\"OPERATOR\",\"kind\":\"{kind}\",\"code\":\"{code}\",\"value\":0,\"detail\":\"cli\"}}\n");
    let _ = s.write_all(msg.as_bytes());
    let _ = s.set_read_timeout(Some(Duration::from_secs(5)));
    let mut resp = String::new();
    let mut buf = [0u8; 1];
    while let Ok(1) = s.read(&mut buf) { if buf[0] == b'\n' { break; } resp.push(buf[0] as char); }
    println!("{resp}");
    if resp.contains("\"ok\":true") { 0 } else { 1 }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let sock = env_or("SF_HUB_SOCK", "/tmp/sf_interlock.sock");
    if args.first().map(|s| s.as_str()) == Some("send") { std::process::exit(client_mode(&sock, &args[1..])); }

    let home = env_or("HOME", ".");
    let db_path = env_or("SF_DB_PATH", &format!("{home}/work/middleware/smart_factory_edge.db"));
    let port = env_or("SF_PORT_CONVEYOR", "/dev/ttyACM2");

    println!("\n=======================================================");
    println!("  🦀 Smart Factory Interlock Hub (Rust)");
    println!("  CONVEYOR : {port}\n  SOCKET   : {sock}\n  DB       : {db_path}");
    println!("=======================================================\n");

    let running = Arc::new(AtomicBool::new(true));
    { let r = running.clone(); let _ = ctrlc::set_handler(move || r.store(false, Ordering::SeqCst)); }

    let state = Arc::new(Mutex::new(HubState { line_state: "UNKNOWN".into(), ..Default::default() }));
    let log_tx = spawn_db_logger(db_path);
    let conv_tx = spawn_conveyor_io(port, state.clone(), running.clone());
    let hub = Arc::new(Hub { state, conveyor: Mutex::new(conv_tx), decide: Mutex::new(()), log: Mutex::new(log_tx) });

    { // 기동 시 컨베이어 상태 동기화
        let h = hub.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_millis(1500));
            let (o, _, _) = h.command(ConveyorCmd::Ping);
            println!("🔎 [HUB] 4호기 초기 상태: {}", o.label());
        });
    }
    { let h = hub.clone(); let r = running.clone(); thread::spawn(move || watchdog_loop(h, r)); }

    let _ = std::fs::remove_file(&sock);
    let listener = UnixListener::bind(&sock).unwrap_or_else(|e| { eprintln!("❌ 소켓 바인드 실패 {sock}: {e}"); std::process::exit(1) });
    listener.set_nonblocking(true).expect("nonblocking");
    println!("🦀 [HUB] 요청 대기 중");
    while running.load(Ordering::SeqCst) {
        match listener.accept() {
            Ok((stream, _)) => {
                let _ = stream.set_nonblocking(false);
                let h = hub.clone();
                thread::spawn(move || serve_client(stream, h));
            }
            Err(e) if e.kind() == ErrorKind::WouldBlock => thread::sleep(Duration::from_millis(20)),
            Err(e) => { eprintln!("❌ accept 오류: {e}"); thread::sleep(Duration::from_millis(200)); }
        }
    }
    let _ = std::fs::remove_file(&sock);
    println!("👋 인터록 허브 종료");
}
