package io.github.chungus_actual.coldweenie

import android.content.Context
import android.graphics.Path
import android.graphics.RectF
import org.json.JSONObject

/** Where things are in the rendered room, as Blender projected them (render/scene.py writes room.json). */
object Geo {
    val ROOMS = listOf("neon", "basement", "rain", "grid", "mall")
    var name = "neon"
    /** The tube's corners TL TR BR BL, in 1920x1080. */
    var screen = FloatArray(8)
    /** Lava lamp glass: bottom and top, each x, y, half width. Empty when this room has no lamp. */
    var lampLow = FloatArray(0)
    var lampTop = FloatArray(0)
    /** Where the rainy window's glass shows: x, y, w, h. Empty when this room has none. */
    var glass = FloatArray(0)
    /** Something hot, x, y pairs: where steam starts. */
    var steam = FloatArray(0)
    /** How big it looks from here: a pie across the room, a mug on the table. */
    var steamSize = 1f
    /** A string of little bulbs: x, y pairs. */
    var bulbs = FloatArray(0)
    /** Lights racing across the far floor: colour, seconds per step, x, y points, and whether the camera can see each one. */
    class Runner(val color: Int, val speed: Float, val path: FloatArray, val seen: BooleanArray)
    var runners = emptyList<Runner>()
    /** What crosses far off now and then: a picture, its feet at each step, how tall it stands, and the room in front of its path. */
    class Passer(val sprite: String, val path: FloatArray, val tall: Float, val step: Float, val every: Float, val at: Float, val wall: Int, val nearer: String)
    var passers = emptyList<Passer>()
    /** The crane's claw: x, y of the rail end and the head, at home; rail, head and lowest head over the prizes; pixels per .1 of height. */
    var claw = FloatArray(0)
    /** The prize it goes for, where it lies: x, y, w, h. */
    var topDog = FloatArray(0)
    var ledge = 650f

    fun load(ctx: Context, room: String) {
        name = room
        val j = JSONObject(ctx.assets.open("scenes/$room/room.json").bufferedReader().readText())
        val s = j.getJSONArray("screen")
        screen = FloatArray(8) { i -> s.getJSONArray(i / 2).getDouble(i % 2).toFloat() }
        j.optJSONArray("lamp")?.let { l ->
            lampLow = FloatArray(3) { l.getJSONArray(0).getDouble(it).toFloat() }
            lampTop = FloatArray(3) { l.getJSONArray(1).getDouble(it).toFloat() }
        }
        glass = j.optJSONArray("glass")?.let { g -> FloatArray(4) { g.getDouble(it).toFloat() } } ?: FloatArray(0)
        steamSize = j.optDouble("steam_size", 1.0).toFloat()
        steam = j.optJSONArray("steam")?.let { b -> FloatArray(b.length() * 2) { i -> b.getJSONArray(i / 2).getDouble(i % 2).toFloat() } } ?: FloatArray(0)
        j.optJSONArray("bulbs")?.let { b ->
            bulbs = FloatArray(b.length() * 2) { i -> b.getJSONArray(i / 2).getDouble(i % 2).toFloat() }
        }
        runners = j.optJSONArray("runners")?.let { a ->
            List(a.length()) { i ->
                val o = a.getJSONObject(i)
                val p = o.getJSONArray("p")
                val v = o.getJSONArray("v")
                Runner(o.getLong("c").toInt(), o.getDouble("s").toFloat(), FloatArray(p.length() * 2) { k -> p.getJSONArray(k / 2).getDouble(k % 2).toFloat() }, BooleanArray(v.length()) { v.getBoolean(it) })
            }
        } ?: emptyList()
        claw = j.optJSONObject("claw")?.let { o ->
            val pts = listOf("home_top", "home_rest", "over_top", "over_rest", "over_low").flatMap { n -> o.getJSONArray(n).let { listOf(it.getDouble(0).toFloat(), it.getDouble(1).toFloat()) } }
            (pts + (-o.getDouble("unit").toFloat())).toFloatArray()
        } ?: FloatArray(0)
        topDog = j.optJSONArray("topdog")?.let { d -> FloatArray(4) { d.getDouble(it).toFloat() } } ?: FloatArray(0)
        passers = j.optJSONArray("passers")?.let { a ->
            List(a.length()) { i ->
                val o = a.getJSONObject(i)
                val p = o.getJSONArray("p")
                Passer(o.getString("sprite"), FloatArray(p.length() * 2) { k -> p.getJSONArray(k / 2).getDouble(k % 2).toFloat() }, o.getDouble("h").toFloat(),
                    o.getDouble("step").toFloat(), o.getDouble("every").toFloat(), o.getDouble("at").toFloat(), o.getLong("wall").toInt(), o.getString("nearer"))
            }
        } ?: emptyList()
        ledge = j.getJSONArray("ledge").getDouble(1).toFloat()
    }

    fun screenBox(): RectF {
        val xs = listOf(screen[0], screen[2], screen[4], screen[6])
        val ys = listOf(screen[1], screen[3], screen[5], screen[7])
        return RectF(xs.min(), ys.min(), xs.max(), ys.max())
    }

    /** A point on the glass, u and v running 0..1 across it. */
    private fun at(u: Float, v: Float): Pair<Float, Float> {
        val tx = screen[0] + (screen[2] - screen[0]) * u
        val ty = screen[1] + (screen[3] - screen[1]) * u
        val bx = screen[6] + (screen[4] - screen[6]) * u
        val by = screen[7] + (screen[5] - screen[7]) * u
        return (tx + (bx - tx) * v) to (ty + (by - ty) * v)
    }

    /** The tube's outline: the quad with its corners rounded off, the way the glass meets the bezel. */
    fun tubePath(): Path {
        val rx = .045f
        val ry = rx * 4f / 3f
        val p = Path()
        fun arc(cx: Float, cy: Float, from: Double) {
            for (i in 0..8) {
                val a = from + i / 8.0 * Math.PI / 2
                val (x, y) = at(cx + rx * Math.cos(a).toFloat(), cy + ry * Math.sin(a).toFloat())
                if (p.isEmpty) p.moveTo(x, y) else p.lineTo(x, y)
            }
        }
        arc(rx, ry, Math.PI)
        arc(1 - rx, ry, Math.PI * 1.5)
        arc(1 - rx, 1 - ry, 0.0)
        arc(rx, 1 - ry, Math.PI * .5)
        p.close()
        return p
    }
}
