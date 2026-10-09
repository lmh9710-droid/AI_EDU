// main.cpp — 원래 physics2d.cpp의 데모 (엔진은 physics2d.h로 분리)
#include <cstdio>
#include "physics2d.h"

using namespace phys;

int main() {
    World world;
    // 위치, 반지름, 질량, 반발계수
    world.bodies.emplace_back(Vec2(0.0f, 10.0f), 1.0f, 1.0f, 0.6f);   // 공 A
    world.bodies.emplace_back(Vec2(0.5f, 14.0f), 1.0f, 1.0f, 0.6f);   // 공 B
    world.bodies.emplace_back(Vec2(-5.0f, 5.0f), 0.5f, 0.5f, 0.9f);   // 작은 공
    world.bodies[2].vel = {6.0f, 0.0f};

    const float dt = 1.0f / 60.0f;
    for (int frame = 0; frame <= 300; ++frame) {
        if (frame % 30 == 0) {
            std::printf("t=%.1fs ", frame * dt);
            for (size_t i = 0; i < world.bodies.size(); ++i) {
                auto& b = world.bodies[i];
                std::printf("| #%zu pos(%6.2f,%6.2f) vel(%6.2f,%6.2f) ", i, b.pos.x, b.pos.y, b.vel.x, b.vel.y);
            }
            std::printf("\n");
        }
        world.step(dt);
    }
    return 0;
}