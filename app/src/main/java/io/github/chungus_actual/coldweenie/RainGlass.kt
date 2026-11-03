package io.github.chungus_actual.coldweenie

import android.content.Context
import android.graphics.BitmapFactory
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.opengl.GLUtils
import android.os.SystemClock
import java.nio.ByteBuffer
import java.nio.ByteOrder
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/**
 * The window pane: the rendered street seen through wet glass. Beads and running drops bend the view
 * for real and trails clear the fog behind them. It sits
 * behind Room, which cuts a hole exactly where the glass shows, so the sofa and curtains stay in front.
 */
class RainGlass(context: Context) : GLSurfaceView(context), GLSurfaceView.Renderer {
    private var program = 0
    private var uT = 0
    private var uAspect = 0
    private val start = SystemClock.uptimeMillis()

    init {
        setEGLContextClientVersion(2)
        setRenderer(this)
        renderMode = RENDERMODE_CONTINUOUSLY
    }

    private fun texture(unit: Int, asset: String) {
        val ids = IntArray(1)
        GLES20.glGenTextures(1, ids, 0)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0 + unit)
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, ids[0])
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)
        val b = context.assets.open(asset).use { BitmapFactory.decodeStream(it) }
        GLUtils.texImage2D(GLES20.GL_TEXTURE_2D, 0, b, 0)
        b.recycle()
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        program = link(VERT, FRAG)
        GLES20.glUseProgram(program)
        texture(0, "scenes/${Geo.name}/plate.jpg")
        texture(1, "scenes/${Geo.name}/platefog.jpg")
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program, "uSharp"), 0)
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program, "uFog"), 1)
        uT = GLES20.glGetUniformLocation(program, "uT")
        uAspect = GLES20.glGetUniformLocation(program, "uAspect")
        val data = floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f)
        val ids = IntArray(1)
        GLES20.glGenBuffers(1, ids, 0)
        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, ids[0])
        val bb = ByteBuffer.allocateDirect(data.size * 4).order(ByteOrder.nativeOrder())
        bb.asFloatBuffer().put(data)
        GLES20.glBufferData(GLES20.GL_ARRAY_BUFFER, data.size * 4, bb, GLES20.GL_STATIC_DRAW)
        val aPos = GLES20.glGetAttribLocation(program, "aPos")
        GLES20.glEnableVertexAttribArray(aPos)
        GLES20.glVertexAttribPointer(aPos, 2, GLES20.GL_FLOAT, false, 8, 0)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
        GLES20.glUniform1f(uAspect, width.toFloat() / height)
    }

    override fun onDrawFrame(gl: GL10?) {
        val t = ((SystemClock.uptimeMillis() - start) % 400000L) / 1000f
        GLES20.glUniform1f(uT, t)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
    }

    private fun link(v: String, f: String): Int {
        fun compile(type: Int, src: String): Int {
            val s = GLES20.glCreateShader(type)
            GLES20.glShaderSource(s, src)
            GLES20.glCompileShader(s)
            val ok = IntArray(1)
            GLES20.glGetShaderiv(s, GLES20.GL_COMPILE_STATUS, ok, 0)
            if (ok[0] == 0) android.util.Log.e("Basement", GLES20.glGetShaderInfoLog(s))
            return s
        }
        val p = GLES20.glCreateProgram()
        GLES20.glAttachShader(p, compile(GLES20.GL_VERTEX_SHADER, v))
        GLES20.glAttachShader(p, compile(GLES20.GL_FRAGMENT_SHADER, f))
        GLES20.glLinkProgram(p)
        return p
    }

    private companion object {
        const val VERT = """
attribute vec2 aPos;
varying highp vec2 vUv;
void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }
"""
        const val FRAG = """
precision highp float;
varying highp vec2 vUv;
uniform sampler2D uSharp;
uniform sampler2D uFog;
uniform float uT;
uniform float uAspect;
float h1(vec2 p) {
    p = fract(p * vec2(0.1031, 0.1030));
    p += dot(p, p.yx + 33.33);
    return fract((p.x + p.y) * p.x);
}
vec3 h3(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    q += dot(q, q.yxz + 33.33);
    return fract((q.xxy + q.yzz) * q.zyx);
}

// running drops, in a space where one unit is the pane's height. x = height of the water, y = glass cleared
vec2 runs(vec2 uv, float t, vec2 grid, float seed) {
    vec2 st = uv * grid;
    float col = floor(st.x);
    st.y += t * (0.10 + 0.14 * h1(vec2(col, seed))) + h1(vec2(seed, col)) * 7.0;
    vec2 id = floor(st);
    vec2 f = fract(st) - 0.5;
    vec3 n = h3(id + seed);
    if (n.z < 0.42) return vec2(0.0);
    float tt = t * (0.55 + n.y * 0.5) + n.x * 6.283;
    // stick, then slip
    float y = -0.33 * sin(tt + sin(tt + sin(tt) * 0.5));
    float x = (n.x - 0.5) * 0.62 + 0.09 * sin(st.y * 6.0 + n.y * 6.283) * sin(st.y * 2.7);
    vec2 d = (f - vec2(x, y)) / grid;
    d.y *= 0.72 + 0.28 * smoothstep(-0.02, 0.02, d.y);
    float r = (0.011 + 0.008 * n.y);
    float main = smoothstep(r, r * 0.25, length(d));
    // a line of smaller drops left behind on the glass, and the clear path they sit in
    float above = smoothstep(y, y + 0.08, f.y) * smoothstep(0.5, y + 0.12, f.y);
    float path = smoothstep(r * 0.95, r * 0.35, abs(d.x)) * above;
    float tp = fract(f.y * 7.0 + n.x * 3.0) - 0.5;
    vec2 td = vec2(d.x, tp / (7.0 * grid.y));
    float trail = smoothstep(r * 0.42, r * 0.1, length(td)) * above * (0.4 + 0.6 * smoothstep(y + 0.5, y, f.y));
    return vec2(max(main, trail), path);
}

// tiny beads that land, sit there and get absorbed. Two densities
float beads(vec2 uv, float t, float g, float seed) {
    vec2 st = uv * g;
    vec2 id = floor(st);
    vec2 f = fract(st) - 0.5;
    vec3 n = h3(id + seed);
    vec2 d = (f - (n.xy - 0.5) * 0.74) / g;
    float life = fract(t * (0.05 + n.z * 0.1) + n.x * 3.7);
    float a = smoothstep(0.0, 0.015, life) * smoothstep(1.0, 0.45, life) * step(0.6, n.z);
    float r = (0.0026 + 0.0036 * n.y);
    return smoothstep(r, r * 0.3, length(d)) * a;
}

vec2 water(vec2 uv, float t) {
    vec2 a = runs(uv, t, vec2(7.0, 1.9), 3.1);
    vec2 b = runs(uv + vec2(0.37, 0.11), t * 0.85, vec2(11.0, 2.8), 9.7);
    float c = beads(uv, t, 34.0, 1.7) + beads(uv + 0.31, t * 1.2, 58.0, 5.3);
    return vec2(clamp(max(max(a.x, b.x), c), 0.0, 1.0), max(a.y, b.y));
}

void main() {
    vec2 uv = vec2(vUv.x * uAspect, vUv.y);
    float t = uT;
    vec2 tuv = vec2(vUv.x, 1.0 - vUv.y);
    vec2 w = water(uv, t);
    float e = 0.0012;
    float wx = water(uv + vec2(e, 0.0), t).x;
    float wy = water(uv + vec2(0.0, e), t).x;
    vec2 n = vec2(wx - w.x, wy - w.x);

    // through a bead the street turns over; through a film it just goes soft
    vec2 bend = vec2(n.x / uAspect, -n.y);
    vec3 fog = texture2D(uFog, tuv + bend * 0.4).rgb;
    vec3 sharp = texture2D(uSharp, tuv + bend * 2.2).rgb;
    vec3 col = mix(fog, sharp, clamp(smoothstep(0.0, 0.35, w.x) + w.y * 0.75, 0.0, 1.0));

    // the dark rim and the little window of sky a drop carries on its upper shoulder
    float slope = length(n);
    col *= 1.0 - 0.26 * smoothstep(0.03, 0.2, slope) * w.x;
    float gl = pow(max(0.0, dot(n / max(slope, 0.0001), vec2(0.45, -0.89))), 6.0) * smoothstep(0.04, 0.18, slope);
    col += vec3(0.9, 0.95, 1.0) * gl * 0.24;
    gl_FragColor = vec4(col, 1.0);
}
"""
    }
}
