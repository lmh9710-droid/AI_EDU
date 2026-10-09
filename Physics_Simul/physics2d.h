#pragma once

#include <cmath>
#include <vector> 

namespace phys {

    struct Vec2 {
        float x = 0, y= 0;
        Vec2() = default;
        Vec2(float x, float y) : x(x), y(y) {}
        Vec2 operator+(const Vec2& o) const { return {x + o.x, y + o.y};}
        Vec2 operator-(const Vec2& o) const { return {x - o.x, y - o.y};}
        Vec2 operator*(float s) const {return {x * s, y * s};}
        Vec2& operator+= (const Vec2& o) { x +=o.x; y +=o.y; return *this; }
        Vec2& operator-= (const Vec2& o) { x -=o.x; y -=o.y; return *this; }
    };

    inline float dot(const Vec2& a, const Vec2& b) { return a.x * b.x + a.y * b.y; }
    inline float length(const Vec2& v) { return std::sqrt(dot(v, v)); }


    /* 강체 구조체 */
    struct Body {
        Vec2 pos, vel, force;
        float radius;
        float invMass;
        float restitution;

        Body(Vec2 p, float r, float mass, float e)
           : pos(p), radius(r), invMass(mass > 0 ? 1.0f / mass : 0.0f), restitution(e) {}
        
        float mass() const { return invMass > 0  ? 1.0f/invMass : 0.0f; }
    };

    /* 충돌 */
    struct Contact {
        Body* a = nullptr;
        Body* b = nullptr;
        Vec2 normal;
        float penetration = 0;
    };

    inline bool circleVsCircle(Body& a, Body& b, Contact& c) {
        Vec2 d = b.pos - a.pos;
        float r = a.radius + b.radius;
        float distSq = dot(d, d);
        if (distSq >= r*r) return false;
        float dist = std::sqrt(distSq);
        c.a = &a; c.b = &b;
        c.normal = dist > 1e-6f ? d* (1.0f/dist) : Vec2(0, 1);
        c.penetration = r - dist;
        return true;

    }

    inline void resolveCollision(Contact& c) {
        Body& a = *c.a;
        Body& b = *c.b;
        Vec2 rv = b.vel - a.vel;
        float velAlongNormal = dot(rv, c.normal);
        if(velAlongNormal > 0) return;
        float invMassSum = a.invMass + b.invMass;
        if(invMassSum == 0) return;
        float e = std::fmin(a.restitution, b.restitution);
        float j = -(1 + e) * velAlongNormal / invMassSum;
        Vec2 impulse = c.normal * j;
        a.vel -= impulse * a.invMass;
        b.vel += impulse * b.invMass;
    } 

    inline void correctPosition(Contact& c) {
        const float percent = 0.8f, slop = 0.01f;
        float invMassSum = c.a->invMass + c.b->invMass;
        if(invMassSum == 0) return;
        Vec2 correction = c.normal * (std::fmax(c.penetration - slop, 0.0f) / invMassSum * percent);
        c.a->pos -= correction * c.a->invMass;
        c.b->pos += correction * c.b->invMass;
    }

    enum class Integrator { ExplicitEuler, SemiImplicitEuler};

    struct World {
      std::vector<Body> bodies; 
      Vec2 gravity {0, -9.8f};
      float floorY = 0.0f, leftX = -10.0f, rightX = 10.0f;
      bool walls = true;

      Integrator integrator = Integrator::SemiImplicitEuler;
      int substeps = 1;

      void step(float dt) {
         float h = dt / substeps;
         for(int s = 0; s < substeps; ++s) subStep(h);
         for(auto& b : bodies) b.force = {0, 0};
      }

      float kineticEnergy() const {
        float k = 0;
        for(auto& b : bodies) if (b.invMass > 0) 
        k += 0.05f * b.mass() * dot(b.vel, b.vel);
        return k;
      }

      float potentialEnergy() const {
        float u = 0;
        for(auto& b: bodies) if(b.invMass > 0) 
        u += b.mass() * -gravity.y * (b.pos.y - floorY);
        return u;
      }

      Vec2 momentum() const {
         Vec2 p;
         for(auto& b : bodies) if (b.invMass > 0) p += b.vel * b.mass();
         return p;
      }

      private: 
         void subStep(float h) {
            /* 적분 */
            for(auto& b : bodies) {
                if (b.invMass == 0) continue;
                Vec2 accel = gravity + b.force * b.invMass;
                if (integrator == Integrator::SemiImplicitEuler) {
                    b.vel += accel * h;
                    b.pos += b.vel * h;
                } else {
                    b.pos += b.vel * h;
                    b.vel += accel * h;
                }
            }
           
           /* 원.원 충돌 */
           std::vector<Contact> contacts;
            for (size_t i = 0; i < bodies.size(); ++i)
              for (size_t k = i + 1; k < bodies.size(); ++k) {
                 Contact c;
                 if (circleVsCircle(bodies[i], bodies[k], c))
                 contacts.push_back(c); 
              }
            
            for(auto& c : contacts) resolveCollision(c);
            for(auto& c : contacts) correctPosition(c);
            
            /* 바닥.벽 */
            if (!walls) return;
            for(auto& b : bodies) {
                if (b.invMass == 0) continue;
                if(b.pos.y - b.radius < floorY) {
                    b.pos.y = floorY + b.radius;
                    if(b.vel.y < 0) b.vel.y = -b.vel.y * b.restitution;
                }
                if(b.pos.x - b.radius < leftX) {
                    b.pos.x = leftX + b.radius;
                    if(b.vel.x < 0) b.vel.x = -b.vel.x * b.restitution;
                }
                if(b.pos.x +b.radius > rightX) {
                    b.pos.x = rightX - b.radius;
                    if (b.vel.x > 0) b.vel.x = -b.vel.x * b.restitution;
                }

            }
         }


    };
}