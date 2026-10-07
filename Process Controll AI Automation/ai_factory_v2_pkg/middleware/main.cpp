#include "Common.h"
#include "DatabaseManager.h"
#include "HubClient.h"
#include "EquipmentNodes.h"
#include <csignal>

static void onSignal(int) { system_active = false; }

int main() {
    setenv("TZ", "Asia/Seoul", 1); tzset();
    std::signal(SIGINT, onSignal); std::signal(SIGTERM, onSignal);

    const std::string home = getenv_or("HOME", ".");
    const std::string db_path = getenv_or("SF_DB_PATH", home + "/work/middleware/smart_factory_edge.db");
    const std::string hub_sock = getenv_or("SF_HUB_SOCK", "/tmp/sf_interlock.sock");

    auto db = std::make_shared<DatabaseManager>(db_path);
    if (!db->initializeDatabase()) { std::cerr << "❌ DB 초기화 실패: " << db_path << "\n"; return 1; }
    db->start();
    auto hub = std::make_shared<HubClient>(hub_sock, db);

    std::cout << "\n=======================================================\n"
              << "  ⚙️ Smart Factory Data Middleware (수집·저장·규격 판정)\n"
              << "  DB  : " << db_path << "\n  HUB : " << hub_sock << " (Rust 인터록 허브)\n"
              << "=======================================================\n\n";

    std::string p1 = getenv_or("SF_PORT_FORGING", "/dev/ttyACM0");
    std::string p2 = getenv_or("SF_PORT_ROLLING", "/dev/ttyUSB0");
    std::string p3 = getenv_or("SF_PORT_HEAT",    "/dev/ttyACM1");
    // 4호기 컨베이어 포트는 Rust 인터록 허브가 단독으로 사용한다.

    std::unique_ptr<BaseEquipment> eq1 = std::make_unique<ForgingNode>(p1, db, hub);
    std::unique_ptr<BaseEquipment> eq2 = std::make_unique<RollingNode>(p2, db, hub);
    std::unique_ptr<BaseEquipment> eq3 = std::make_unique<HeatNode>(p3, db, hub);

    std::thread t1(&BaseEquipment::startCaptureLoop, eq1.get());
    std::thread t2(&BaseEquipment::startCaptureLoop, eq2.get());
    std::thread t3(&BaseEquipment::startCaptureLoop, eq3.get());
    std::thread th(&HubClient::senderLoop, hub.get());

    t1.join(); t2.join(); t3.join(); th.join();
    db->stop();
    std::cout << "👋 미들웨어 정상 종료\n";
    return 0;
}
