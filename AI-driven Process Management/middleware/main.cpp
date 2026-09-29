#include "Common.h"
#include "DatabaseManager.h"
#include "EquipmentNodes.h"

int main() {
    auto dbManager = std::make_shared<DatabaseManager>("smart_factory_edge.db");
    dbManager->initializeDatabase();

    std::cout << "\n=======================================================\n";
    std::cout << "  ⚙️ OOP & Split-File Architecture Middleware Active\n";
    std::cout << "=======================================================\n\n";

    // WSL 장치 매핑 경로 확정
    std::string p1 = "/dev/ttyACM0"; // 1호기 압조
    std::string p2 = "/dev/ttyUSB0"; // 2호기 전조
    std::string p3 = "/dev/ttyACM1"; // 3호기 열처리
    // std::string p2 = "/dev/ttyACM1"; // 2호기 전조
    // std::string p3 = "/dev/ttyUSB0"; // 3호기 열처리
    std::string p4 = "/dev/ttyACM2"; // 4호기 컨베이어

    // std::string p3 = "/dev/ttyACM2"; // 3호기 열처리
    // std::string p4 = "/dev/ttyUSB0"; // 4호기 컨베이어


    // 다형성(Upcasting) 스마트 포인터 배정
    std::unique_ptr<BaseEquipment> eq1 = std::make_unique<ForgingNode>(p1, "EQ_FORGING_01", dbManager);
    std::unique_ptr<BaseEquipment> eq2 = std::make_unique<RollingNode>(p2, "EQ_ROLLING_01", dbManager);
    std::unique_ptr<BaseEquipment> eq3 = std::make_unique<HeatNode>(p3, "EQ_HEAT_01", dbManager);
    auto interlockHub = std::make_unique<ConveyorInterlockResponder>(p4);

    // 공정별 멀티스레드 병렬 구동
    std::thread t1(&BaseEquipment::startCaptureLoop, eq1.get());
    std::thread t2(&BaseEquipment::startCaptureLoop, eq2.get());
    std::thread t3(&BaseEquipment::startCaptureLoop, eq3.get());
    std::thread t4(&ConveyorInterlockResponder::startListening, interlockHub.get());

    t1.join(); t2.join(); t3.join(); t4.join();
    return 0;
}
