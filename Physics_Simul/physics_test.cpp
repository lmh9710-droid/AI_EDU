// physics_test.cpp — physics2d.h 단위 테스트 (GoogleTest)
//
// 테스트 설계 원칙
//  1) 단위 테스트: 함수 하나의 입력·출력을 손으로 계산한 값과 비교
//  2) 해석해 비교: 공식으로 정답을 아는 상황을 돌려서 오차 확인
//  3) 보존 법칙: 운동량·에너지처럼 변하면 안 되는 값 확인
//  4) 알려진 한계 기록: 터널링처럼 "현재 엔진이 실패하는 것"도 테스트로 남겨 둠
//     → 나중에 CCD를 구현하면 이 테스트가 깨지면서 개선을 알려 줌

#include <gtest/gtest.h>
#include <cmath>
#include "physics2d.h"

using namespace phys;

constexpr float kDt = 1.0f / 60.0f;
constexpr float kG = 9.8f;

// =====================================================================
// 1. 벡터 수학
// =====================================================================
TEST(Vec2Test, BasicArithmetic) {
    Vec2 a(1, 2), b(3, -4);
    Vec2 s = a + b;
    EXPECT_FLOAT_EQ(s.x, 4);
    EXPECT_FLOAT_EQ(s.y, -2);
    EXPECT_FLOAT_EQ(dot(a, b), 1 * 3 + 2 * -4);
    EXPECT_FLOAT_EQ(length(Vec2(3, 4)), 5);
}

// =====================================================================
// 2. 충돌 감지
// =====================================================================
TEST(CollisionDetection, SeparatedCirclesDoNotCollide) {
    Body a(Vec2(0, 0), 1, 1, 1), b(Vec2(2.01f, 0), 1, 1, 1);
    Contact c;
    EXPECT_FALSE(circleVsCircle(a, b, c));
}

TEST(CollisionDetection, OverlapGivesNormalAndPenetration) {
    Body a(Vec2(0, 0), 1, 1, 1), b(Vec2(1.5f, 0), 1, 1, 1);
    Contact c;
    ASSERT_TRUE(circleVsCircle(a, b, c));
    EXPECT_NEAR(c.normal.x, 1.0f, 1e-6f);   // a -> b 방향
    EXPECT_NEAR(c.normal.y, 0.0f, 1e-6f);
    EXPECT_NEAR(c.penetration, 0.5f, 1e-6f);
    EXPECT_NEAR(length(c.normal), 1.0f, 1e-6f);  // 단위 벡터
}

TEST(CollisionDetection, SameCenterDoesNotProduceNaN) {
    Body a(Vec2(3, 3), 1, 1, 1), b(Vec2(3, 3), 1, 1, 1);
    Contact c;
    ASSERT_TRUE(circleVsCircle(a, b, c));
    EXPECT_FALSE(std::isnan(c.normal.x));
    EXPECT_FALSE(std::isnan(c.normal.y));
    EXPECT_NEAR(length(c.normal), 1.0f, 1e-6f);
}

// =====================================================================
// 3. 충돌 응답 (충격량)
// =====================================================================
Contact makeContact(Body& a, Body& b) {
    Contact c;
    circleVsCircle(a, b, c);
    return c;
}

TEST(CollisionResponse, EqualMassElasticSwapsVelocities) {
    Body a(Vec2(0, 0), 1, 1, 1.0f), b(Vec2(1.9f, 0), 1, 1, 1.0f);
    a.vel = {3, 0};
    b.vel = {-1, 0};
    Contact c = makeContact(a, b);
    resolveCollision(c);
    EXPECT_NEAR(a.vel.x, -1, 1e-5f);  // 같은 질량 + 완전 탄성 → 속도 교환
    EXPECT_NEAR(b.vel.x, 3, 1e-5f);
}

TEST(CollisionResponse, ConservesMomentumForUnequalMass) {
    Body a(Vec2(0, 0), 1, 2.0f, 0.5f), b(Vec2(1.9f, 0.3f), 1, 5.0f, 0.5f);
    a.vel = {4, 1};
    b.vel = {-2, 0};
    Vec2 before = a.vel * 2.0f + b.vel * 5.0f;
    Contact c = makeContact(a, b);
    resolveCollision(c);
    Vec2 after = a.vel * 2.0f + b.vel * 5.0f;
    EXPECT_NEAR(after.x, before.x, 1e-4f);
    EXPECT_NEAR(after.y, before.y, 1e-4f);
}

TEST(CollisionResponse, RestitutionScalesSeparationSpeed) {
    // 충돌 후 법선 방향 상대 속도 = -e × 충돌 전 상대 속도
    for (float e : {0.0f, 0.3f, 0.8f, 1.0f}) {
        Body a(Vec2(0, 0), 1, 1, e), b(Vec2(1.9f, 0), 1, 1, e);
        a.vel = {2, 0};
        Contact c = makeContact(a, b);
        float before = dot(b.vel - a.vel, c.normal);
        resolveCollision(c);
        float after = dot(b.vel - a.vel, c.normal);
        EXPECT_NEAR(after, -e * before, 1e-5f) << "e = " << e;
    }
}

TEST(CollisionResponse, SeparatingBodiesAreUntouched) {
    Body a(Vec2(0, 0), 1, 1, 1), b(Vec2(1.9f, 0), 1, 1, 1);
    a.vel = {-1, 0};  // 이미 서로 멀어지는 중
    b.vel = {1, 0};
    Contact c = makeContact(a, b);
    resolveCollision(c);
    EXPECT_FLOAT_EQ(a.vel.x, -1);
    EXPECT_FLOAT_EQ(b.vel.x, 1);
}

TEST(CollisionResponse, StaticBodyNeverMoves) {
    World w;
    w.gravity = {0, 0};
    w.bodies.emplace_back(Vec2(0, 5), 1, 0.0f, 1.0f);   // 질량 0 → 정적 물체
    w.bodies.emplace_back(Vec2(-4, 5), 0.5f, 1.0f, 1.0f);
    w.bodies[1].vel = {5, 0};
    for (int i = 0; i < 40; ++i) w.step(kDt);           // 충돌 직후까지만
    EXPECT_FLOAT_EQ(w.bodies[0].pos.x, 0);
    EXPECT_FLOAT_EQ(w.bodies[0].pos.y, 5);
    EXPECT_LT(w.bodies[1].vel.x, 0);  // 튕겨 나왔어야 함
}

// =====================================================================
// 4. 해석해 비교
// =====================================================================
// 자유낙하 1초 후 높이 오차
float freeFallError(float dt, int substeps) {
    World w;
    w.walls = false;
    w.substeps = substeps;
    w.bodies.emplace_back(Vec2(0, 100), 0.5f, 1, 0);
    const int steps = static_cast<int>(std::round(1.0f / dt));
    for (int i = 0; i < steps; ++i) w.step(dt);
    float t = steps * dt;
    float exact = 100 - 0.5f * kG * t * t;
    return std::fabs(w.bodies[0].pos.y - exact);
}

TEST(AnalyticSolution, FreeFallMatchesFormula) {
    // 반암시적 오일러의 위치 오차 ≈ g·h·t/2 → dt=1/60, t=1이면 약 8.2 cm
    EXPECT_LT(freeFallError(kDt, 1), 0.1f);
}

TEST(AnalyticSolution, FreeFallErrorIsFirstOrder) {
    // 1차 정확도: 스텝을 절반으로 줄이면 오차도 절반
    float e1 = freeFallError(1.0f / 60, 1);
    float e2 = freeFallError(1.0f / 120, 1);
    EXPECT_NEAR(e1 / e2, 2.0f, 0.1f);
    // 서브스텝 2는 dt를 절반으로 줄인 것과 같아야 함
    EXPECT_NEAR(freeFallError(1.0f / 60, 2), e2, 1e-3f);
}

TEST(AnalyticSolution, BounceReachesRestitutionSquaredHeight) {
    // 높이 h에서 떨어지면 첫 최고점은 h·e²
    const float h0 = 5.0f, r = 0.5f, e = 0.8f;
    World w;
    w.substeps = 4;
    w.bodies.emplace_back(Vec2(0, h0 + r), r, 1, e);
    float prevVy = 0, peak = -1;
    for (int i = 0; i < 600 && peak < 0; ++i) {
        w.step(kDt);
        float vy = w.bodies[0].vel.y;
        if (prevVy > 0 && vy <= 0) peak = w.bodies[0].pos.y - r;
        prevVy = vy;
    }
    ASSERT_GT(peak, 0) << "공이 튀어 오르지 않음";
    EXPECT_NEAR(peak, h0 * e * e, h0 * e * e * 0.05f);  // 5% 이내
}

// =====================================================================
// 5. 보존 법칙
// =====================================================================
TEST(Conservation, MomentumConservedInMultiBodyCollisions) {
    World w;
    w.gravity = {0, 0};
    w.walls = false;  // 외부 힘(벽) 제거
    w.bodies.emplace_back(Vec2(-3, 0.2f), 0.5f, 1.0f, 0.7f);
    w.bodies.emplace_back(Vec2(0, 0), 0.7f, 3.0f, 0.7f);
    w.bodies.emplace_back(Vec2(3, -0.3f), 0.4f, 0.5f, 0.7f);
    w.bodies[0].vel = {4, 0};
    w.bodies[2].vel = {-3, 0.5f};
    Vec2 p0 = w.momentum();
    for (int i = 0; i < 180; ++i) w.step(kDt);
    Vec2 p1 = w.momentum();
    EXPECT_NEAR(p1.x, p0.x, 1e-3f);
    EXPECT_NEAR(p1.y, p0.y, 1e-3f);
}

TEST(Conservation, ElasticCollisionKeepsKineticEnergy) {
    World w;
    w.gravity = {0, 0};
    w.walls = false;
    w.bodies.emplace_back(Vec2(-2, 0), 0.5f, 1.0f, 1.0f);
    w.bodies.emplace_back(Vec2(2, 0.3f), 0.5f, 2.0f, 1.0f);
    w.bodies[0].vel = {3, 0};
    w.bodies[1].vel = {-1, 0};
    float k0 = w.kineticEnergy();
    for (int i = 0; i < 180; ++i) w.step(kDt);
    EXPECT_NEAR(w.kineticEnergy(), k0, k0 * 0.001f);
}

TEST(Conservation, InelasticCollisionLosesEnergy) {
    World w;
    w.gravity = {0, 0};
    w.walls = false;
    w.bodies.emplace_back(Vec2(-2, 0), 0.5f, 1.0f, 0.2f);
    w.bodies.emplace_back(Vec2(2, 0), 0.5f, 1.0f, 0.2f);
    w.bodies[0].vel = {3, 0};
    float k0 = w.kineticEnergy();
    for (int i = 0; i < 180; ++i) w.step(kDt);
    EXPECT_LT(w.kineticEnergy(), k0);  // 에너지가 늘어나면 버그
}

// =====================================================================
// 6. 적분기 비교 (용수철 진동, 에너지 보존)
// =====================================================================
// 용수철 진동 5초 후 에너지 변화율(%)
float springEnergyDrift(Integrator integ, float dt) {
    const float k = 40, m = 1, A = 2;
    World w;
    w.gravity = {0, 0};
    w.walls = false;
    w.integrator = integ;
    w.bodies.emplace_back(Vec2(A, 0), 0.3f, m, 0);
    auto energy = [&] {
        const Body& b = w.bodies[0];
        return 0.5f * m * dot(b.vel, b.vel) + 0.5f * k * dot(b.pos, b.pos);
    };
    float e0 = energy();
    const int steps = static_cast<int>(std::round(5.0f / dt));
    for (int i = 0; i < steps; ++i) {
        w.bodies[0].force = w.bodies[0].pos * -k;  // F = -kx
        w.step(dt);
    }
    return (energy() - e0) / e0 * 100.0f;
}

TEST(Integrator, SemiImplicitEulerKeepsSpringEnergyBounded) {
    EXPECT_LT(std::fabs(springEnergyDrift(Integrator::SemiImplicitEuler, kDt)), 10.0f);
}

TEST(Integrator, ExplicitEulerGainsEnergy) {
    // 알려진 한계를 테스트로 기록: 명시적 오일러는 진동에서 에너지가 계속 증가
    float drift = springEnergyDrift(Integrator::ExplicitEuler, kDt);
    EXPECT_GT(drift, 100.0f) << "명시적 오일러인데 에너지가 거의 보존됨? 적분 순서를 확인";
}

// =====================================================================
// 7. 안정성 · 엣지 케이스
// =====================================================================
TEST(Stability, BallRestsOnFloor) {
    World w;
    w.bodies.emplace_back(Vec2(0, 0.5f), 0.5f, 1, 0.5f);
    for (int i = 0; i < 300; ++i) w.step(kDt);
    EXPECT_NEAR(w.bodies[0].pos.y, 0.5f, 0.01f);   // 바닥에 박히거나 떠오르지 않음
    EXPECT_LT(std::fabs(w.bodies[0].vel.y), 0.2f); // 계속 튀지 않음
}

TEST(Stability, NoNaNAfterLongRun) {
    World w;
    for (int i = 0; i < 20; ++i)
        w.bodies.emplace_back(Vec2(-8 + i * 0.8f, 2 + (i % 4) * 1.5f), 0.35f, 1.0f + i % 3, 0.6f);
    for (int i = 0; i < 60 * 30; ++i) w.step(kDt);  // 30초
    for (auto& b : w.bodies) {
        ASSERT_TRUE(std::isfinite(b.pos.x) && std::isfinite(b.pos.y));
        ASSERT_TRUE(std::isfinite(b.vel.x) && std::isfinite(b.vel.y));
        EXPECT_GE(b.pos.y, b.radius - 0.05f);          // 바닥 아래로 빠지지 않음
        EXPECT_LE(std::fabs(b.pos.x), 10 - b.radius + 0.05f);
    }
}

// =====================================================================
// 8. 터널링 (알려진 한계 + 서브스텝으로 해결되는지)
// =====================================================================
// 빠른 공이 얇은 정적 물체를 뚫고 지나가는지
bool tunnels(int substeps) {
    World w;
    w.gravity = {0, 0};
    w.walls = false;
    w.substeps = substeps;
    w.bodies.emplace_back(Vec2(0, 0), 0.05f, 0.0f, 1.0f);   // 지름 10 cm 정적 기둥
    w.bodies.emplace_back(Vec2(-5, 0), 0.1f, 1.0f, 1.0f);   // 지름 20 cm 공
    w.bodies[1].vel = {40, 0};                              // 한 스텝 0.67 m 이동
    for (int i = 0; i < 30; ++i) w.step(kDt);
    return w.bodies[1].pos.x > 0;  // 기둥 오른쪽에 있으면 뚫고 지나간 것
}

TEST(Tunneling, FastBodyPassesThroughThinObstacle_KnownLimitation) {
    // 현재 엔진은 연속 충돌 감지(CCD)가 없어서 터널링이 일어남.
    // CCD를 구현하면 이 테스트가 실패하므로 그때 EXPECT_FALSE로 바꾸면 됨.
    EXPECT_TRUE(tunnels(1));
}

TEST(Tunneling, SubstepsPreventTunneling) {
    // 원-원 충돌은 공의 중심이 기둥 중심을 넘기 전에 감지돼야 제대로 튕겨 나감.
    // 넘은 뒤에 감지되면 법선이 반대로 잡혀 "멀어지는 중"으로 판정되고 그대로 통과.
    // 조건: 서브스텝당 이동 거리 < 두 반지름의 합(0.15 m)
    //   서브스텝 4: 40/60/4 ≈ 0.167 m > 0.15 → 여전히 통과
    //   서브스텝 8: 40/60/8 ≈ 0.083 m < 0.15 → 막힘
    EXPECT_TRUE(tunnels(4));
    EXPECT_FALSE(tunnels(8));
}