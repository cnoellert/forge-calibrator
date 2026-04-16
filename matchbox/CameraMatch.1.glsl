// CameraMatch — Matchbox Shader for Flame
//
// 2-vanishing-point camera solve from user-drawn line pairs.
// Drag the Axis widgets onto perspective edges in the viewport.
//
// Computed camera values (position, rotation, FOV) are encoded in
// the bottom-left pixels of the output for expression linking.
//
// Reference: Guillou et al., "Using Vanishing Points for Camera
// Calibration and Coarse 3D Reconstruction from a Single Image"

uniform sampler2D front;
uniform float adsk_result_w, adsk_result_h;

// VP1 control points (line pair 1)
uniform vec2 vp1_l1_start;
uniform vec2 vp1_l1_end;
uniform vec2 vp1_l2_start;
uniform vec2 vp1_l2_end;

// VP2 control points (line pair 2)
uniform vec2 vp2_l1_start;
uniform vec2 vp2_l1_end;
uniform vec2 vp2_l2_start;
uniform vec2 vp2_l2_end;

// Axis assignment: 0=+X, 1=-X, 2=+Y, 3=-Y, 4=+Z, 5=-Z
uniform int vp1_axis;
uniform int vp2_axis;

// Display controls
uniform float image_opacity;
uniform float line_width;
uniform float line_opacity;
uniform bool show_vp_markers;
uniform bool show_extended;
uniform bool show_info;
uniform vec3 vp1_color;
uniform vec3 vp2_color;

// Origin
uniform vec2 origin_pt;
uniform bool use_origin;

// Solved camera output values (written by Python companion, linkable in animation editor)
uniform float out_pos_x;
uniform float out_pos_y;
uniform float out_pos_z;
uniform float out_rot_x;
uniform float out_rot_y;
uniform float out_rot_z;
uniform float out_focal_mm;
uniform float out_hfov;
uniform float out_vfov;

// =========================================================================
// Math
// =========================================================================

vec2 px_to_ip(vec2 px) {
    float a = adsk_result_w / adsk_result_h;
    float rx = px.x / adsk_result_w;
    float ry = px.y / adsk_result_h;
    if (a >= 1.0) return vec2(-1.0 + 2.0 * rx, (2.0 * ry - 1.0) / a);
    else          return vec2((-1.0 + 2.0 * rx) * a, 2.0 * ry - 1.0);
}

vec2 ip_to_px(vec2 ip) {
    float a = adsk_result_w / adsk_result_h;
    if (a >= 1.0) return vec2((ip.x + 1.0) * 0.5 * adsk_result_w,
                              (ip.y * a + 1.0) * 0.5 * adsk_result_h);
    else          return vec2((ip.x / a + 1.0) * 0.5 * adsk_result_w,
                              (ip.y + 1.0) * 0.5 * adsk_result_h);
}

vec2 p2px(vec2 p) { return vec2(p.x * adsk_result_w, p.y * adsk_result_h); }

vec3 line_isect(vec2 p1, vec2 p2, vec2 p3, vec2 p4) {
    float d = (p1.x-p2.x)*(p3.y-p4.y) - (p1.y-p2.y)*(p3.x-p4.x);
    if (abs(d) < 1e-10) return vec3(0.0);
    float t = ((p1.x-p3.x)*(p3.y-p4.y) - (p1.y-p3.y)*(p3.x-p4.x)) / d;
    return vec3(p1 + t*(p2-p1), 1.0);
}

vec2 ortho_proj(vec2 pt, vec2 a, vec2 b) {
    vec2 d = b - a;
    float s = dot(d, d);
    if (s < 1e-20) return a;
    return a + (dot(pt - a, d) / s) * d;
}

float compute_focal(vec2 v1, vec2 v2, vec2 pp) {
    vec2 puv = ortho_proj(pp, v1, v2);
    float fsq = length(v2-puv) * length(v1-puv) - length(pp-puv) * length(pp-puv);
    return (fsq > 0.0) ? sqrt(fsq) : -1.0;
}

mat3 compute_rotation(vec2 v1, vec2 v2, float f, vec2 pp) {
    vec3 u = normalize(vec3(v1 - pp, -f));
    vec3 v = normalize(vec3(v2 - pp, -f));
    vec3 w = normalize(cross(u, v));
    return mat3(u, v, w);
}

mat3 axis_assign(int a1, int a2) {
    vec3 ax[6];
    ax[0]=vec3(1,0,0); ax[1]=vec3(-1,0,0);
    ax[2]=vec3(0,1,0); ax[3]=vec3(0,-1,0);
    ax[4]=vec3(0,0,1); ax[5]=vec3(0,0,-1);
    vec3 r1=ax[a1], r2=ax[a2], r3=cross(r1,r2);
    return mat3(vec3(r1.x,r2.x,r3.x), vec3(r1.y,r2.y,r3.y), vec3(r1.z,r2.z,r3.z));
}

vec3 mat_to_euler(mat3 R) {
    float cy = sqrt(R[0][0]*R[0][0] + R[0][1]*R[0][1]);
    float rx, ry, rz;
    if (cy > 1e-6) { rx=atan(R[1][2],R[2][2]); ry=atan(-R[0][2],cy); rz=atan(R[0][1],R[0][0]); }
    else           { rx=atan(-R[2][1],R[1][1]); ry=atan(-R[0][2],cy); rz=0.0; }
    return degrees(vec3(rx, ry, rz));
}

// =========================================================================
// Drawing
// =========================================================================

float sdf_seg(vec2 p, vec2 a, vec2 b) {
    vec2 pa=p-a, ba=b-a;
    return length(pa - ba*clamp(dot(pa,ba)/dot(ba,ba), 0.0, 1.0));
}

float sdf_line(vec2 p, vec2 a, vec2 b) {
    vec2 ba=b-a; float l=length(ba);
    if (l < 1e-10) return length(p-a);
    return abs(dot(p-a, vec2(-ba.y,ba.x)/l));
}

float draw_seg(vec2 p, vec2 a, vec2 b, float w) {
    return 1.0 - smoothstep(w*0.5-1.0, w*0.5+1.0, sdf_seg(p,a,b));
}

float draw_ext(vec2 p, vec2 a, vec2 b, float w) {
    float d = sdf_line(p,a,b);
    float lv = 1.0 - smoothstep(w*0.25-0.5, w*0.25+0.5, d);
    float dash = step(0.5, fract(dot(p-a, normalize(b-a))/30.0));
    return lv * dash;
}

float draw_circ(vec2 p, vec2 c, float r) {
    return 1.0 - smoothstep(r-1.5, r+1.5, length(p-c));
}

float draw_cross(vec2 p, vec2 c, float s, float w) {
    return max(draw_seg(p, c-vec2(s,0), c+vec2(s,0), w),
               draw_seg(p, c-vec2(0,s), c+vec2(0,s), w));
}

// =========================================================================
// Main
// =========================================================================

void main() {
    vec2 uv = gl_FragCoord.xy / vec2(adsk_result_w, adsk_result_h);
    vec2 px = gl_FragCoord.xy;
    vec4 src = texture2D(front, uv);

    // Control points → pixel space
    vec2 a1s = p2px(vp1_l1_start), a1e = p2px(vp1_l1_end);
    vec2 a2s = p2px(vp1_l2_start), a2e = p2px(vp1_l2_end);
    vec2 b1s = p2px(vp2_l1_start), b1e = p2px(vp2_l1_end);
    vec2 b2s = p2px(vp2_l2_start), b2e = p2px(vp2_l2_end);

    // Compute VPs in ImagePlane
    vec3 vp1r = line_isect(px_to_ip(a1s), px_to_ip(a1e), px_to_ip(a2s), px_to_ip(a2e));
    vec3 vp2r = line_isect(px_to_ip(b1s), px_to_ip(b1e), px_to_ip(b2s), px_to_ip(b2e));
    vec2 pp = vec2(0.0);

    // Solve
    float focal = -1.0;
    vec3 cam_pos = vec3(0.0), cam_rot = vec3(0.0);
    float hfov_deg = 0.0, vfov_deg = 0.0;
    bool valid = false;

    if (vp1r.z > 0.5 && vp2r.z > 0.5) {
        focal = compute_focal(vp1r.xy, vp2r.xy, pp);
        if (focal > 0.0) {
            valid = true;
            float asp = adsk_result_w / adsk_result_h;
            float hfov = 2.0 * atan(1.0/focal);
            float vfov = 2.0 * atan(tan(hfov*0.5)/asp);
            hfov_deg = degrees(hfov);
            vfov_deg = degrees(vfov);

            mat3 R = compute_rotation(vp1r.xy, vp2r.xy, focal, pp);
            mat3 A = axis_assign(vp1_axis, vp2_axis);
            mat3 vr = R * A;
            mat3 cr = transpose(vr);
            cam_rot = mat_to_euler(cr);

            if (use_origin) {
                vec2 oip = px_to_ip(p2px(origin_pt));
                float hw = tan(hfov*0.5);
                vec3 ray;
                if (asp >= 1.0) ray = vec3(oip*hw, -1.0);
                else { float hh=hw/asp; ray = vec3(oip.x*hh*asp, oip.y*hh, -1.0); }
                cam_pos = -10.0 * (cr * normalize(ray));
            }
        }
    }

    // Draw overlay — dim source image (like fSpy opacity slider)
    vec3 col = src.rgb * image_opacity;

    // VP1 segments
    float l1 = max(draw_seg(px,a1s,a1e,line_width), draw_seg(px,a2s,a2e,line_width));
    // VP2 segments
    float l2 = max(draw_seg(px,b1s,b1e,line_width), draw_seg(px,b2s,b2e,line_width));
    col = mix(col, vp1_color, l1 * line_opacity);
    col = mix(col, vp2_color, l2 * line_opacity);

    // Extended lines
    if (show_extended) {
        float e1 = max(draw_ext(px,a1s,a1e,line_width), draw_ext(px,a2s,a2e,line_width));
        float e2 = max(draw_ext(px,b1s,b1e,line_width), draw_ext(px,b2s,b2e,line_width));
        col = mix(col, vp1_color, e1*line_opacity*0.3);
        col = mix(col, vp2_color, e2*line_opacity*0.3);
    }

    // VP markers
    if (show_vp_markers) {
        if (vp1r.z > 0.5) col = mix(col, vec3(1.0), draw_cross(px, ip_to_px(vp1r.xy), 15.0, line_width) * line_opacity);
        if (vp2r.z > 0.5) col = mix(col, vec3(1.0), draw_cross(px, ip_to_px(vp2r.xy), 15.0, line_width) * line_opacity);
    }

    // Origin marker
    if (use_origin) col = mix(col, vec3(1,1,0), draw_circ(px, p2px(origin_pt), 8.0) * line_opacity);

    // Status indicator
    if (show_info) {
        vec3 ic = valid ? vec3(0,1,0) : vec3(1,0,0);
        col = mix(col, ic, draw_circ(px, vec2(30.0, adsk_result_h-30.0), 10.0) * 0.8);
    }

    // Encode camera data in bottom-left pixels
    vec4 out_col = vec4(col, src.a);
    if (valid && px.y < 1.5 && px.x < 5.5) {
        int i = int(px.x);
        if      (i==0) out_col = vec4(cam_pos, 1.0);
        else if (i==1) out_col = vec4(cam_rot, 1.0);
        else if (i==2) out_col = vec4(focal, hfov_deg, vfov_deg, 1.0);
        else if (i==3) out_col = vec4(vp1r.xy, vp1r.z, 1.0);
        else if (i==4) out_col = vec4(vp2r.xy, vp2r.z, 1.0);
    }

    gl_FragColor = out_col;
}
