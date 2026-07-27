#version 330
// pax3d_render water surface — fragment stage (engine promotion of the
// planetside/paxcraft shared water, 2026-07-28 voxel-lane ask).
//
// The documented pitfalls of the source system (sfb2 terrain demo
// sessions 449-453, WATER_SYSTEM.md) are preserved: noise (never sine)
// fragment normals, restrained Fresnel, distance-faded tight specular.
// Sky reflection arrives per-frame from the game's REAL sky (SH-derived
// horizon/zenith tints) and the sun uniforms are the game's day-night
// feed — planetside flips them to the MOON below -8 deg solar altitude,
// so night water reflects moonlight for free.
//
// Shore pass (real seafloor depth from the provider texture): per-channel
// Beer-Lambert body colour (red dies first: turquoise -> navy with
// depth), depth-keyed alpha melting the waterline into the sand, contact
// foam gated by WORLD-SPACE seafloor slope, marching iso-depth shore
// bands, Gerstner crest-pinch whitecaps.
//
// Distance haze is the ENGINE's analytic aerial perspective — the exact
// pax_pbr.frag formula (exponential-height medium, forward-scattering
// sun lobe), so sea, terrain and any far-field ring haze as ONE system
// (the 2026-07-28 voxel-lane finding: planetside's plain exp fog never
// matched its hazed terrain).  With u_density = 0: trans = 1, exact
// no-op — airless worlds keep their unfogged horizon.
//
// Game-specific whitecap tuning arrives as uniforms (defaults =
// planetside; the voxel game shrinks patches ~3x and gates tighter):
//   u_whitecap = (patch noise scale, patch lo, patch hi, foam gain)
//   u_capgate  = (cap noise gate lo, hi)

// --- Lighting ---
uniform vec3 u_sun_dir_world;
uniform vec3 u_sun_color;
uniform vec3 u_sky_horizon;
uniform vec3 u_sky_zenith;

// --- Camera & animation ---
uniform vec3 u_camera_pos;
uniform float u_time;

// --- Water colours & optics ---
uniform vec3 u_shallow_color;
uniform vec3 u_deep_color;
uniform vec3 u_absorb;        // per-channel extinction, 1/m (R > G > B)
uniform float u_alpha_k;      // view-through opacity rate, 1/m
uniform float u_foam_gain;    // master foam scale
uniform vec4 u_whitecap;      // patch scale, patch lo/hi, base gain
uniform vec2 u_capgate;       // cap noise gate lo/hi

// --- Seafloor depth map (provider contract) ---
uniform sampler2D u_seafloor;
uniform vec3 u_sf_origin_size;   // xy = SW corner, z = size (<=0: not ready)
uniform float u_water_z;
uniform float u_uncovered_dz;    // floor z - water z where the map has no data

// --- Aerial haze (the pipeline's analytic block, pax_pbr.frag) ---
uniform vec3 u_haze_color;
uniform vec3 u_sun_haze_color;
uniform float u_sun_power;
uniform float u_density;
uniform float u_inv_scale_h;
uniform float u_base_h;

in vec3 v_worldPos;
in vec3 v_waveNormal;
in float v_crest;
in float v_edge;

out vec4 o_color;

// ---------------------------------------------------------------------------
// Hash noise — non-periodic, breaks the repetition sine waves create.
// ---------------------------------------------------------------------------
float hash21(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float vnoise2(vec2 p) {
    return vnoise(p) * 0.65 + vnoise(p * 2.13 + vec2(17.0, 31.0)) * 0.35;
}

// ---------------------------------------------------------------------------
// Fragment-level normal from noise gradients (finite differences on
// scrolling noise layers — non-periodic, no repeats at any distance).
// ---------------------------------------------------------------------------
vec3 waterNormal(vec3 baseN, vec3 wp, float t) {
    float px = 0.0;
    float py = 0.0;
    float e = 0.5;

    // Layer 1: large ripples scrolling northeast (~12-16 m features)
    vec2 uv1 = wp.xy * 0.06 + vec2(t * 0.30, t * 0.15);
    px += (vnoise2(uv1 + vec2(e, 0.0)) - vnoise2(uv1 - vec2(e, 0.0))) * 0.55;
    py += (vnoise2(uv1 + vec2(0.0, e)) - vnoise2(uv1 - vec2(0.0, e))) * 0.55;

    // Layer 2: medium ripples scrolling northwest (~5-8 m features)
    vec2 uv2 = wp.xy * 0.14 + vec2(-t * 0.40, t * 0.25);
    px += (vnoise2(uv2 + vec2(e, 0.0)) - vnoise2(uv2 - vec2(e, 0.0))) * 0.35;
    py += (vnoise2(uv2 + vec2(0.0, e)) - vnoise2(uv2 - vec2(0.0, e))) * 0.35;

    // Layer 3: fine ripples scrolling south (~2-3 m, fades at range)
    float camDist = length(wp - u_camera_pos);
    float fine = 1.0 - smoothstep(100.0, 500.0, camDist);
    vec2 uv3 = wp.xy * 0.35 + vec2(t * 0.15, -t * 0.50);
    px += (vnoise(uv3 + vec2(e, 0.0)) - vnoise(uv3 - vec2(e, 0.0))) * 0.22 * fine;
    py += (vnoise(uv3 + vec2(0.0, e)) - vnoise(uv3 - vec2(0.0, e))) * 0.22 * fine;

    return normalize(baseN + vec3(px, py, 0.0));
}

// ---------------------------------------------------------------------------
// Seafloor map sampling.  Uncovered ground (window not ready / beyond
// its edge) reads u_water_z + u_uncovered_dz — deep open water for an
// ocean-horizon game, dry land for a windowed coastal game.
// ---------------------------------------------------------------------------
float floorHeight(vec2 xy) {
    vec2 uv = (xy - u_sf_origin_size.xy) / max(u_sf_origin_size.z, 1.0);
    float h = texture(u_seafloor, clamp(uv, 0.0, 1.0)).r;
    bool covered = u_sf_origin_size.z > 0.0 && uv == clamp(uv, 0.0, 1.0);
    return covered ? h : u_water_z + u_uncovered_dz;
}

// ---------------------------------------------------------------------------
void main() {
    vec3 V = normalize(u_camera_pos - v_worldPos);
    vec3 L = normalize(u_sun_dir_world);
    float dist = length(v_worldPos - u_camera_pos);
    float t = u_time;

    vec3 N = waterNormal(v_waveNormal, v_worldPos, t);

    // ---- Depth below the sea PLANE (stable — not the wavy surface, so
    // the shore colour bands don't shimmer with the swells) ----
    float depth = max(u_water_z - floorHeight(v_worldPos.xy), 0.0);

    // ---- Water body colour, lit by sun + sky ambient ----
    // Beer-Lambert per channel: transmit = how much of the shallow
    // scatter tint survives the water column.  Red extinct first, so the
    // hue walks turquoise -> blue-green -> navy as depth grows.  The
    // body term is scaled by scene light so night water goes dark
    // instead of glowing (HDR pipeline — nothing is emissive here).
    vec3 bodyLight = u_sun_color * (0.25 + 0.75 * max(L.z, 0.0))
                     + u_sky_zenith * 0.8;
    vec3 transmit = exp(-u_absorb * depth);
    vec3 waterCol = mix(u_deep_color, u_shallow_color, transmit) * bodyLight;
    // Sunlit in-scatter band: peaks mid-shallow (~10 m), the "lit
    // swimming pool over sand" glow.
    waterCol += u_shallow_color * u_sun_color
                * (0.30 * max(L.z, 0.0)) * transmit.g * (1.0 - transmit.g);

    // ---- Fresnel (Schlick, power 5) — restrained on purpose ----
    // (WATER_SYSTEM.md V4/V5: at physical grazing reflectance the body
    // colour disappears under the sky reflection.)
    float NdV = max(dot(N, V), 0.0);
    float fresnel = pow(1.0 - NdV, 5.0);
    fresnel = clamp(fresnel * 0.45 + 0.03, 0.0, 1.0);

    // ---- Sky reflection: the scene's actual sky, per-frame ----
    vec3 R = reflect(-V, N);
    float skyH = clamp(R.z * 0.5 + 0.5, 0.0, 1.0);
    // Horizon endpoint damped: a bright haze sky at full strength turns
    // the whole surface milk — 0.75 keeps the body colour in the mix.
    vec3 skyRef = mix(u_sky_horizon * 0.75, u_sky_zenith, skyH);
    // Sun disc in the reflection (only at the exact mirror angle)
    float sunRef = pow(max(dot(R, L), 0.0), 1024.0);
    skyRef += u_sun_color * sunRef * 1.5;

    vec3 color = mix(waterCol, skyRef, fresnel);

    // ---- Subsurface scattering: glow on sun-facing slopes, in the
    // water's own shallow colour, boosted on backlit swell crests ----
    float NdL = max(dot(N, L), 0.0);
    float sss = pow(max(dot(V, -L + N * 0.35), 0.0), 3.0) * 0.25;
    float crestH = clamp((v_worldPos.z - u_water_z) * 0.6, 0.0, 1.5);
    color += u_shallow_color * 0.5 * (NdL * 0.25 + sss)
             * (1.0 + crestH) * u_sun_color;

    // ---- Specular sun path (distance-faded tight terms) ----
    vec3 H = normalize(L + V);
    float NdH = max(dot(N, H), 0.0);
    float specFade = 1.0 - smoothstep(100.0, 800.0, dist);
    color += u_sun_color * pow(NdH, 128.0) * 0.25;
    color += u_sun_color * pow(NdH, 512.0) * 0.6 * specFade;
    vec2 spUV = v_worldPos.xy * 0.30 + vec2(t * 0.5, -t * 0.35);
    float spx = vnoise(spUV + vec2(0.5, 0.0)) - vnoise(spUV - vec2(0.5, 0.0));
    float spy = vnoise(spUV + vec2(0.0, 0.5)) - vnoise(spUV - vec2(0.0, 0.5));
    vec3 N2 = normalize(v_waveNormal + vec3(spx * 0.5, spy * 0.5, 0.0));
    float sparkle = pow(max(dot(N2, H), 0.0), 400.0);
    color += u_sun_color * sparkle * 0.5 * specFade;

    // ---- Foam ------------------------------------------------------
    // Whitecaps: the crest pinch decides ELIGIBILITY only — two layers
    // of non-periodic noise decide PLACEMENT.  The maxima of three sine
    // swells form a periodic lattice, and gating foam on v_crest alone
    // prints that grid across every aerial view (WATER_SYSTEM.md lesson
    // #3 sneaking back in through the foam).
    float capN = vnoise2(v_worldPos.xy * 0.05 + t * vec2(0.05, 0.03));
    float patch = smoothstep(u_whitecap.y, u_whitecap.z,
        vnoise2(v_worldPos.xy * u_whitecap.x + t * vec2(0.010, -0.006)));
    float foam = u_whitecap.w * smoothstep(0.10, 0.35, v_crest)
                 * patch * smoothstep(u_capgate.x, u_capgate.y, capN);

    // Shore foam is a WAVE-SCALE effect: from the air it degenerates
    // into white paint smears along every coast, so it fades out
    // between 30 and 120 m of camera altitude over the water.
    // Whitecaps stay — a real ocean shows those from altitude.
    float camAlt = u_camera_pos.z - u_water_z;
    float shoreVis = 1.0 - smoothstep(30.0, 120.0, camAlt);

    if (depth < 14.0 && shoreVis > 0.001) {
        // Shore zone.  World-space seafloor slope gates every shore
        // effect: sloping ground = a real shoreline nearby, flat shallow
        // basin = no foam (resolution-independent).
        vec2 e = vec2(6.0, 0.0);
        float slope = length(vec2(
            floorHeight(v_worldPos.xy + e.xy) - floorHeight(v_worldPos.xy - e.xy),
            floorHeight(v_worldPos.xy + e.yx) - floorHeight(v_worldPos.xy - e.yx)
        )) / 12.0;
        float shoreGate = smoothstep(0.004, 0.02, slope);

        // Contact line: the thin animated white edge where water meets
        // the sand.  Kept TIGHT (outer edge 0.4 m of depth): on gentle
        // lagoon slopes a wider band reads as a solid white outline
        // from the air.
        float contactN = vnoise2(v_worldPos.xy * 0.35 + t * vec2(0.15, 0.10));
        foam += shoreVis * shoreGate * smoothstep(0.40, 0.08, depth)
                * smoothstep(0.35, 0.70, contactN);

        // Marching bands: two interleaved sets of foam lines riding
        // iso-depth contours shoreward; a large-scale noise warp keeps
        // them from being surveyor-perfect depth contours.  The warp
        // amplitude (+-3 m) deliberately EXCEEDS half the band period
        // so aerial views never read evenly spaced topo rings.
        // MARCH DIRECTION: fract(depth*k + t*speed) — a band at constant
        // phase needs depth to DECREASE as t grows, i.e. it travels
        // toward the shore.
        float dwarp = depth
            + (vnoise2(v_worldPos.xy * 0.02 + vec2(t * 0.02, 0.0)) - 0.5) * 6.0;
        float ph1 = fract(dwarp * 0.22 + t * 0.09);
        float band = 0.9 * smoothstep(0.68, 0.84, ph1)
                     * smoothstep(0.98, 0.88, ph1);
        float ph2 = fract(dwarp * 0.11 + t * 0.05 + 0.37);
        band += 0.5 * smoothstep(0.70, 0.86, ph2)
                * smoothstep(0.98, 0.90, ph2);
        // Confined to the 0-10 m depth band; dissolves at the waterline
        // (contact foam takes over).  The along-shore gate is SPARSE
        // (~30% coverage): distinct rolling lines, not foam soup.
        band *= smoothstep(10.0, 3.5, depth) * smoothstep(0.10, 0.90, depth);
        band *= smoothstep(0.45, 0.85,
                           vnoise2(v_worldPos.xy * 0.06 + t * vec2(0.05, 0.03)));
        foam += band * shoreGate * shoreVis;
    }
    // Foam detail is invisible (and the bands would alias) at range.
    foam = clamp(foam * u_foam_gain, 0.0, 1.0)
           * (1.0 - smoothstep(700.0, 1600.0, dist));

    // Foam is rough white — diffuse-lit by sun + sky, never specular
    // (the mix pulls the sun path out from under it).
    vec3 foamLight = u_sun_color * (0.30 + 0.70 * max(L.z, 0.0))
                     + (u_sky_horizon + u_sky_zenith) * 0.5;
    color = mix(color, vec3(0.85) * foamLight, foam);

    // ---- Distance haze: the engine's analytic aerial perspective ----
    // The exact pax_pbr.frag block (exponential-height medium, forward
    // sun lobe), so water and every hazed surface in the scene share one
    // atmosphere.  u_density = 0 -> trans = 1 -> exact no-op.
    vec3 ray = v_worldPos - u_camera_pos;
    float atmo_a = (u_camera_pos.z - u_base_h) * u_inv_scale_h;
    float atmo_u = (v_worldPos.z - u_camera_pos.z) * u_inv_scale_h;
    float falloff = (abs(atmo_u) > 1e-4)
        ? (1.0 - exp(-clamp(atmo_u, -30.0, 30.0))) / atmo_u : 1.0;
    float tau = u_density * dist * exp(-clamp(atmo_a, -30.0, 30.0)) * falloff;
    float trans = exp(-clamp(tau, 0.0, 60.0));
    float mu = (dist > 1e-6)
        ? clamp(dot(ray / dist, L), 0.0, 1.0) : 0.0;
    vec3 insc = mix(u_haze_color, u_sun_haze_color, pow(mu, u_sun_power));
    color = color * trans + insc * (1.0 - trans);

    // ---- Alpha: the shore melt ----
    // Clear at depth 0 (the lit sand IS the shallows' colour), opaque by
    // ~10 m.  Fresnel keeps grazing water reflective, foam sits ON the
    // surface, hazed-out water is always solid — but the melt trumps all
    // of them: every contribution fades out over the last half-metre of
    // depth, or a grazing view paints the reflection sheet right up to
    // the z-cut and the waterline is a hard edge again.
    float alpha = 1.0 - exp(-depth * u_alpha_k);
    alpha = mix(alpha, 0.98, fresnel);
    alpha = max(alpha, foam * 0.92);
    alpha = mix(alpha, 1.0, 1.0 - trans);
    alpha *= smoothstep(0.02, 0.50, depth);
    alpha *= v_edge;

    o_color = vec4(max(color, vec3(0.0)), alpha);
}
