package io.github.chungus_actual.coldweenie

import android.content.Context
import android.graphics.SurfaceTexture
import android.media.MediaPlayer
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.view.Surface
import java.nio.ByteBuffer
import java.nio.ByteOrder
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10

/**
 * The TV: attract videos through a tube shader, static between channels.
 * Tegra notes carried over from Nightdrop: everything highp (mediump is fp16), small numbers in the
 * noise, and draw from a real vertex buffer.
 */
class Crt(context: Context) : GLSurfaceView(context), GLSurfaceView.Renderer {
    /** The glass, as x,y pairs TL TR BR BL in this surface's own pixels. Set before the first frame. */
    var quad = floatArrayOf(0f, 0f, 1f, 0f, 1f, 1f, 0f, 1f)
    /** What the picture is throwing onto the room right now, 0..1 per channel. */
    @Volatile var glowR = .3f
    @Volatile var glowG = .3f
    @Volatile var glowB = .3f
    private var frames = 0
    private val px = ByteBuffer.allocateDirect(4).order(ByteOrder.nativeOrder())

    private val thread = HandlerThread("crt-player").apply { start() }
    private val worker = Handler(thread.looper)
    private var player: MediaPlayer? = null
    private var surface: Surface? = null
    private var texture: SurfaceTexture? = null
    private var wanted: Pair<String, Int>? = null

    @Volatile var muted = false
    @Volatile private var hasPicture = false
    @Volatile private var frameReady = false
    /** 1 is full snow, 0 is a clean picture. */
    @Volatile private var snow = 1f
    @Volatile private var snowTarget = .55f
    private val texMatrix = FloatArray(16)

    private var program = 0
    private var uT = 0
    private var uSnow = 0
    private var uPicture = 0
    private var uTex = 0
    private var uRes = 0
    private var oes = 0
    private var w = 640
    private var h = 480
    private val start = SystemClock.uptimeMillis()

    init {
        setEGLContextClientVersion(2)
        setRenderer(this)
        renderMode = RENDERMODE_CONTINUOUSLY
    }

    /** Change the channel: snow now, the video when it is ready. Null leaves it on snow. */
    fun tune(path: String?, seekFrac: Float = 0f) {
        snow = 1f
        snowTarget = if (path == null) .42f else 1f
        hasPicture = false
        val seek = (seekFrac * 1000).toInt()
        worker.removeCallbacksAndMessages(null)
        wanted = path?.let { it to seek }
        worker.post { open() }
    }

    fun burst() {
        snow = 1f
    }

    fun off() {
        worker.removeCallbacksAndMessages(null)
        wanted = null
        worker.post { close() }
    }

    fun setMute(m: Boolean) {
        muted = m
        worker.post { player?.setVolume(vol(), vol()) }
    }

    private fun vol() = if (muted) 0f else .36f

    private fun close() {
        player?.let { p -> runCatching { p.stop() }; runCatching { p.release() } }
        player = null
    }

    private fun open() {
        close()
        val (path, seek) = wanted ?: return
        val s = surface ?: return
        val p = MediaPlayer()
        runCatching {
            p.setSurface(s)
            p.setDataSource(path)
            p.isLooping = true
            p.setVolume(vol(), vol())
            p.setOnPreparedListener { mp ->
                if (seek > 0) mp.seekTo((mp.duration * (seek / 1000f)).toInt())
                mp.start()
            }
            p.setOnInfoListener { _, what, _ ->
                if (what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) {
                    hasPicture = true
                    snowTarget = 0f
                }
                false
            }
            p.setOnErrorListener { _, _, _ ->
                hasPicture = false
                snowTarget = .42f
                true
            }
            p.prepareAsync()
            player = p
        }.onFailure {
            runCatching { p.release() }
            snowTarget = .42f
        }
    }

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        program = link(VERT, FRAG)
        val ids = IntArray(1)
        GLES20.glGenTextures(1, ids, 0)
        oes = ids[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, oes)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)
        val st = SurfaceTexture(oes)
        st.setOnFrameAvailableListener { frameReady = true }
        texture?.release()
        texture = st
        val s = Surface(st)
        surface?.release()
        surface = s
        android.opengl.Matrix.setIdentityM(texMatrix, 0)

        GLES20.glUseProgram(program)
        uT = GLES20.glGetUniformLocation(program, "uT")
        uSnow = GLES20.glGetUniformLocation(program, "uSnow")
        uPicture = GLES20.glGetUniformLocation(program, "uPicture")
        uTex = GLES20.glGetUniformLocation(program, "uTex")
        uRes = GLES20.glGetUniformLocation(program, "uRes")
        worker.post { if (wanted != null) open() }
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        w = width
        h = height
        GLES20.glViewport(0, 0, width, height)
        uploadQuad()
    }

    /** Perspective-correct uvs for a four-cornered screen: q from where the diagonals cross. */
    private fun uploadQuad() {
        val q = quad
        fun gx(x: Float) = x / w * 2f - 1f
        fun gy(y: Float) = 1f - y / h * 2f
        val x0 = gx(q[0]); val y0 = gy(q[1]); val x1 = gx(q[2]); val y1 = gy(q[3])
        val x2 = gx(q[4]); val y2 = gy(q[5]); val x3 = gx(q[6]); val y3 = gy(q[7])
        val den = (x2 - x0) * (y3 - y1) - (y2 - y0) * (x3 - x1)
        val t = ((x1 - x0) * (y3 - y1) - (y1 - y0) * (x3 - x1)) / den
        val cx = x0 + t * (x2 - x0)
        val cy = y0 + t * (y2 - y0)
        fun dist(ax: Float, ay: Float) = Math.hypot((ax - cx).toDouble(), (ay - cy).toDouble()).toFloat()
        val d = floatArrayOf(dist(x0, y0), dist(x1, y1), dist(x2, y2), dist(x3, y3))
        val qs = FloatArray(4) { (d[it] + d[(it + 2) % 4]) / d[(it + 2) % 4] }
        val us = floatArrayOf(0f, 1f, 1f, 0f)
        val vs = floatArrayOf(1f, 1f, 0f, 0f)
        val xs = floatArrayOf(x0, x1, x2, x3)
        val ys = floatArrayOf(y0, y1, y2, y3)
        val data = FloatArray(20)
        for (i in 0..3) {
            data[i * 5] = xs[i]
            data[i * 5 + 1] = ys[i]
            data[i * 5 + 2] = us[i] * qs[i]
            data[i * 5 + 3] = vs[i] * qs[i]
            data[i * 5 + 4] = qs[i]
        }
        val ids = IntArray(1)
        GLES20.glGenBuffers(1, ids, 0)
        GLES20.glBindBuffer(GLES20.GL_ARRAY_BUFFER, ids[0])
        val bb = ByteBuffer.allocateDirect(data.size * 4).order(ByteOrder.nativeOrder())
        bb.asFloatBuffer().put(data)
        GLES20.glBufferData(GLES20.GL_ARRAY_BUFFER, data.size * 4, bb, GLES20.GL_STATIC_DRAW)
        GLES20.glUseProgram(program)
        val aPos = GLES20.glGetAttribLocation(program, "aPos")
        val aUv = GLES20.glGetAttribLocation(program, "aUvq")
        GLES20.glEnableVertexAttribArray(aPos)
        GLES20.glVertexAttribPointer(aPos, 2, GLES20.GL_FLOAT, false, 20, 0)
        GLES20.glEnableVertexAttribArray(aUv)
        GLES20.glVertexAttribPointer(aUv, 3, GLES20.GL_FLOAT, false, 20, 8)
    }

    override fun onDrawFrame(gl: GL10?) {
        if (frameReady) {
            frameReady = false
            texture?.updateTexImage()
            texture?.getTransformMatrix(texMatrix)
        }
        snow += (snowTarget - snow) * .22f
        val t = ((SystemClock.uptimeMillis() - start) % 100000L) / 1000f
        GLES20.glUseProgram(program)
        GLES20.glUniform1f(uT, t)
        GLES20.glUniform1f(uSnow, snow)
        GLES20.glUniform1f(uPicture, if (hasPicture) 1f else 0f)
        GLES20.glUniformMatrix4fv(uTex, 1, false, texMatrix, 0)
        GLES20.glUniform2f(uRes, w.toFloat(), h.toFloat())
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_FAN, 0, 4)
        if (++frames % 6 == 0) sampleGlow()
    }

    /** A handful of pixels from the middle of the tube: enough to tell what colour the room should be. */
    private fun sampleGlow() {
        var r = 0
        var g = 0
        var b = 0
        for (i in 0..4) {
            val x = w * (2 + i * 3) / 16
            val y = h * (3 + (i * 7) % 5) / 8
            px.position(0)
            GLES20.glReadPixels(x, y, 1, 1, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, px)
            r += px.get(0).toInt() and 255
            g += px.get(1).toInt() and 255
            b += px.get(2).toInt() and 255
        }
        val k = 1f / (5 * 255f)
        glowR += (r * k - glowR) * .25f
        glowG += (g * k - glowG) * .25f
        glowB += (b * k - glowB) * .25f
    }

    private fun link(v: String, f: String): Int {
        fun compile(type: Int, src: String): Int {
            val s = GLES20.glCreateShader(type)
            GLES20.glShaderSource(s, src)
            GLES20.glCompileShader(s)
            val ok = IntArray(1)
            GLES20.glGetShaderiv(s, GLES20.GL_COMPILE_STATUS, ok, 0)
            if (ok[0] == 0) android.util.Log.e("ColdWeenie", GLES20.glGetShaderInfoLog(s))
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
attribute vec3 aUvq;
varying highp vec3 vUvq;
void main() { vUvq = aUvq; gl_Position = vec4(aPos, 0.0, 1.0); }
"""
        const val FRAG = """
#extension GL_OES_EGL_image_external : require
precision highp float;
varying highp vec3 vUvq;
uniform samplerExternalOES uVideo;
uniform mat4 uTex;
uniform float uT;
uniform float uSnow;
uniform float uPicture;
uniform vec2 uRes;
float hash(vec2 p) {
    p = fract(p * vec2(0.1031, 0.1030));
    p += dot(p, p.yx + 33.33);
    return fract((p.x + p.y) * p.x);
}
void main() {
    vec2 c = vUvq.xy / vUvq.z * 2.0 - 1.0;
    c *= 1.0 + dot(c.yx, c.yx) * vec2(0.035, 0.05);
    vec2 uv = c * 0.5 + 0.5;
    vec2 edge = smoothstep(vec2(0.0), vec2(0.012), uv) * smoothstep(vec2(0.0), vec2(0.012), 1.0 - uv);
    float inside = edge.x * edge.y;

    vec2 tc = (uTex * vec4(uv, 0.0, 1.0)).xy;
    float jitter = uSnow * (hash(vec2(floor(uv.y * 120.0), floor(uT * 30.0))) - 0.5) * 0.04;
    vec3 col = texture2D(uVideo, tc + vec2(jitter, 0.0)).rgb * uPicture;

    // lift the blacks and warm it up like a phosphor, then scanlines and an aperture grille
    col = pow(col, vec3(0.92)) * 1.08;
    float scan = 0.80 + 0.20 * sin(uv.y * 240.0 * 6.28318);
    float mask = 0.93 + 0.07 * sin(gl_FragCoord.x * 2.0944);
    col *= scan * mask;

    vec2 cell = floor(gl_FragCoord.xy / 2.0);
    float grain = hash(cell + vec2(fract(uT * 7.13) * 417.0, fract(uT * 3.71) * 253.0));
    float band = smoothstep(0.82, 1.0, sin(uv.y * 5.0 + uT * 3.3));
    vec3 snow = vec3(grain * (0.78 + band * 0.22));
    col = mix(col, snow, clamp(uSnow, 0.0, 1.0));

    vec2 v = uv * (1.0 - uv);
    float vig = pow(clamp(v.x * v.y * 16.0, 0.0, 1.0), 0.28);
    col *= vig;
    gl_FragColor = vec4(col * inside, 1.0);
}
"""
    }
}
