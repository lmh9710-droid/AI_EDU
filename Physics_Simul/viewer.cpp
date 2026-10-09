#include <cmath>
#include <cstdio>
#include <deque>
#include <vector>
#include "raylib.h"
#include "physics2d.h"

using phys::Body;
using phys::Integrator;
using phys::Vec2;
using phys::World;

/* 화면 ↔ 좌표 */
constexpr int kScreenW = 1280, kScreenH= 800;
constexpr float kPxPerM = kScreenW / 20.0f;
constexpr float kWorldH = kScreenH / kPxPerM;

Vector2 toScreen(Vec2 p) {return {(p.x + 10.0f) * kPxPerM, kScreenH - p.y *kPxPerM}; }
Vec2 toWorld(Vector2 s) {return {s.x / kPxPerM - 10.0f, (kScreenH - s.y) / kPxPerM}; }

/* 시나리오 */
void scenarioDemo(World& w) {
    w.gravity = {0, -9.8f};
    w.walls = true;
    w.bodies.clear();
    w.bodies.emplace_back(Vec2(0.0f, 10.0f), 1.0f, 1.0f, 0.6f);
    w.bodies.emplace_back(Vec2(0.5f, 14.0f), 1.0f, 1.0f, 0.6f);
    w.bodies.emplace_back(Vec2(-5.0f, 5.0f), 0.5f, 0.5f, 0.9f);
    w.bodies[2].vel = {6.0f, 0.0f};
    for (int i = 0; i < 8; ++i)
       w.bodies.emplace_back(Vec2(-8.0f * i * 2.2f, 3.0f + (i % 3)),0.3f + 0.1f, 0.5f + 0.5f * (i % 3), 0.7f);
}

void scenarioCradle(World& w) {
    w.gravity = {0, -9.8f};
    w.walls = true;
    w.bodies.clear();
    for(int i = 0; i < 5; i++) w.bodies.emplace_back(Vec2(-1.6f + i*0.802f, 0.4f), 0.4f, 1.0f, 1.0f);
    w.bodies.emplace_back(Vec2(-8.0f, 0.4f), 0.4f, 1.0f, 1.0f);
    w.bodies.back().vel = {5.0f, 0.0f};
}

void scenarioTunnel(World& w) {
    w.gravity = {0, 0};
    w.walls = true;
    w.bodies.clear();

    const float speeds[4] = {5.0f, 15.0f, 30.0f, 60.0f};
    for( int i = 0; i < 4; ++i) {
        float y = 3.0f + i * 2.0f;
        w.bodies.emplace_back(Vec2(2.0f, y), 0.05f, 0.0f, 1.0f); /* 기둥 */
        w.bodies.emplace_back(Vec2(-9.0f, y), 0.1f, 1.0f, 1.0f); /* 공 */
        w.bodies.back().vel = {speeds[i], 0.0f};
    }
}

/* 그리기 도우미 */
Color bodyColor(const Body& b, int idx) {
    if(b.invMass == 0) return Color{90, 98, 110, 255};
    static const Color pallete[] = {{38, 80, 204, 255}, {201, 116, 12, 255}, {29, 127, 71, 255}, {170, 60, 140, 255}, {30, 140, 160, 255}};
    return pallete[idx % 5];
}

void drawArrow(Vector2 a, Vector2 b, float thick, Color c) {
    DrawLineEx(a, b, thick, c);
    float dx = b.x - a.x, dy = b.y - a.y, len = std::sqrt(dx * dx + dy * dy);
    if (len < 6) return;
    dx /= len; dy /=len;
    Vector2 l = {b.x - dx * 8 - dy * 4, b.y - dy * 8 + dx * 4};
    Vector2 r = {b.x - dx * 8 + dy * 4, b.y - dy * 8 - dx * 4};
    DrawTriangle(b, r, l, c); /* ralib 삼각형은 반시계 방향 */
    DrawTriangle(b, l, r, c);
}


int main(void) {
    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_VSYNC_HINT);
    InitWindow(kScreenW, kScreenH, "physics2d viewer");
    SetTargetFPS(60);
    
    World world;
    int scenario = 1;
    auto load = [&](int s) {
        scenario = s;
        if (s == 1) scenarioDemo(world);
        if (s == 2) scenarioCradle(world);
        if (s == 3) scenarioTunnel(world);
    };
    load(1);

    const float dt = 1.0f / 60.0f;
    float acc = 0, simTime = 0;
    bool paused = false, showVel = true, showTrail = false;
    bool dragging = false;
    Vector2 dragStart{};
    std::vector<std::deque<Vector2>> trails;
    float e0 = world.kineticEnergy() + world.potentialEnergy();

    while(!WindowShouldClose()) {
        /* 입력 */
        if(IsKeyPressed(KEY_ONE)) { load(1); simTime = 0; trails.clear(); e0 = world.kineticEnergy() + world.potentialEnergy();}
        if(IsKeyPressed(KEY_TWO)) { load(2); simTime = 0; trails.clear(); e0 = world.kineticEnergy() + world.potentialEnergy();}
        if (IsKeyPressed(KEY_THREE)) { load(3); simTime = 0; trails.clear(); e0 = world.kineticEnergy() + world.potentialEnergy(); }
        if (IsKeyPressed(KEY_R)) { load(scenario); simTime = 0; trails.clear(); e0 = world.kineticEnergy() + world.potentialEnergy(); }
        if (IsKeyPressed(KEY_C)) { world.bodies.clear(); trails.clear(); e0 = 0; }
        if (IsKeyPressed(KEY_SPACE)) paused = !paused;
        if (IsKeyPressed(KEY_V)) showVel = !showVel;
        if (IsKeyPressed(KEY_T)) { showTrail = !showTrail; trails.clear(); }
        if (IsKeyPressed(KEY_S)) world.substeps = world.substeps >= 8 ? 1 : world.substeps * 2;
        if (IsKeyPressed(KEY_I))
            world.integrator = world.integrator == Integrator::SemiImplicitEuler ? Integrator::ExplicitEuler : Integrator::SemiImplicitEuler;
 
        Vector2 mouse = GetMousePosition();
        if (IsMouseButtonPressed(MOUSE_BUTTON_LEFT)) { dragging = true; dragStart = mouse; }
        if (dragging && IsMouseButtonReleased(MOUSE_BUTTON_LEFT)) {
            dragging = false;
            Vec2 p = toWorld(dragStart);
            float r = GetRandomValue(25, 60) / 100.0f;
            world.bodies.emplace_back(p, r, r * r * 4.0f, 0.7f);       // 질량은 면적에 비례
            Vec2 pull = toWorld(dragStart) - toWorld(mouse);           // 당긴 반대 방향으로 발사
            world.bodies.back().vel = pull * 4.0f;
            e0 = world.kineticEnergy() + world.potentialEnergy();
        }
        if (IsMouseButtonPressed(MOUSE_BUTTON_RIGHT)) {
            world.bodies.emplace_back(toWorld(mouse), 0.4f, 0.0f, 1.0f);  // 질량 0 = 정적
        }
 
        // ----- 물리: 고정 타임스텝 -----
        bool stepOnce = paused && IsKeyPressed(KEY_N);
        if (!paused) acc += GetFrameTime();
        if (acc > 0.25f) acc = 0.25f;  // 창을 끌어서 멈췄다 풀릴 때 폭주 방지
        while (acc >= dt || stepOnce) {
            world.step(dt);
            simTime += dt;
            if (showTrail) {
                trails.resize(world.bodies.size());
                for (size_t i = 0; i < world.bodies.size(); ++i) {
                    trails[i].push_back(toScreen(world.bodies[i].pos));
                    if (trails[i].size() > 180) trails[i].pop_front();
                }
            }
            if (stepOnce) { stepOnce = false; break; }
            acc -= dt;
        }
 
        // ----- 그리기 -----
        BeginDrawing();
        ClearBackground(Color{244, 246, 248, 255});
 
        // 1 m 격자
        for (int x = -10; x <= 10; ++x) {
            float sx = toScreen({(float)x, 0}).x;
            DrawLineV({sx, 0}, {sx, (float)kScreenH}, x == 0 ? Color{210, 216, 224, 255} : Color{228, 232, 237, 255});
        }
        for (int y = 1; y <= (int)kWorldH; ++y) {
            float sy = toScreen({0, (float)y}).y;
            DrawLineV({0, sy}, {(float)kScreenW, sy}, Color{228, 232, 237, 255});
            if (y % 2 == 0) DrawText(TextFormat("%d m", y), 6, (int)sy + 3, 10, GRAY);
        }
        if (world.walls) DrawRectangle(0, kScreenH - 3, kScreenW, 3, Color{24, 33, 43, 255});
 
        // 궤적
        if (showTrail)
            for (size_t i = 0; i < trails.size() && i < world.bodies.size(); ++i)
                for (size_t k = 1; k < trails[i].size(); ++k)
                    DrawLineV(trails[i][k - 1], trails[i][k], Fade(bodyColor(world.bodies[i], (int)i), 0.35f));
 
        // 물체
        for (size_t i = 0; i < world.bodies.size(); ++i) {
            const Body& b = world.bodies[i];
            Vector2 c = toScreen(b.pos);
            float rpx = std::fmax(b.radius * kPxPerM, 2.0f);
            Color col = bodyColor(b, (int)i);
            DrawCircleV(c, rpx, Fade(col, 0.85f));
            DrawCircleLinesV(c, rpx, Color{24, 33, 43, 255});
            if (showVel && b.invMass > 0 && dot(b.vel, b.vel) > 0.01f) {
                float s = std::fmin(0.15f, 3.0f / length(b.vel));     // 너무 길어지지 않게
                drawArrow(c, toScreen(b.pos + b.vel * s), 2.0f, Color{70, 78, 90, 255});
            }
        }
 
        // 새총 미리보기
        if (dragging) {
            DrawCircleLinesV(dragStart, 20, Color{38, 80, 204, 255});
            DrawLineEx(dragStart, mouse, 2, Color{201, 116, 12, 255});
            Vector2 launch = {dragStart.x + (dragStart.x - mouse.x) * 0.6f, dragStart.y + (dragStart.y - mouse.y) * 0.6f};
            drawArrow(dragStart, launch, 3, Color{38, 80, 204, 255});
        }
 
        // 정보 패널
        float e = world.kineticEnergy() + world.potentialEnergy();
        Vec2 p = world.momentum();
        const char* scName = scenario == 1 ? "1 Demo" : scenario == 2 ? "2 Newton's cradle" : "3 Tunneling";
        DrawRectangle(kScreenW - 330, 56, 320, 170, Fade(WHITE, 0.92f));
        DrawRectangleLines(kScreenW - 330, 56, 320, 170, Color{211, 217, 224, 255});
        int x = kScreenW - 318, y = 66;
        DrawText(TextFormat("Scenario   %s", scName), x, y, 18, Color{24, 33, 43, 255}); y += 26;
        DrawText(TextFormat("t = %.2f s   bodies = %d   %s", simTime, (int)world.bodies.size(), paused ? "[PAUSED]" : ""), x, y, 14, DARKGRAY); y += 20;
        DrawText(TextFormat("Integrator %s", world.integrator == Integrator::SemiImplicitEuler ? "semi-implicit" : "EXPLICIT"), x, y, 14, DARKGRAY); y += 20;
        DrawText(TextFormat("Substeps   %d  (h = %.2f ms)", world.substeps, dt / world.substeps * 1000), x, y, 14, DARKGRAY); y += 20;
        DrawText(TextFormat("Energy     %.2f J  (%+.1f%%)", e, e0 > 0 ? (e - e0) / e0 * 100 : 0.0f), x, y, 14, DARKGRAY); y += 20;
        DrawText(TextFormat("Momentum   (%.2f, %.2f)", p.x, p.y), x, y, 14, DARKGRAY); y += 20;
        DrawFPS(x, y);
 
        DrawText("Drag: throw   Right-click: pillar   1/2/3: scenario   Space: pause   N: step   S: substeps   I: integrator   V/T: vectors/trails   R: reset   C: clear",
                 10, 10, 14, Color{90, 101, 115, 255});
        if (scenario == 3)
            DrawText("Balls at 5/15/30/60 m/s (bottom to top). Press S: substeps 2, 4, 8 stop one more ball each. Then R to rerun.", 10, 30, 14, Color{187, 51, 39, 255});
        EndDrawing();
    }
    CloseWindow();
    return 0;
}
